"""Real PostgreSQL assertions; all boards/listings here are deterministic synthetic fixtures."""
from datetime import date
from unittest.mock import Mock
import pytest
from jobpulse.database.migrate import upgrade
from jobpulse.database import repository
from jobpulse.database.ingestion import begin_run, persist_snapshot, fail_run
from jobpulse.database.listings import list_jobs, get_job
from jobpulse.ingestion.models import Job, content_hash
from jobpulse.ingestion.sources import Board
from jobpulse.ingestion.pipeline import run_board, run_sources

pytestmark = pytest.mark.integration


def job(board, identity='1', **kwargs):
    fields = dict(title='Engineer', company='Acme', location='Remote', posted_date=None,
                  url=f'https://example.test/{board.source}/{board.board}/{identity}',
                  description='Build Python APIs', source=board.source, source_board=board.board,
                  source_job_id=identity, employment_type='Full-time', workplace_type='remote')
    fields.update(kwargs)
    return Job(**fields)


def ingest(board, jobs, **kwargs):
    return persist_snapshot(board, jobs, begin_run(board), **kwargs)


def scalar(database, query, params=()):
    with database, database.cursor() as cursor:
        cursor.execute(query,params)
        return cursor.fetchone()[0]


def test_idempotent_url_change_null_preservation_and_ai_invalidation(database):
    upgrade(database)
    board = Board('lever','acme')
    original = job(board, salary='100-200')
    assert ingest(board,[original])['inserted'] == 1
    row = list_jobs()['items'][0]
    job_id, first_seen = row['id'], row['first_seen_at']
    repository.save_job_ai_enrichment(job_id, {'skills':['Python']}, model='fixture')
    repository.save_job_embedding(job_id,[.1,.2],'fixture')
    assert ingest(board,[original])['unchanged'] == 1
    assert repository.get_job_embedding(job_id) is not None
    moved = job(board,url='https://example.test/moved',description=None,company=None,salary=None)
    assert ingest(board,[moved])['updated'] == 1
    assert get_job(job_id).description == 'Build Python APIs'
    assert get_job(job_id).salary == '100-200'
    assert get_job(job_id).first_seen_at.isoformat() == first_seen
    assert repository.get_job_embedding(job_id) is not None  # URL is not semantic content.
    changed = job(board,url=moved.url,description='Build Rust services',salary='200-300')
    assert ingest(board,[changed])['updated'] == 1
    assert scalar(database,'SELECT count(*) FROM jobs') == 1
    assert repository.get_job_ai_enrichment(job_id)['status'] == 'stale'
    assert repository.get_job_embedding(job_id) is None
    assert scalar(database,'SELECT count(*) FROM job_embeddings') == 1  # Artifact retained.
    assert get_job(job_id).content_hash == content_hash(vars(changed))
    assert repository.get_jobs_for_embedding_batch(10)[0]['job'].id == job_id
    assert repository.get_jobs_for_enrichment_batch(10)[0]['job'].id == job_id
    assert repository.search_jobs_by_embedding([.1,.2]) == []
    repository.save_job_embedding(job_id,[.2,.3],'fixture')
    assert repository.get_job_embedding(job_id)['embedding'] == [.2,.3]


def test_cross_source_candidates_keep_distinct_records_and_scoped_ids(database):
    upgrade(database)
    for board in [Board('lever','one'),Board('lever','two'),Board('ashby','one')]:
        ingest(board,[job(board,url='https://example.test/shared')])
    assert scalar(database,'SELECT count(*) FROM jobs') == 3
    assert scalar(database,'SELECT count(*) FROM job_duplicate_candidates') == 2
    assert list_jobs(source='ashby')['total'] == 1
    assert list_jobs(keyword='Python',company='acme',location='remote',workplace_type='remote',employment_type='full-time')['total'] == 3
    assert len(list_jobs(page_size=1,page=2)['items']) == 1
    assert list_jobs(company="'; DROP TABLE jobs;--")['total'] == 0


def test_failed_incomplete_and_different_board_runs_cannot_deactivate(database,monkeypatch):
    upgrade(database)
    a,b = Board('lever','a'),Board('lever','b')
    ingest(a,[job(a)]);ingest(b,[job(b)])
    with database, database.cursor() as cursor:
        cursor.execute("UPDATE jobs SET last_seen_at=CURRENT_TIMESTAMP-INTERVAL '10 days'")
    run_id=begin_run(a)
    with pytest.raises(ValueError,match='Incomplete'):
        persist_snapshot(a,[],run_id,complete=False)
    fail_run(run_id,ValueError())
    assert scalar(database,'SELECT count(*) FROM jobs WHERE is_active') == 2
    broken=Mock();broken.fetch.side_effect=ValueError('partial page')
    good=Mock();good.fetch.return_value=[job(b)]
    import jobpulse.ingestion.pipeline as pipeline
    monkeypatch.setattr(pipeline,'adapter_for',lambda source: broken)
    failed=run_board(a,adapter=broken)
    assert failed['status']=='failed' and failed['stale']==0
    assert run_board(b,adapter=good)['status']=='succeeded'
    assert scalar(database,'SELECT count(*) FROM jobs WHERE is_active') == 2
    assert ingest(a,[])['stale'] == 1  # Explicit successful empty board, age threshold met.
    assert scalar(database,"SELECT is_active FROM jobs WHERE source_board='b'") is True
    assert list_jobs()['ingestion'][0]['status'] in {'succeeded','failed'}


def test_backfill_duplicate_validation_and_run_order(database):
    upgrade(database)
    board=Board('greenhouse','acme')
    ingest(board,[job(board)])
    with database, database.cursor() as cursor:
        cursor.execute("UPDATE jobs SET last_seen_at=CURRENT_TIMESTAMP-INTERVAL '10 days'")
    assert ingest(board,[],deactivate=False)['stale']==0
    assert scalar(database,'SELECT count(*) FROM jobs WHERE is_active')==1
    with pytest.raises(ValueError,match='Repeated'):
        ingest(board,[job(board),job(board)])
    assert scalar(database,'SELECT count(*) FROM jobs')==1
    older=begin_run(board)
    newer=begin_run(board)
    persist_snapshot(board,[job(board)],newer)
    with pytest.raises(ValueError,match='newer'):
        persist_snapshot(board,[],older)
    assert scalar(database,'SELECT is_active FROM jobs') is True


def test_obsolete_ai_results_cannot_clear_staleness(database):
    upgrade(database)
    board=Board('ashby','acme')
    ingest(board,[job(board)])
    record=repository.get_jobs_for_embedding_batch(1)[0]['job']
    revision=record.semantic_revision
    repository.save_job_embedding(record.id,[.1,.2],expected_revision=revision)
    ingest(board,[job(board,description='New responsibilities')])
    with pytest.raises(ValueError,match='changed'):
        repository.save_job_embedding(record.id,[.5,.6],expected_revision=revision)
    with pytest.raises(ValueError,match='changed'):
        repository.save_job_ai_enrichment(record.id,{'skills':['Obsolete']},expected_revision=revision)
    assert repository.get_job_embedding(record.id) is None


def test_provider_metadata_survives_missing_nested_values(database):
    upgrade(database)
    board=Board('lever','acme')
    ingest(board,[job(board,source_metadata={'categories':{'team':'Platform','department':'Engineering'}})])
    before=list_jobs()['items'][0]['content_hash']
    result=ingest(board,[job(board,source_metadata={'categories':{'team':None}})])
    assert result['unchanged']==1
    row=list_jobs()['items'][0]
    assert row['source_metadata']['categories']['team']=='Platform'
    assert row['content_hash']==before
    ingest(board,[job(board,source_metadata={'categories':{'team':'Infrastructure'}})])
    assert list_jobs()['items'][0]['content_hash']!=before


def test_live_validation_harness_samples_only_disposable_database(database,monkeypatch,tmp_path):
    import config
    from scripts import validate_public_sources as validator
    upgrade(database)
    original_name=config.DB_NAME
    ingest(Board('lever','keep'),[job(Board('lever','keep'))])
    def adapter(source):
        result=Mock()
        def fetch(board): return [job(board,str(i)) for i in range(25)]
        result.fetch.side_effect=fetch
        return result
    monkeypatch.setattr(validator,'adapter_for',adapter)
    output=tmp_path/'validation.json'
    monkeypatch.setattr('sys.argv',['validate_public_sources.py','--limit','20','--output',str(output)])
    assert validator.main()==0
    import json
    results=json.loads(output.read_text())['sources']
    assert len(results)==4
    assert all(r['fetched']==25 and r['sampled']==20 and r['inserted']==20
               and r['unchanged']==20 and r['updated']==1 and r['skipped']==5 and r['failed']==0 for r in results)
    assert config.DB_NAME==original_name
    assert scalar(database,'SELECT count(*) FROM jobs')==1
    assert scalar(database,"SELECT count(*) FROM pg_database WHERE datname LIKE %s",('jobpulse_validation_%',))==0
