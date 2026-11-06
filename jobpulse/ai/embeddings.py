"""Embedding generation and persistence workflow."""

from collections.abc import Mapping

from jobpulse.database.repository import save_job_embedding

from .client import AIClient


class EmbeddingGenerationError(RuntimeError):
    """Raised when the configured embedding provider cannot generate a vector."""


def _job_value(job, field_name):
    if isinstance(job, Mapping):
        return job.get(field_name)
    return getattr(job, field_name, None)


def build_job_embedding_text(job) -> str:
    """Build deterministic semantic text from the populated job fields."""
    fields = (
        ("Title", "title"),
        ("Company", "company"),
        ("Location", "location"),
        ("Description", "description"),
        ("Employment type", "employment_type"),
        ("Salary", "salary"),
    )
    parts = []
    for label, field_name in fields:
        value = _job_value(job, field_name)
        if value is not None and str(value).strip():
            parts.append(f"{label}: {str(value).strip()}")
    return "\n".join(parts)


def create_embedding(text: str, client: AIClient | None = None) -> tuple[list[float], int]:
    """Generate an embedding with the configured model and return its dimension."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("embedding text must be a non-empty string")

    ai_client = client or AIClient()
    try:
        response = ai_client.provider_client.models.embed_content(
            model=ai_client.embedding_model,
            contents=text,
        )
        embedding = list(response.embeddings[0].values)
    except Exception as error:
        raise EmbeddingGenerationError("Embedding API request failed") from error

    if not embedding:
        raise EmbeddingGenerationError("Embedding API returned an empty vector")
    return embedding, len(embedding)


def generate_and_save_job_embedding(job, job_id=None, client: AIClient | None = None):
    """Generate and persist one embedding for a database-backed job."""
    resolved_job_id = job_id if job_id is not None else _job_value(job, "id")
    if resolved_job_id is None:
        raise ValueError("job_id is required to persist a job embedding")

    ai_client = client or AIClient()
    embedding_text = build_job_embedding_text(job)
    embedding, dimensions = create_embedding(embedding_text, client=ai_client)

    revision = _job_value(job, "semantic_revision")
    save_job_embedding(
        resolved_job_id,
        embedding,
        embedding_model=ai_client.embedding_model,
        **({"expected_revision": revision} if revision is not None else {}),
    )
    return embedding, dimensions
