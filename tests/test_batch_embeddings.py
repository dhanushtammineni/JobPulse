import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jobpulse.ai.batch_embeddings import embed_jobs_batch


def job(job_id):
    return SimpleNamespace(id=job_id, description=f"Description {job_id}")


class BatchEmbeddingTests(unittest.TestCase):
    @patch("jobpulse.ai.batch_embeddings.generate_and_save_job_embedding")
    @patch("jobpulse.ai.batch_embeddings.get_jobs_for_embedding_batch")
    def test_eligible_jobs_are_selected_with_limit(self, select, embed):
        select.return_value = [{"job": job(1), "has_embedding": False}]

        stats = embed_jobs_batch(3, client=SimpleNamespace(embedding_model="custom-model"))

        select.assert_called_once_with(3, model="custom-model")
        embed.assert_called_once()
        self.assertEqual(stats.selected, 1)

    @patch("jobpulse.ai.batch_embeddings.generate_and_save_job_embedding")
    @patch("jobpulse.ai.batch_embeddings.get_jobs_for_embedding_batch")
    def test_existing_embedding_is_skipped(self, select, embed):
        select.return_value = [{"job": job(1), "has_embedding": True}]

        stats = embed_jobs_batch(3)

        embed.assert_not_called()
        self.assertEqual(
            stats.as_dict(),
            {"selected": 1, "succeeded": 0, "failed": 0, "skipped": 1},
        )

    @patch("jobpulse.ai.batch_embeddings.generate_and_save_job_embedding")
    @patch("jobpulse.ai.batch_embeddings.get_jobs_for_embedding_batch")
    def test_successful_embedding_is_counted(self, select, embed):
        select.return_value = [{"job": job(1), "has_embedding": False}]

        stats = embed_jobs_batch(1)

        self.assertEqual(stats.succeeded, 1)
        self.assertEqual(stats.failed, 0)

    @patch("jobpulse.ai.batch_embeddings.generate_and_save_job_embedding")
    @patch("jobpulse.ai.batch_embeddings.get_jobs_for_embedding_batch")
    def test_one_failure_does_not_stop_batch(self, select, embed):
        select.return_value = [
            {"job": job(1), "has_embedding": False},
            {"job": job(2), "has_embedding": False},
        ]
        embed.side_effect = [RuntimeError("bad job"), None]

        stats = embed_jobs_batch(2)

        self.assertEqual(stats.succeeded, 1)
        self.assertEqual(stats.failed, 1)
        self.assertEqual(embed.call_count, 2)


if __name__ == "__main__":
    unittest.main()