"""Gemini job enrichment workflow and result schema."""

import json
import re
from datetime import datetime
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from jobpulse.database.repository import save_job_ai_enrichment

from .client import AIClient
from .prompts import JOB_ENRICHMENT_SYSTEM_PROMPT


class EnrichmentGenerationError(RuntimeError):
    """Raised when Gemini returns an unusable enrichment response."""


GEMINI_ENRICHMENT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "skills": {"type": "array", "items": {"type": "string"}},
        "category": {"type": "string"},
        "seniority": {"type": "string"},
        "experience_years": {"type": "integer", "nullable": True},
        "employment_type": {"type": "string"},
        "responsibilities": {"type": "array", "items": {"type": "string"}},
        "requirements": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": [
        "skills",
        "category",
        "seniority",
        "employment_type",
        "responsibilities",
        "requirements",
        "summary",
    ],
}

GEMINI_ENRICHMENT_FIELDS = (
    "skills",
    "category",
    "seniority",
    "experience_years",
    "employment_type",
    "responsibilities",
    "requirements",
    "summary",
)


@dataclass
class EnrichmentResult:
    skills: list[str] = field(default_factory=list)
    category: str | None = None
    seniority: str | None = None
    experience_years: int | None = None
    employment_type: str | None = None
    responsibilities: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    summary: str | None = None

    def __post_init__(self):
        for field_name in ("skills", "responsibilities", "requirements"):
            values = getattr(self, field_name)
            if not isinstance(values, list) or not all(
                isinstance(value, str) for value in values
            ):
                raise TypeError(f"{field_name} must be a list of strings")

        for field_name in (
            "category",
            "seniority",
            "employment_type",
            "summary",
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string or None")
        if self.experience_years is not None and (
            isinstance(self.experience_years, bool)
            or not isinstance(self.experience_years, int)
            or self.experience_years < 0
        ):
            raise TypeError("experience_years must be a non-negative integer or None")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EnrichmentResult":
        fields = {
            "skills",
            "category",
            "seniority",
            "experience_years",
            "employment_type",
            "responsibilities",
            "requirements",
            "summary",
        }
        return cls(**{key: data[key] for key in fields if key in data})


def _job_value(job: Any, field_name: str) -> Any:
    if isinstance(job, Mapping):
        return job.get(field_name)
    return getattr(job, field_name, None)


def build_enrichment_text(job: Any) -> str:
    fields = (
        ("Title", "title"),
        ("Company", "company"),
        ("Location", "location"),
        ("Description", "description"),
        ("Employment type", "employment_type"),
        ("Salary", "salary"),
    )
    return "\n".join(
        f"{label}: {str(value).strip()}"
        for label, field_name in fields
        if (value := _job_value(job, field_name)) is not None
        and str(value).strip()
    )


def enrich_job(job: Any) -> EnrichmentResult:
    """Return the enrichment contract without calling an AI provider."""
    return EnrichmentResult(employment_type=_job_value(job, "employment_type"))


def _parse_gemini_enrichment(data: Any) -> EnrichmentResult:
    if not isinstance(data, Mapping):
        raise TypeError("structured response must be a JSON object")
    missing = [
        field_name
        for field_name in GEMINI_ENRICHMENT_FIELDS
        if field_name not in data
    ]
    if missing:
        raise ValueError(
            f"structured response is missing fields: {', '.join(missing)}"
        )

    normalized = dict(data)
    for field_name in ("category", "seniority", "employment_type", "summary"):
        if not isinstance(normalized[field_name], str):
            raise TypeError(f"{field_name} must be a string")
        if normalized[field_name] == "":
            normalized[field_name] = None
    if normalized["experience_years"] is not None and not isinstance(
        normalized["experience_years"], int
    ):
        raise TypeError("experience_years must be an integer or None")

    normalized["seniority"] = _normalize_seniority(normalized["seniority"])
    normalized["employment_type"] = _normalize_employment_type(
        normalized["employment_type"]
    )
    return EnrichmentResult.from_dict(normalized)


SENIORITY_VALUES = {
    "internship": "Internship",
    "entry level": "Entry Level",
    "junior": "Junior",
    "mid level": "Mid Level",
    "senior": "Senior",
    "staff": "Staff",
    "lead": "Lead",
    "principal": "Principal",
    "manager": "Manager",
    "director": "Director",
    "unknown": "Unknown",
}
EMPLOYMENT_TYPE_VALUES = {
    "full time": "Full Time",
    "part time": "Part Time",
    "contract": "Contract",
    "internship": "Internship",
    "temporary": "Temporary",
    "freelance": "Freelance",
    "unknown": "Unknown",
}


def _normalize_seniority(value):
    normalized = re.sub(r"[-_]", " ", (value or "").strip().lower())
    return SENIORITY_VALUES.get(normalized, "Unknown")


def _normalize_employment_type(value):
    normalized = re.sub(r"[-_]", " ", (value or "").strip().lower())
    return EMPLOYMENT_TYPE_VALUES.get(normalized, "Unknown")


def _explicit_experience_years(text):
    match = re.search(r"\b(\d+)\s*\+?\s*years?\b", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def generate_and_save_job_enrichment(job, client: AIClient | None = None):
    """Generate, validate, and persist enrichment for one database-backed job."""
    job_id = _job_value(job, "id")
    if job_id is None:
        raise ValueError("job_id is required to persist job enrichment")

    ai_client = client or AIClient()
    enrichment_text = build_enrichment_text(job)
    if not enrichment_text:
        raise ValueError("job must contain fields to enrich")

    try:
        from google.genai import types

        response = ai_client.provider_client.models.generate_content(
            model=ai_client.model,
            contents=enrichment_text,
            config=types.GenerateContentConfig(
                system_instruction=JOB_ENRICHMENT_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=GEMINI_ENRICHMENT_RESPONSE_SCHEMA,
            ),
        )
        data = json.loads(response.text)
        result = _parse_gemini_enrichment(data)
        if result.experience_years is None:
            result.experience_years = _explicit_experience_years(enrichment_text)
    except EnrichmentGenerationError:
        raise
    except Exception as error:
        raise EnrichmentGenerationError(
            "Job enrichment API returned an invalid response"
        ) from error

    revision = _job_value(job, "semantic_revision")
    save_job_ai_enrichment(
        job_id,
        result,
        model=ai_client.model,
        status="completed",
        enriched_at=datetime.utcnow(),
        **({"expected_revision": revision} if revision is not None else {}),
    )
    return result
