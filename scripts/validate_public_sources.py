"""Opt-in live public-board validation in an automatically removed disposable DB.

No AI calls. Full public snapshots are fetched sequentially, but only 1..20 records
per source are imported. Unsampled records are counted as skipped; no stale sweep.
"""
import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg2
from psycopg2 import sql
import config
from jobpulse.database.migrate import upgrade
from jobpulse.database.ingestion import begin_run, persist_snapshot, fail_run
from jobpulse.database.listings import list_jobs
from jobpulse.ingestion.sources import Board, adapter_for
from jobpulse.ingestion.http import SourceError

BOARDS = [Board('python.org'), Board('greenhouse','stripe','Stripe'),
          Board('lever','palantir','Palantir','global'), Board('ashby','ramp','Ramp')]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit',type=int,default=20)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not 1 <= args.limit <= 20: parser.error('--limit must be 1..20')
    options=config.database_options()
    admin=psycopg2.connect(**{**options,'dbname':'postgres'})
    admin.autocommit=True
    name='jobpulse_validation_'+uuid4().hex
    original=config.DB_NAME
    reports=[]
    try:
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        config.DB_NAME=name
        upgrade()
        for board in BOARDS:
            run_id=begin_run(board)
            report=dict(source=board.source,board=board.board,status='failed',fetched=0,
                        sampled=0,inserted=0,updated=0,unchanged=0,skipped=0,failed=0)
            try:
                jobs=adapter_for(board.source).fetch(board)
                if not jobs: raise ValueError('No public postings returned')
                report['fetched']=len(jobs)
                sample=jobs[:args.limit]
                report['sampled']=len(sample)
                report['skipped']=len(jobs)-len(sample)
                first=persist_snapshot(board,sample,run_id,deactivate=False)
                repeat=persist_snapshot(board,sample,begin_run(board),deactivate=False)
                assert first['inserted']==len(sample),first
                assert repeat['inserted']==0 and repeat['unchanged']==len(sample),repeat
                # Mutate one normalized object only in this disposable DB. Never change source data.
                row=sample[0]
                actual_description=row.description
                row.description=(actual_description or '')+'\nDisposable upsert validation marker.'
                changed=persist_snapshot(board,sample,begin_run(board),deactivate=False)
                assert changed['updated']==1 and changed['inserted']==0,changed
                row.description=actual_description
                persist_snapshot(board,sample,begin_run(board),deactivate=False)
                page=list_jobs(source=board.source,page_size=100)
                assert page['total']==len(sample)
                assert all(item['id'] and item['url'] and item['source_job_id'] for item in page['items'])
                report.update(status='succeeded',inserted=first['inserted'],updated=changed['updated'],
                              unchanged=repeat['unchanged'],repeat=repeat)
            except Exception as error:
                fail_run(run_id,error)
                report.update(failed=1,error_type=type(error).__name__)
                if isinstance(error, SourceError): report['reason']=str(error)
            reports.append(report)
    finally:
        config.DB_NAME=original
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(name)))
        admin.close()
    result=dict(validation='disposable sampled import; no AI; database removed',sources=reports)
    rendered=json.dumps(result,indent=2,default=str)
    if args.output: args.output.write_text(rendered+'\n')
    print(rendered)
    return int(any(row['status']!='succeeded' for row in reports))


if __name__=='__main__':
    raise SystemExit(main())
