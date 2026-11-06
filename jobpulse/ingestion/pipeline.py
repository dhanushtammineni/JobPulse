"""Provider isolation, complete-snapshot validation, and CLI orchestration."""
import argparse
import json
import logging
from jobpulse.ingestion.sources import Board, configured_boards, adapter_for
from jobpulse.database.ingestion import begin_run, fail_run, persist_snapshot

logger = logging.getLogger(__name__)


def run_board(board, *, adapter=None, deactivate=True):
    run_id = begin_run(board)
    try:
        jobs = (adapter or adapter_for(board.source)).fetch(board)
        stats = persist_snapshot(board, jobs, run_id, complete=True, deactivate=deactivate)
    except Exception as error:
        fail_run(run_id, error)
        # Never include response bodies, configuration values, or credentials in logs.
        logger.error(json.dumps({'event':'ingestion_failed','source':board.source,
                                 'board':board.board,'run_id':run_id,'error_type':type(error).__name__}))
        return {'source':board.source,'board':board.board,'run_id':run_id,'status':'failed',
                'fetched':0,'inserted':0,'updated':0,'unchanged':0,'failed':1,'stale':0}
    result = {'source':board.source,'board':board.board,'run_id':run_id,'status':'succeeded',**stats}
    logger.info(json.dumps({'event':'ingestion_completed', **result}))
    return result


def run_sources(boards=None, *, source=None, deactivate=True):
    boards = configured_boards() if boards is None else boards
    if source: boards = [board for board in boards if board.source == source]
    return [run_board(board, deactivate=deactivate) for board in boards]


def run_ingestion():
    """Legacy one-pass Python.org entrypoint, including JSON export."""
    from config import OUTPUT_FILE
    from jobpulse.storage.exporter import export_jobs
    from jobpulse.database.repository import get_jobs_by_filter
    result = run_board(Board('python.org'))
    if result['status'] != 'succeeded': raise RuntimeError('Python.org ingestion failed')
    from pathlib import Path
    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    export_jobs([j for j in get_jobs_by_filter() if j.source == 'python.org'], OUTPUT_FILE)
    return {k: result[k] for k in ('fetched','inserted','updated','unchanged','failed','stale')}


def main():
    parser = argparse.ArgumentParser(description='Sequential public-board ingestion; migrations must be current')
    parser.add_argument('--source', choices=['python.org','greenhouse','lever','ashby'])
    parser.add_argument('--backfill', action='store_true', help='Idempotent refresh without deactivation')
    args = parser.parse_args()
    from jobpulse.database.migrate import assert_current
    assert_current()
    results = run_sources(source=args.source, deactivate=not args.backfill)
    if not results:
        parser.error("No matching enabled boards; configure JOBPULSE_SOURCES and board arrays")
    print(json.dumps(results, default=str))
    return int(any(result['status'] == 'failed' for result in results))


if __name__ == '__main__':
    raise SystemExit(main())
