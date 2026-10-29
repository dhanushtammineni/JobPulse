from __future__ import annotations

from typing import TYPE_CHECKING

from .connections import connect_db, psycopg2
import json
from uuid import UUID, uuid4

from psycopg2.extras import Json
from jobpulse.utils.logger import logger
from jobpulse.ingestion.models import Job
import config

if TYPE_CHECKING:
    from jobpulse.ai.resume import ResumeProfile


JOB_COLUMNS = """
    title, company, location, posted_date, url,
    source, first_seen_at, last_seen_at, is_active,
    source_job_id, description, employment_type, salary
"""


def ensure_ai_schema():
    """Compatibility hook: verify migrations; never change schema at runtime."""
    from .migrate import assert_current
    assert_current()


def ensure_job_freshness_schema():
    """Compatibility hook for older scripts. Run the migration CLI first."""
    from .migrate import assert_current
    assert_current()


def insert_jobs(jobs, source="python.org", complete_run=False, stale_after_days=7):
    if not jobs:
        logger.warning("skipping empty ingestion run")
        return {"inserted": 0, "updated": 0, "stale": 0}

    conn = None
    cursor = None
    try:
        conn = connect_db()
        cursor = conn.cursor()
        urls = list(dict.fromkeys(job.url for job in jobs))
        cursor.execute("SELECT url FROM jobs WHERE url = ANY(%s)", (urls,))
        existing_urls = {row[0] for row in cursor.fetchall()}
        for job in jobs:
            cursor.execute(
                f"""
                INSERT INTO jobs ({JOB_COLUMNS})
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP, TRUE, %s, %s, %s, %s)
                ON CONFLICT (url)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    company = EXCLUDED.company,
                    location = EXCLUDED.location,
                    posted_date = EXCLUDED.posted_date,
                    source = EXCLUDED.source,
                    source_job_id = EXCLUDED.source_job_id,
                    description = EXCLUDED.description,
                    employment_type = EXCLUDED.employment_type,
                    salary = EXCLUDED.salary,
                    last_seen_at = CURRENT_TIMESTAMP,
                    is_active = TRUE
                """,
                (
                    job.title,
                    job.company,
                    job.location,
                    job.posted_date,
                    job.url,
                    source,
                    job.source_job_id,
                    job.description,
                    job.employment_type,
                    job.salary,
                ),
            )

        inactive_count = 0
        if complete_run:
            cursor.execute(
                """
                UPDATE jobs
                SET is_active = FALSE
                WHERE source = %s
                  AND is_active = TRUE
                  AND last_seen_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                """,
                (source, stale_after_days),
            )
            inactive_count = cursor.rowcount

        conn.commit()
        logger.info(
            "upserted %d jobs from %s; marked %d stale jobs inactive",
            len(jobs),
            source,
            inactive_count,
        )
        return {
            "inserted": len(set(urls) - existing_urls),
            "updated": len(set(urls) & existing_urls),
            "stale": inactive_count,
        }
    except psycopg2.Error:
        if conn:
            conn.rollback()
        logger.exception("failed to upsert jobs")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _enrichment_values(enrichment):
    if hasattr(enrichment, "to_dict"):
        enrichment = enrichment.to_dict()
    return {
        "skills": enrichment.get("skills", []),
        "category": enrichment.get("category"),
        "seniority": enrichment.get("seniority"),
        "experience_years": enrichment.get("experience_years"),
        "employment_type": enrichment.get("employment_type"),
        "responsibilities": enrichment.get("responsibilities", []),
        "requirements": enrichment.get("requirements", []),
        "summary": enrichment.get("summary"),
    }


def save_job_ai_enrichment(
    job_id,
    enrichment,
    model=None,
    status="completed",
    enriched_at=None,
):
    values = _enrichment_values(enrichment)
    conn = None
    cursor = None
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO job_ai_enrichment (
                job_id, skills, category, seniority, experience_years, employment_type,
                responsibilities, requirements, summary, model, status,
                enriched_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (job_id)
            DO UPDATE SET
                skills = EXCLUDED.skills,
                category = EXCLUDED.category,
                seniority = EXCLUDED.seniority,
                experience_years = EXCLUDED.experience_years,
                employment_type = EXCLUDED.employment_type,
                responsibilities = EXCLUDED.responsibilities,
                requirements = EXCLUDED.requirements,
                summary = EXCLUDED.summary,
                model = EXCLUDED.model,
                status = EXCLUDED.status,
                enriched_at = EXCLUDED.enriched_at,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                job_id,
                Json(values["skills"]),
                values["category"],
                values["seniority"],
                values["experience_years"],
                values["employment_type"],
                Json(values["responsibilities"]),
                Json(values["requirements"]),
                values["summary"],
                model or config.AI_MODEL,
                status,
                enriched_at,
            ),
        )
        conn.commit()
    except psycopg2.Error:
        if conn:
            conn.rollback()
        logger.exception("failed to save AI enrichment for job %s", job_id)
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_job_ai_enrichment(job_id):
    conn = None
    cursor = None
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT skills, category, seniority, experience_years, employment_type,
                   responsibilities, requirements, summary, model, status,
                   enriched_at, created_at, updated_at
            FROM job_ai_enrichment
            WHERE job_id = %s
            """,
            (job_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "job_id": job_id,
            "skills": row[0],
            "category": row[1],
            "seniority": row[2],
            "experience_years": row[3],
            "employment_type": row[4],
            "responsibilities": row[5],
            "requirements": row[6],
            "summary": row[7],
            "model": row[8],
            "status": row[9],
            "enriched_at": row[10],
            "created_at": row[11],
            "updated_at": row[12],
        }
    except psycopg2.Error:
        logger.exception("failed to retrieve AI enrichment for job %s", job_id)
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def save_resume_profile(profile: ResumeProfile) -> UUID:
    def serialize_items(items):
        return [item.model_dump() if hasattr(item, "model_dump") else item for item in items]

    resume_id = uuid4()
    conn = None
    cursor = None
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO resume_profiles (
                id, name, summary, skills, technologies, experience,
                education, projects
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(resume_id),
                profile.name,
                profile.summary,
                Json(profile.skills),
                Json(profile.technologies),
                Json(serialize_items(profile.experience)),
                Json(serialize_items(profile.education)),
                Json(serialize_items(profile.projects)),
            ),
        )
        conn.commit()
        return resume_id
    except psycopg2.Error:
        if conn:
            conn.rollback()
        logger.exception("failed to save resume profile")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _resume_jsonb_value(value):
    return json.loads(value) if isinstance(value, str) else value


def get_resume_profile(resume_id: UUID) -> ResumeProfile | None:
    from jobpulse.ai.resume import ResumeProfile

    conn = None
    cursor = None
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT name, summary, skills, technologies, experience,
                   education, projects
            FROM resume_profiles
            WHERE id = %s
            """,
            (str(resume_id),),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return ResumeProfile(
            name=row[0],
            summary=row[1],
            skills=_resume_jsonb_value(row[2]),
            technologies=_resume_jsonb_value(row[3]),
            experience=_resume_jsonb_value(row[4]),
            education=_resume_jsonb_value(row[5]),
            projects=_resume_jsonb_value(row[6]),
        )
    except psycopg2.Error:
        logger.exception("failed to retrieve resume profile %s", resume_id)
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_active_enriched_job_ids():
    """Return active jobs with completed enrichment and stored embeddings."""
    conn = None
    cursor = None
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT j.id
            FROM jobs j
            JOIN job_ai_enrichment ai ON ai.job_id = j.id
            JOIN job_embeddings e ON e.job_id = j.id
            WHERE j.is_active = TRUE
              AND ai.status = 'completed'
            ORDER BY j.id
            """
        )
        return [row[0] for row in cursor.fetchall()]
    except psycopg2.Error:
        logger.exception("failed to select eligible recommendation jobs")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def save_resume_embedding(resume_id: UUID, embedding, embedding_model=None):
    if not embedding:
        raise ValueError("embedding must contain at least one value")
    if not all(isinstance(value, (int, float)) for value in embedding):
        raise TypeError("embedding must contain only numeric values")

    vector = "[" + ",".join(str(value) for value in embedding) + "]"
    conn = None
    cursor = None
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO resume_embeddings (
                resume_id, embedding, embedding_model, dimensions
            )
            VALUES (%s, %s::vector, %s, %s)
            ON CONFLICT (resume_id)
            DO UPDATE SET
                embedding = EXCLUDED.embedding,
                embedding_model = EXCLUDED.embedding_model,
                dimensions = EXCLUDED.dimensions,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                str(resume_id),
                vector,
                embedding_model or config.AI_EMBEDDING_MODEL,
                len(embedding),
            ),
        )
        conn.commit()
    except psycopg2.Error:
        if conn:
            conn.rollback()
        logger.exception("failed to save resume embedding for %s", resume_id)
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_resume_embedding(resume_id: UUID):
    conn = None
    cursor = None
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT embedding, embedding_model, dimensions, created_at, updated_at
            FROM resume_embeddings
            WHERE resume_id = %s
            """,
            (str(resume_id),),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        embedding = row[0]
        if isinstance(embedding, str):
            embedding = [
                float(value) for value in embedding.strip("[]").split(",")
            ]
        return {
            "resume_id": resume_id,
            "embedding": embedding,
            "embedding_model": row[1],
            "dimensions": row[2],
            "created_at": row[3],
            "updated_at": row[4],
        }
    except psycopg2.Error:
        logger.exception("failed to retrieve resume embedding for %s", resume_id)
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_jobs_for_enrichment_batch(limit, model=None):
    """Return active jobs with descriptions not completed by the given model."""
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer")

    configured_model = model or config.AI_MODEL
    conn = None
    cursor = None
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            f"""
                        SELECT j.id, j.title, j.company, j.location, j.posted_date, j.url,
                                     j.source, j.first_seen_at, j.last_seen_at, j.is_active,
                                     j.source_job_id, j.description, j.employment_type, j.salary,
                                     ai.status, ai.model
                        FROM jobs j
                        LEFT JOIN job_ai_enrichment ai ON ai.job_id = j.id
                        WHERE j.is_active = TRUE
                            AND j.description IS NOT NULL
                            AND BTRIM(j.description) <> ''
              AND NOT (
                  ai.status = 'completed'
                  AND ai.model = %s
              )
                        ORDER BY j.id
            LIMIT %s
            """,
            (configured_model, limit),
        )
        records = []
        for row in cursor.fetchall():
            job = Job.from_row(row[1:14])
            job.id = row[0]
            records.append({"job": job, "status": row[14], "model": row[15]})
        return records
    except psycopg2.Error:
        logger.exception("failed to select jobs for AI enrichment")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_jobs_for_embedding_batch(limit):
    """Return active jobs with non-empty descriptions and embedding state."""
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer")

    conn = None
    cursor = None
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT j.id, j.title, j.company, j.location, j.posted_date, j.url,
                   j.source, j.first_seen_at, j.last_seen_at, j.is_active,
                   j.source_job_id, j.description, j.employment_type, j.salary,
                   e.job_id
            FROM jobs j
            LEFT JOIN job_embeddings e ON e.job_id = j.id
            WHERE j.is_active = TRUE
              AND j.description IS NOT NULL
              AND BTRIM(j.description) <> ''
            ORDER BY j.id
            LIMIT %s
            """,
            (limit,),
        )
        records = []
        for row in cursor.fetchall():
            job = Job.from_row(row[1:14])
            job.id = row[0]
            records.append({"job": job, "has_embedding": row[14] is not None})
        return records
    except psycopg2.Error:
        logger.exception("failed to select jobs for embedding")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def save_job_embedding(job_id, embedding, embedding_model=None):
    if not embedding:
        raise ValueError("embedding must contain at least one value")
    if not all(isinstance(value, (int, float)) for value in embedding):
        raise TypeError("embedding must contain only numeric values")

    vector = "[" + ",".join(str(value) for value in embedding) + "]"
    conn = None
    cursor = None
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO job_embeddings (
                job_id, embedding, embedding_model, dimensions
            )
            VALUES (%s, %s::vector, %s, %s)
            ON CONFLICT (job_id)
            DO UPDATE SET
                embedding = EXCLUDED.embedding,
                embedding_model = EXCLUDED.embedding_model,
                dimensions = EXCLUDED.dimensions,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                job_id,
                vector,
                embedding_model or config.AI_EMBEDDING_MODEL,
                len(embedding),
            ),
        )
        conn.commit()
    except psycopg2.Error:
        if conn:
            conn.rollback()
        logger.exception("failed to save embedding for job %s", job_id)
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_job_embedding(job_id):
    conn = None
    cursor = None
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT embedding, embedding_model, dimensions, created_at, updated_at
            FROM job_embeddings
            WHERE job_id = %s
            """,
            (job_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        embedding = row[0]
        if isinstance(embedding, str):
            embedding = [float(value) for value in embedding.strip("[]").split(",")]
        return {
            "job_id": job_id,
            "embedding": embedding,
            "embedding_model": row[1],
            "dimensions": row[2],
            "created_at": row[3],
            "updated_at": row[4],
        }
    except psycopg2.Error:
        logger.exception("failed to retrieve embedding for job %s", job_id)
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def search_jobs_by_embedding(embedding, top_k=10):
    if not embedding:
        raise ValueError("embedding must contain at least one value")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    if not all(isinstance(value, (int, float)) for value in embedding):
        raise TypeError("embedding must contain only numeric values")

    vector = "[" + ",".join(str(value) for value in embedding) + "]"
    conn = None
    cursor = None
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT {JOB_COLUMNS},
                   job_embeddings.embedding <=> %s::vector AS distance
            FROM jobs
            JOIN job_embeddings ON job_embeddings.job_id = jobs.id
            WHERE jobs.is_active = TRUE
            ORDER BY distance ASC
            LIMIT %s
            """,
            (vector, top_k),
        )
        results = []
        for row in cursor.fetchall():
            distance = float(row[-1])
            results.append(
                {
                    "job": Job.from_row(row[:-1]),
                    "distance": distance,
                    "similarity": 1.0 - distance,
                }
            )
        return results
    except psycopg2.Error:
        logger.exception("failed to search jobs by embedding")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _fetch_jobs(query, params=()):
    conn = None
    cursor = None
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [Job.from_row(row) for row in cursor.fetchall()]
    except psycopg2.Error:
        logger.exception("failed to fetch jobs")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_all_jobs():
    return _fetch_jobs(
        f"SELECT {JOB_COLUMNS} FROM jobs WHERE is_active = TRUE ORDER BY posted_date DESC"
    )


def get_jobs_by_url(url):
    jobs = _fetch_jobs(
        f"SELECT {JOB_COLUMNS} FROM jobs WHERE url = %s AND is_active = TRUE",
        (url,),
    )
    return jobs[0] if jobs else None


def get_jobs_by_company(company):
    return _fetch_jobs(
        f"""SELECT {JOB_COLUMNS} FROM jobs
            WHERE company ILIKE %s AND is_active = TRUE
            ORDER BY posted_date DESC""",
        (f"%{company}%",),
    )


def get_jobs_by_location(location):
    return _fetch_jobs(
        f"""SELECT {JOB_COLUMNS} FROM jobs
            WHERE location ILIKE %s AND is_active = TRUE
            ORDER BY posted_date DESC""",
        (f"%{location}%",),
    )


def get_recent_jobs(days):
    return _fetch_jobs(
        f"""SELECT {JOB_COLUMNS} FROM jobs
            WHERE posted_date >= CURRENT_DATE - (%s * INTERVAL '1 day')
              AND is_active = TRUE
            ORDER BY posted_date DESC""",
        (days,),
    )


def get_job_by_id(job_id):
    jobs = _fetch_jobs(
        f"SELECT {JOB_COLUMNS} FROM jobs WHERE id = %s AND is_active = TRUE",
        (job_id,),
    )
    return jobs[0] if jobs else None


def get_jobs_by_filter(job_location=None, company=None):
    if job_location and company:
        return _fetch_jobs(
            f"""SELECT {JOB_COLUMNS} FROM jobs
                WHERE location ILIKE %s AND company ILIKE %s
                  AND is_active = TRUE
                ORDER BY posted_date DESC""",
            (f"%{job_location}%", f"%{company}%"),
        )
    if job_location:
        return get_jobs_by_location(job_location)
    if company:
        return get_jobs_by_company(company)
    return get_all_jobs()
