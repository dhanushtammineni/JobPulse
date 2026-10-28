"""Bounded, sequential batch processing for job embeddings."""

from dataclasses import dataclass

from jobpulse.database.repository import get_jobs_for_embedding_batch

from .embeddings import generate_and_save_job_embedding


@dataclass
class BatchEmbeddingStats:
    selected: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0

    def as_dict(self):
        return {
            "selected": self.selected,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
        }


def embed_jobs_batch(limit, client=None):
    """Embed up to ``limit`` eligible jobs sequentially without retries."""
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer")

    records = (
        get_jobs_for_embedding_batch(limit, model=client.embedding_model)
        if client is not None
        else get_jobs_for_embedding_batch(limit)
    )
    stats = BatchEmbeddingStats(selected=len(records))

    for record in records:
        if record.get("has_embedding"):
            stats.skipped += 1
            continue

        try:
            generate_and_save_job_embedding(record["job"], client=client)
        except Exception:
            stats.failed += 1
        else:
            stats.succeeded += 1

    return stats