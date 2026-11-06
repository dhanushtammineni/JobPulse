import unittest
from datetime import date
from unittest.mock import patch

from jobpulse.ai.enrichment import EnrichmentResult
from jobpulse.database import repository
from jobpulse.ingestion.models import Job


class FakeCursor:
    def __init__(self, row=None):
        self.executed = []
        self.row = row

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.row or []

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


class AIRepositoryTests(unittest.TestCase):
    def test_legacy_schema_hook_checks_migrations_without_runtime_ddl(self):
        with patch("jobpulse.database.migrate.assert_current") as check:
            repository.ensure_ai_schema()
        check.assert_called_once_with()

    def test_enrichment_upsert_uses_job_key_and_structured_fields(self):
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        result = EnrichmentResult(skills=["Python"], summary="Backend role")
        with patch.object(repository, "ensure_ai_schema"), patch.object(
            repository, "connect_db", return_value=connection
        ):
            repository.save_job_ai_enrichment(7, result, model="test-model")

        query, params = cursor.executed[0]
        self.assertIn("ON CONFLICT (job_id)", query)
        self.assertEqual(params[0], 7)
        self.assertEqual(params[8], "Backend role")
        self.assertEqual(params[9], "test-model")
        self.assertTrue(connection.committed)

    def test_embedding_upsert_records_dimensions(self):
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        with patch.object(repository, "ensure_ai_schema"), patch.object(
            repository, "connect_db", return_value=connection
        ):
            repository.save_job_embedding(7, [0.1, 0.2], "test-embedding")

        query, params = cursor.executed[0]
        self.assertIn("%s::vector", query)
        self.assertEqual(params[0], 7)
        self.assertEqual(params[1], "[0.1,0.2]")
        self.assertEqual(params[2:], ("test-embedding", 2))
        self.assertTrue(connection.committed)

    def test_embedding_search_returns_ordered_jobs_and_similarity(self):
        from datetime import date

        job_row = (
            "Backend Engineer",
            "JobPulse",
            "Remote",
            date.today(),
            "https://example.test/job/1",
            "python.org",
            None,
            None,
            True,
            None,
            "Build APIs",
            "Full-time",
            None,
        )
        cursor = FakeCursor([job_row + (0.1,), job_row[:-1] + ("Other", 0.4)])
        connection = FakeConnection(cursor)
        with patch.object(repository, "ensure_ai_schema"), patch.object(
            repository, "connect_db", return_value=connection
        ):
            results = repository.search_jobs_by_embedding([0.1, 0.2], top_k=2)

        query, params = cursor.executed[0]
        self.assertIn("<=> %s::vector", query)
        self.assertIn("WHERE jobs.is_active = TRUE", query)
        self.assertIn("ORDER BY distance ASC", query)
        self.assertEqual(params, ("[0.1,0.2]", 2))
        self.assertEqual([result["distance"] for result in results], [0.1, 0.4])
        self.assertEqual(results[0]["job"].title, "Backend Engineer")
        self.assertEqual(results[0]["similarity"], 0.9)

    def test_legacy_insert_delegates_to_board_snapshot_without_deactivation(self):
        job = Job('Engineer','Acme','Remote',date.today(),'https://example.test/1')
        stats = dict(inserted=1,updated=0,unchanged=0,failed=0,stale=0)
        with patch('jobpulse.database.ingestion.begin_run', return_value='run'), patch(
            'jobpulse.database.ingestion.persist_snapshot', return_value=stats
        ) as persist:
            self.assertEqual(repository.insert_jobs([job]), {'inserted':1,'updated':0,'stale':0})
        self.assertFalse(persist.call_args.kwargs['deactivate'])


if __name__ == "__main__":
    unittest.main()
