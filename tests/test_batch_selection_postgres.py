"""Real SQL regression tests; opt in with JOBPULSE_TEST_POSTGRES_DSN."""

import os
from types import SimpleNamespace

import psycopg2
import pytest

import config
from jobpulse.ai.batch_embeddings import embed_jobs_batch
from jobpulse.database import repository


@pytest.fixture
def database(monkeypatch):
    dsn = os.getenv("JOBPULSE_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set JOBPULSE_TEST_POSTGRES_DSN to run PostgreSQL integration tests")
    # An explicitly configured but unreachable database is a test failure.
    connection = psycopg2.connect(dsn, connect_timeout=5)
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TEMP TABLE jobs (
                    id BIGINT PRIMARY KEY, title TEXT, company TEXT, location TEXT,
                    posted_date DATE DEFAULT CURRENT_DATE, url TEXT,
                    source TEXT, first_seen_at TIMESTAMP, last_seen_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE, source_job_id TEXT,
                    description TEXT, employment_type TEXT, salary TEXT
                );
                CREATE TEMP TABLE job_ai_enrichment (
                    job_id BIGINT PRIMARY KEY, status TEXT, model TEXT
                );
                CREATE TEMP TABLE job_embeddings (
                    job_id BIGINT PRIMARY KEY, embedding TEXT,
                    embedding_model TEXT, dimensions INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # The TEXT vector column lets selection tests run on plain PostgreSQL;
            # provider output and pgvector operators are outside this PR's scope.
            cursor.execute("SET LOCAL search_path = pg_temp")

        class Session:
            def cursor(self):
                return connection.cursor()

            def commit(self):
                pass

            def rollback(self):
                connection.rollback()

            def close(self):
                pass

        monkeypatch.setattr(repository, "connect_db", lambda: Session())

        def add_job(job_id, *, status=None, model=None, enriched=False,
                    embedding_model=None, active=True, description="Build APIs"):
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO jobs (id, title, is_active, description) VALUES (%s,%s,%s,%s)",
                    (job_id, f"Fixture {job_id}", active, description),
                )
                if enriched:
                    cursor.execute(
                        "INSERT INTO job_ai_enrichment VALUES (%s,%s,%s)",
                        (job_id, status, model),
                    )
                if embedding_model is not None:
                    cursor.execute(
                        "INSERT INTO job_embeddings (job_id, embedding_model) VALUES (%s,%s)",
                        (job_id, embedding_model),
                    )

        yield connection, add_job
    finally:
        connection.rollback()
        connection.close()


def ids(records):
    return [record["job"].id for record in records]


def test_enrichment_null_safe_eligibility(database):
    _, add = database
    add(1)
    add(2, enriched=True, status="completed", model="current")
    add(3, enriched=True, status="failed", model="current")
    add(4, enriched=True, status="pending", model="current")
    add(5, enriched=True, status="completed", model="old")
    add(6, enriched=True, status=None, model="current")
    add(7, enriched=True, status="completed", model=None)
    add(8, active=False)
    add(9, description="  ")
    add(10, description=None)
    assert ids(repository.get_jobs_for_enrichment_batch(20, model="current")) == [1, 3, 4, 5, 6, 7]
    assert ids(repository.get_jobs_for_enrichment_batch(2, model="current")) == [1, 3]


def test_embedding_pending_filter_precedes_limit(database, monkeypatch):
    _, add = database
    monkeypatch.setattr(config, "AI_EMBEDDING_MODEL", "current")
    add(1, embedding_model="current")
    add(2)
    add(3, embedding_model="old")
    add(4, active=False)
    add(5, description=" ")
    add(6, description=None)
    assert ids(repository.get_jobs_for_embedding_batch(1)) == [2]
    records = repository.get_jobs_for_embedding_batch(10)
    assert ids(records) == [2, 3]
    assert all(not record["has_embedding"] for record in records)
    assert ids(repository.get_jobs_for_embedding_batch(10, model="old")) == [1, 2]


def test_repeated_embedding_batches_progress(database, monkeypatch):
    connection, add = database
    add(1, embedding_model="current")
    add(2)
    add(3, embedding_model="old")
    add(4)
    calls = []

    def persist_fixture(job, client=None):
        calls.append(job.id)
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO job_embeddings (job_id, embedding_model) VALUES (%s,%s)
                ON CONFLICT (job_id) DO UPDATE SET embedding_model=EXCLUDED.embedding_model
            """, (job.id, client.embedding_model))

    monkeypatch.setattr("jobpulse.ai.batch_embeddings.generate_and_save_job_embedding", persist_fixture)
    # Deliberately differs from the global default: selection must follow client.
    monkeypatch.setattr(config, "AI_EMBEDDING_MODEL", "other-default")
    client = SimpleNamespace(embedding_model="current")
    assert embed_jobs_batch(2, client).succeeded == 2
    assert embed_jobs_batch(2, client).succeeded == 1
    assert embed_jobs_batch(2, client).as_dict() == {
        "selected": 0, "succeeded": 0, "failed": 0, "skipped": 0,
    }
    assert calls == [2, 3, 4]


def test_empty_eligible_sets(database):
    _, add = database
    assert repository.get_jobs_for_enrichment_batch(10) == []
    assert repository.get_jobs_for_embedding_batch(10) == []
    add(1, enriched=True, status="completed", model=config.AI_MODEL,
        embedding_model=config.AI_EMBEDDING_MODEL)
    assert repository.get_jobs_for_enrichment_batch(10) == []
    assert repository.get_jobs_for_embedding_batch(10) == []
