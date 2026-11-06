"""Deterministic resume-to-job matching based on stored AI data."""

import math
import re
from uuid import UUID

from pydantic import BaseModel

from jobpulse.database.repository import (
    get_job_ai_enrichment,
    get_job_by_id,
    get_job_embedding,
    get_resume_embedding,
    get_resume_profile,
)


SIMILARITY_WEIGHT = 0.5
SKILL_COVERAGE_WEIGHT = 0.4
EXPERIENCE_WEIGHT = 0.1


class MatchResult(BaseModel):
    resume_id: UUID
    job_id: int
    similarity: float
    matched_skills: list[str]
    missing_skills: list[str]
    experience_match: bool | None
    explanation: str
    match_score: float


class MatchError(RuntimeError):
    """Raised when required data for matching is unavailable or invalid."""


SKILL_ALIASES = {
    "rest apis": "http/rest",
    "http/rest": "http/rest",
    "postgresql": "postgres",
    "postgres": "postgres",
    "fastapi": "fast api",
    "fast api": "fast api",
}


def _normalize_skill(value):
    return " ".join(str(value).strip().casefold().split())


def _canonical_skill(value):
    normalized = _normalize_skill(value)
    return SKILL_ALIASES.get(normalized, normalized)


def _unique_skills(values):
    result = []
    seen = set()
    for value in values:
        normalized = _normalize_skill(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append((normalized, str(value).strip()))
    return result


def _cosine_similarity(left, right):
    if len(left) != len(right) or not left:
        raise MatchError("resume and job embeddings must have the same dimension")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        raise MatchError("resume and job embeddings must be non-zero vectors")
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def _resume_years(profile):
    years = []
    for item in profile.experience:
        text = f"{item.duration} {item.description}"
        years.extend(int(value) for value in re.findall(r"\b(\d+)\+?\s+years?\b", text, re.I))
    return max(years) if years else None


def _experience_match(profile, enrichment):
    required_years = enrichment.get("experience_years")
    if required_years is None:
        return None
    resume_years = _resume_years(profile)
    if resume_years is None:
        return None
    return resume_years >= required_years


def _calculate_match_score(similarity, matched_skills, required_skills, experience_match):
    skill_coverage = (
        len(matched_skills) / len(required_skills) if required_skills else 0.0
    )
    normalized_similarity = (similarity + 1.0) / 2.0
    experience_signal = (
        1.0
        if experience_match is True
        else -1.0
        if experience_match is False
        else 0.0
    )
    raw_score = 100.0 * (
        SIMILARITY_WEIGHT * normalized_similarity
        + SKILL_COVERAGE_WEIGHT * skill_coverage
        + EXPERIENCE_WEIGHT * experience_signal
    )
    return max(0.0, min(100.0, raw_score))


def _build_explanation(
    match_score, similarity, matched_skills, missing_skills, experience_match
):
    overall = (
        f"Overall match score: {match_score:.1f}/100 "
        f"with cosine similarity {similarity:.3f}."
    )
    strengths = (
        "Matched strengths: " + ", ".join(matched_skills) + "."
        if matched_skills
        else "Matched strengths: none identified."
    )
    if missing_skills:
        gaps = "Missing skills: " + ", ".join(missing_skills) + "."
    else:
        gaps = "Missing skills: none identified."
        if not matched_skills:
            gaps = "No required job skills identified."

    experience = (
        "Experience alignment: matches the stated requirement."
        if experience_match is True
        else "Experience alignment: does not match the stated requirement."
        if experience_match is False
        else "Experience alignment: not determined from available data."
    )
    return " ".join((overall, strengths, gaps, experience))


def match_resume_to_job(resume_id: UUID, job_id: int) -> MatchResult:
    profile = get_resume_profile(resume_id)
    if profile is None:
        raise MatchError(f"resume profile not found: {resume_id}")

    job = get_job_by_id(job_id)
    if job is None:
        raise MatchError(f"job not found: {job_id}")

    enrichment = get_job_ai_enrichment(job_id)
    if enrichment is None or enrichment.get("status") == "stale":
        raise MatchError(f"job enrichment not found: {job_id}")

    resume_embedding = get_resume_embedding(resume_id)
    job_embedding = get_job_embedding(job_id)
    if resume_embedding is None:
        raise MatchError(f"resume embedding not found: {resume_id}")
    if job_embedding is None:
        raise MatchError(f"job embedding not found: {job_id}")

    try:
        similarity = _cosine_similarity(
            resume_embedding["embedding"], job_embedding["embedding"]
        )
    except (TypeError, ValueError) as error:
        raise MatchError("stored embeddings must contain numeric vectors") from error

    resume_skills = _unique_skills(profile.skills + profile.technologies)
    job_skills = _unique_skills(enrichment.get("skills", []))
    resume_skill_names = {
        _canonical_skill(display) for _, display in resume_skills
    }
    matched_skills = [
        display
        for _, display in job_skills
        if _canonical_skill(display) in resume_skill_names
    ]
    missing_skills = [
        display
        for _, display in job_skills
        if _canonical_skill(display) not in resume_skill_names
    ]
    experience_match = _experience_match(profile, enrichment)
    match_score = _calculate_match_score(
        similarity,
        matched_skills,
        job_skills,
        experience_match,
    )
    explanation = _build_explanation(
        match_score,
        similarity,
        matched_skills,
        missing_skills,
        experience_match,
    )

    return MatchResult(
        resume_id=resume_id,
        job_id=job_id,
        similarity=similarity,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        experience_match=experience_match,
        explanation=explanation,
        match_score=match_score,
    )