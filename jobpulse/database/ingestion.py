"""Atomic, bounded per-board snapshots. Fetch/validation completes before writes."""
from datetime import datetime, timezone
import json
from uuid import uuid4
from psycopg2.extras import RealDictCursor, execute_values, Json
from jobpulse.database.connections import connect_db
from jobpulse.ingestion.models import CONTENT_FIELDS, SEMANTIC_FIELDS, content_hash, valid_url

MAX_BOARD_JOBS = 10000
FIELDS = tuple(dict.fromkeys((*CONTENT_FIELDS, 'url', 'apply_url', 'source_metadata')))


def merge_metadata(previous, incoming):
    result = dict(previous or {})
    for key,value in incoming.items():
        if value is None: continue
        result[key] = merge_metadata(result.get(key) if isinstance(result.get(key),dict) else {}, value) if isinstance(value,dict) else value
    return result


def begin_run(board):
    run_id = str(uuid4())
    conn = connect_db()
    try:
        with conn, conn.cursor() as cursor:
            cursor.execute('INSERT INTO ingestion_runs(id,source,source_board,status) VALUES(%s,%s,%s,\'running\')',
                           (run_id, board.source, board.board))
        return run_id
    finally:
        conn.close()


def fail_run(run_id, error):
    conn = connect_db()
    try:
        with conn, conn.cursor() as cursor:
            cursor.execute("UPDATE ingestion_runs SET status='failed', finished_at=clock_timestamp(), failed=1, error_type=%s WHERE id=%s AND status='running'",
                           (type(error).__name__, run_id))
    finally:
        conn.close()


def persist_snapshot(board, jobs, run_id, *, complete=True, stale_after_days=7, deactivate=True):
    if not complete:
        raise ValueError('Incomplete source snapshots cannot be persisted')
    if len(jobs) > MAX_BOARD_JOBS or stale_after_days < 1:
        raise ValueError('Board size or stale interval outside supported bounds')
    seen, urls = set(), set()
    for job in jobs:
        if not isinstance(job.title, str) or not job.title.strip():
            raise ValueError('Missing job title')
        valid_url(job.url)
        if job.apply_url: valid_url(job.apply_url)
        if job.source != board.source or job.source_board != board.board:
            raise ValueError('Job provenance differs from board')
        identity = job.source_job_id or job.url
        if identity in seen or job.url in urls:
            raise ValueError('Repeated listing identity or URL')
        job.source_job_id = str(identity)
        seen.add(identity); urls.add(job.url)
    stats = dict(fetched=len(jobs), inserted=0, updated=0, unchanged=0, failed=0, stale=0)
    conn = connect_db()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SET LOCAL statement_timeout='120s'")
                cursor.execute("SET LOCAL lock_timeout='30s'")
                cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                               (board.source + ':' + board.board,))
                cursor.execute("SELECT * FROM ingestion_runs WHERE id=%s FOR UPDATE", (run_id,))
                run = cursor.fetchone()
                if not run or run['status'] != 'running' or (run['source'],run['source_board']) != (board.source,board.board):
                    raise ValueError('Invalid or already finished ingestion run')
                cursor.execute("SELECT 1 FROM ingestion_runs WHERE source=%s AND source_board=%s AND status='succeeded' AND started_at>%s LIMIT 1",
                               (board.source, board.board, run['started_at']))
                if cursor.fetchone(): raise ValueError('A newer board run already completed')
                cursor.execute('SELECT * FROM jobs WHERE source=%s AND source_board=%s FOR UPDATE',
                               (board.source, board.board))
                existing = cursor.fetchall()
                by_id = {row['source_job_id']: row for row in existing if row['source_job_id']}
                by_url = {row['url']: row for row in existing}
                rows, invalidate = [], []
                for job in jobs:
                    old = by_id.get(job.source_job_id) or by_url.get(job.url)
                    if old and old['source_job_id'] not in (None, job.source_job_id):
                        raise ValueError('URL belongs to a different stable source identity')
                    incoming = vars(job)
                    merged = {key: incoming.get(key) if incoming.get(key) is not None else (old or {}).get(key) for key in FIELDS}
                    metadata = merge_metadata((old or {}).get('source_metadata'), job.source_metadata)
                    merged['source_metadata'] = metadata
                    digest = content_hash(merged)
                    semantic_change = bool(old) and any(merged[k] != old.get(k) for k in SEMANTIC_FIELDS)
                    changed = bool(old) and (any(merged[k] != old.get(k) for k in FIELDS) or not old['is_active'])
                    stats['inserted' if not old else 'updated' if changed else 'unchanged'] += 1
                    if semantic_change: invalidate.append(old['id'])
                    rows.append(tuple(Json(merged[k]) if k == 'source_metadata' else merged[k] for k in FIELDS) + (
                        board.source, board.board, job.source_job_id, digest,
                        (old['semantic_revision'] if old else 0) + int(semantic_change)))
                # Upsert by identity; no delete/reinsert, so all job foreign keys survive.
                # A previously URL-only row is adopted before the identity upsert.
                for job in jobs:
                    old = by_url.get(job.url)
                    if old and old['source_job_id'] is None:
                        cursor.execute('UPDATE jobs SET source_job_id=%s WHERE id=%s', (job.source_job_id,old['id']))
                if rows:
                    columns = (*FIELDS, 'source', 'source_board', 'source_job_id', 'content_hash', 'semantic_revision')
                    execute_values(cursor, f"""INSERT INTO jobs ({','.join(columns)}) VALUES %s
                        ON CONFLICT (source,source_board,source_job_id) WHERE source_job_id IS NOT NULL
                        DO UPDATE SET {','.join(f'{key}=EXCLUDED.{key}' for key in (*FIELDS,'content_hash','semantic_revision'))},
                          last_seen_at=CURRENT_TIMESTAMP, is_active=TRUE""", rows, page_size=250)
                if invalidate:
                    cursor.execute("UPDATE job_ai_enrichment SET status='stale',updated_at=CURRENT_TIMESTAMP WHERE job_id=ANY(%s)", (invalidate,))
                    cursor.execute('UPDATE job_embeddings SET is_stale=TRUE WHERE job_id=ANY(%s)', (invalidate,))
                if deactivate:
                    # Snapshot absence alone is insufficient: also require seven days of absence.
                    cursor.execute("""UPDATE jobs SET is_active=FALSE WHERE source=%s AND source_board=%s
                        AND is_active AND NOT (source_job_id=ANY(%s))
                        AND last_seen_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')""",
                                   (board.source,board.board,list(seen),stale_after_days))
                    stats['stale'] = cursor.rowcount
                cursor.execute("""INSERT INTO job_duplicate_candidates(job_id,candidate_job_id,reason)
                    SELECT LEAST(a.id,b.id),GREATEST(a.id,b.id),'exact company/title/location across providers'
                    FROM jobs a JOIN jobs b ON a.source<>b.source AND a.id<>b.id
                      AND lower(btrim(a.company))=lower(btrim(b.company))
                      AND lower(btrim(a.title))=lower(btrim(b.title))
                      AND lower(btrim(a.location))=lower(btrim(b.location))
                    WHERE a.source=%s AND a.source_board=%s AND a.is_active AND b.is_active
                      AND NULLIF(btrim(a.company),'') IS NOT NULL
                      AND NULLIF(btrim(a.location),'') IS NOT NULL
                    ON CONFLICT DO NOTHING""", (board.source,board.board))
                cursor.execute("""UPDATE ingestion_runs SET status='succeeded',finished_at=clock_timestamp(),
                    fetched=%s,inserted=%s,updated=%s,unchanged=%s,failed=%s,stale=%s WHERE id=%s""",
                               (*stats.values(), run_id))
        return stats
    finally:
        conn.close()
