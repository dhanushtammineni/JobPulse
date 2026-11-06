"""Parameterized, bounded listing queries. Legacy AI query projections stay stable."""
from psycopg2.extras import RealDictCursor
from .connections import connect_db
from jobpulse.ingestion.models import Job


def get_job(job_id):
    conn = connect_db()
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('SELECT * FROM jobs WHERE id=%s AND is_active', (job_id,))
            row = cursor.fetchone()
            return Job(**dict(row)) if row else None
    finally:
        conn.close()


def list_jobs(*, page=1, page_size=20, source=None, keyword=None, location=None,
              company=None, employment_type=None, workplace_type=None):
    if page < 1 or not 1 <= page_size <= 100 or page > 10000:
        raise ValueError('Invalid pagination')
    clauses, values = ['is_active'], []
    for key, value in [('source',source), ('employment_type',employment_type), ('workplace_type',workplace_type)]:
        if value:
            clauses.append(f'lower({key})=lower(%s)'); values.append(value)
    for key, value in [('company',company), ('location',location)]:
        if value:
            clauses.append(f'{key} ILIKE %s'); values.append('%'+value+'%')
    if keyword:
        clauses.append("(title ILIKE %s OR description ILIKE %s)")
        values.extend(['%'+keyword+'%']*2)
    where = ' AND '.join(clauses)
    conn = connect_db()
    try:
        # Keep totals and results on a single MVCC snapshot during ingestion.
        conn.set_session(isolation_level='REPEATABLE READ', readonly=True)
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(f'SELECT count(*) AS total FROM jobs WHERE {where}', values)
            total = cursor.fetchone()['total']
            cursor.execute(f'SELECT * FROM jobs WHERE {where} ORDER BY posted_date DESC NULLS LAST,id DESC LIMIT %s OFFSET %s',
                           [*values,page_size,(page-1)*page_size])
            items = [Job(**dict(row)).to_dict() for row in cursor.fetchall()]
            cursor.execute("""SELECT source, source_board, status, started_at, finished_at, fetched,
                inserted, updated, unchanged, failed, stale FROM (
                  SELECT DISTINCT ON(source,source_board) * FROM ingestion_runs
                  ORDER BY source,source_board,started_at DESC,id DESC) latest
                ORDER BY source,source_board""")
            runs = [dict(row) for row in cursor.fetchall()]
            return dict(items=items,total=total,page=page,page_size=page_size,ingestion=runs)
    finally:
        conn.close()
