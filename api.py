from uuid import UUID
from contextlib import asynccontextmanager

from fastapi import FastAPI,HTTPException,status
from jobpulse.ai.matching import MatchError, MatchResult, match_resume_to_job
from jobpulse.ai.search import semantic_search
from jobpulse.database.repository import ensure_job_freshness_schema,get_job_by_id,get_jobs_by_filter
from jobpulse.utils.logger import logger
from jobpulse.database.migrate import MigrationError, assert_current
from jobpulse.database.connections import psycopg2

@asynccontextmanager
async def lifespan(app):
    ensure_job_freshness_schema()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health/live")
def liveness():
    return {"status": "ok"}


@app.get("/health/ready")
def readiness():
    try:
        assert_current()
    except (MigrationError, psycopg2.Error, ValueError):
        raise HTTPException(status_code=503, detail="Database is not ready") from None
    return {"status": "ready"}


@app.get("/jobs")
def get_jobs(company: str | None = None,location:str |None=None):

    jobs=get_jobs_by_filter(location,company)
    if not jobs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No jobs found"
        )
    return [job.to_dict() for job in jobs]

@app.get("/jobs/semantic-search")
def search_jobs(q: str, top_k: int = 10):
    if not q.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'q' must not be blank",
        )
    if top_k < 1 or top_k > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="top_k must be between 1 and 50",
        )

    try:
        matches = semantic_search(q, top_k=top_k)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except Exception as error:
        logger.exception("semantic job search failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Semantic search is temporarily unavailable",
        ) from error

    return {
        "query": q,
        "results": [
            {
                "job": result["job"].to_dict(),
                "distance": result["distance"],
                "similarity": result["similarity"],
            }
            for result in matches
        ],
    }


@app.get("/resumes/{resume_id}/match/{job_id}", response_model=MatchResult)
def match_resume(resume_id: UUID, job_id: int):
    try:
        return match_resume_to_job(resume_id, job_id)
    except MatchError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume, job, or matching data not found",
        ) from error
    except Exception as error:
        logger.exception("resume-to-job matching failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Resume-to-job matching is temporarily unavailable",
        ) from error

@app.get("/jobs/{job_id}")
def get_job(job_id:int):
    job=get_job_by_id(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail="job not found"
        )
    return job.to_dict()
