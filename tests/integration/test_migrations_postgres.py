"""Real PostgreSQL/pgvector tests. All inserted records are synthetic test fixtures."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import shutil
from unittest.mock import patch

import psycopg2
import pytest
from fastapi.testclient import TestClient

import api
import config
from jobpulse.ai.resume import ResumeProfile
from jobpulse.database import repository
from jobpulse.database.migrate import MIGRATIONS, MigrationError, assert_current, upgrade
from jobpulse.ingestion.models import Job

pytestmark = pytest.mark.integration


def test_clean_upgrade_repeat_and_repository_roundtrip(database):
    assert upgrade(database) == ['001_jobs.sql', '002_freshness.sql', '003_ai.sql']
    assert upgrade(database) == []
    assert_current(database)
    job = Job('Fixture engineer', 'Test fixture', 'Remote', date(2026, 1, 1),
              'https://example.test/migration', description='Synthetic Python role')
    assert repository.insert_jobs([job]) == {'inserted': 1, 'updated': 0, 'stale': 0}
    job.title = 'Updated fixture'
    assert repository.insert_jobs([job])['updated'] == 1
    with database, database.cursor() as cursor:
        cursor.execute('SELECT id FROM jobs WHERE url = %s', (job.url,))
        job_id = cursor.fetchone()[0]
    repository.save_job_ai_enrichment(job_id, {'skills': ['Python']}, model='fixture-model')
    repository.save_job_embedding(job_id, [0.1, 0.2], 'fixture-embedding')
    assert repository.get_job_embedding(job_id)['dimensions'] == 2
    assert repository.get_job_ai_enrichment(job_id)['skills'] == ['Python']
    resume_id = repository.save_resume_profile(ResumeProfile(skills=['Python'], technologies=[]))
    repository.save_resume_embedding(resume_id, [0.2, 0.3], 'fixture-embedding')
    assert repository.get_resume_profile(resume_id).skills == ['Python']
    assert repository.get_resume_embedding(resume_id)['dimensions'] == 2
    with TestClient(api.app) as client:
        assert client.get('/health/ready').status_code == 200
        response = client.get('/jobs')
        assert response.status_code == 200
        assert response.json()[0]['title'] == 'Updated fixture'


def test_legacy_jobs_preserved_and_partial_null_columns_repaired(database):
    with database, database.cursor() as cursor:
        cursor.execute('''CREATE TABLE jobs (id SERIAL PRIMARY KEY, title TEXT, company TEXT,
            location TEXT, posted_date DATE, url TEXT UNIQUE, created_timestamp TIMESTAMP,
            source TEXT, first_seen_at TIMESTAMP, last_seen_at TIMESTAMP, is_active BOOLEAN)''')
        cursor.execute('''INSERT INTO jobs (title, company, location, posted_date, url, created_timestamp)
            VALUES ('Fixture', 'Test', 'Remote', '2026-01-01', 'https://example.test/legacy', '2026-01-01')''')
    upgrade(database)
    with database, database.cursor() as cursor:
        cursor.execute('SELECT id, title, source, first_seen_at = created_timestamp, is_active FROM jobs')
        assert cursor.fetchone() == (1, 'Fixture', 'python.org', True, True)
    assert_current(database)


def test_adopts_existing_ai_tables_without_losing_artifacts(database):
    # Model the previous runtime-DDL schema: tables exist, no migration history.
    upgrade(database)
    with database, database.cursor() as cursor:
        cursor.execute("INSERT INTO jobs (title, company, location, posted_date, url) VALUES ('Fixture', 'Test', 'Remote', '2026-01-01', 'https://example.test/ai') RETURNING id")
        job_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO job_embeddings (job_id, embedding, embedding_model, dimensions) VALUES (%s, '[0.1,0.2]', 'fixture', 2)", (job_id,))
        cursor.execute('DROP TABLE schema_migrations')
    upgrade(database)
    with database, database.cursor() as cursor:
        cursor.execute('SELECT embedding_model, dimensions FROM job_embeddings WHERE job_id = %s', (job_id,))
        assert cursor.fetchone() == ('fixture', 2)


def test_failed_migration_rolls_back_all_pending_ddl_and_history(database, tmp_path):
    for path in MIGRATIONS.glob('*.sql'):
        shutil.copy(path, tmp_path)
    (tmp_path / '004_failure.sql').write_text('CREATE TABLE should_rollback (id INTEGER); SELECT 1/0;')
    with pytest.raises(psycopg2.errors.DivisionByZero):
        upgrade(database, tmp_path)
    with database, database.cursor() as cursor:
        cursor.execute("SELECT to_regclass('jobs'), to_regclass('should_rollback'), to_regclass('schema_migrations')")
        assert cursor.fetchone() == (None, None, None)
    assert len(upgrade(database)) == 3


def test_detects_modified_migration_and_unknown_newer_release(database, tmp_path):
    upgrade(database)
    for path in MIGRATIONS.glob('*.sql'):
        shutil.copy(path, tmp_path)
    path = tmp_path / '001_jobs.sql'
    path.write_text(path.read_text() + '\n-- edited after application\n')
    with pytest.raises(MigrationError, match='history differs'):
        upgrade(database, tmp_path)
    with database, database.cursor() as cursor:
        cursor.execute("INSERT INTO schema_migrations (version, checksum) VALUES ('999_future.sql', %s)", ('0' * 64,))
    with pytest.raises(MigrationError, match='history differs'):
        assert_current(database)


def test_check_refuses_empty_and_pending_databases_without_ddl(database):
    with pytest.raises(MigrationError, match='not initialized'):
        assert_current(database)
    with database, database.cursor() as cursor:
        cursor.execute("SELECT to_regclass('schema_migrations')")
        assert cursor.fetchone()[0] is None
    upgrade(database)
    with database, database.cursor() as cursor:
        cursor.execute("DELETE FROM schema_migrations WHERE version = '003_ai.sql'")
    with pytest.raises(MigrationError, match='pending'):
        assert_current(database)


def test_legacy_duplicate_urls_fail_without_data_loss(database):
    with database, database.cursor() as cursor:
        cursor.execute('''CREATE TABLE jobs (id SERIAL PRIMARY KEY, title TEXT, company TEXT,
            location TEXT, posted_date DATE, url TEXT)''')
        cursor.execute("INSERT INTO jobs (url) VALUES ('https://example.test/duplicate'), ('https://example.test/duplicate')")
    with pytest.raises(psycopg2.errors.UniqueViolation):
        upgrade(database)
    with database, database.cursor() as cursor:
        cursor.execute('SELECT count(*) FROM jobs')
        assert cursor.fetchone()[0] == 2
        cursor.execute("SELECT to_regclass('schema_migrations')")
        assert cursor.fetchone()[0] is None


def test_concurrent_migrators_serialize(database):
    def migrate():
        connection = psycopg2.connect(**config.database_options())
        try:
            return upgrade(connection)
        finally:
            connection.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: migrate(), range(2)))
    assert sorted(map(len, results)) == [0, 3]
    assert_current(database)


def test_readiness_hides_database_errors(database):
    with patch('api.assert_current', side_effect=psycopg2.OperationalError('private connection details')):
        response = TestClient(api.app).get('/health/ready')
    assert response.status_code == 503
    assert response.json() == {'detail': 'Database is not ready'}


def test_api_reads_and_startup_work_in_read_only_transactions(database):
    upgrade(database)
    def read_only_connection():
        connection = psycopg2.connect(**config.database_options())
        connection.set_session(readonly=True)
        return connection
    with patch('jobpulse.database.migrate.connect_db', side_effect=read_only_connection), \
         patch.object(repository, 'connect_db', side_effect=read_only_connection):
        with TestClient(api.app) as client:
            assert client.get('/health/ready').status_code == 200
            assert client.get('/jobs').status_code == 404
