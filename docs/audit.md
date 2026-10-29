# Baseline audit and PR 1 scope

Inspected main at `20fb0d2b922d3a0bd4d1e0741ae0ceb834564534` on 29 October 2026.
`git fetch origin main` confirmed that the supplied checkout matched main.

## Existing parallel work

Git advertises PR #1 (`refs/pull/1/head`), branch `fix/batch-selection`, commit
`8f28077b073b1672f83c51c4b2218700570a632b`. Its diff fixes NULL-safe AI batch
eligibility and embedding-model batch selection and adds PostgreSQL tests.
This change deliberately leaves those queries and batch processing unchanged.
GitHub GraphQL access returned Forbidden in the development environment, so PR
state, review comments, and approval status could not be verified through the API.
Recheck them on GitHub before merging; do not replace that work.

## Findings against the requested platform

| Area | Baseline evidence | Disposition |
| --- | --- | --- |
| Schema | `repository.py` assumes `jobs` already exists, creates AI tables and alters freshness columns repeatedly | PR 1 adds explicit migrations and removes DDL from repository operations |
| Runtime | requirements omit dotenv, FastAPI, uvicorn and test dependencies; Docker starts ingestion, no Compose setup | PR 1 adds hashed locks, API image and ordered database/migration/API startup |
| Configuration | database values can be absent or malformed until psycopg connects | PR 1 validates on connection without requiring secrets for imports or unit tests |
| Resume security | profile/embedding stores have no user ownership; match route accepts arbitrary resume UUID | PR 2; do not expose this baseline to untrusted users or upload private resumes |
| Sources | only Python.org ingestion exists | PR 3; configurable public board adapters remain unimplemented |
| Changed listings | upserts overwrite optional fields and do not invalidate enrichment or embeddings | PR 4; preserve scope and existing PR batch fixes |
| Discovery and metrics | unpaginated jobs endpoints; no pipeline run metrics or recommendation API | PR 5 |
| Frontend | job browsing exists; analytics are placeholders; no resume/recommendation UI | PR 6 |
| Assistant | no RAG retrieval/chat endpoint | PR 7 |
| Orchestration | Kafka broker/topics hardcoded; consumer starts on import; Airflow DAG exists under `jobpulse/dags` | PR 8 |
| Delivery | no CI workflow, browser tests or production release pipeline | PR 9; PR 1 only establishes the local runtime foundation |

The Python.org parser, freshness logic, AI enrichment/embedding boundaries, resume
extraction, deterministic matching and recommendation functions already exist.
They are extended in later PRs, not replaced by this migration change.

At this scale there is no demonstrated distributed batch workload requiring
PySpark. Python source adapters and PostgreSQL SQL are sufficient for the current
pipeline; measure volumes and batch latency before introducing another runtime.

## PR 1 acceptance checks

- Clean PostgreSQL 17 + pgvector migration, repeated upgrade and revision check.
- Adoption of legacy jobs, partial freshness columns and existing AI artifacts.
- Transaction rollback on SQL failure, checksum drift rejection, newer-release
  rejection, duplicate-URL failure without deleting records, concurrent migrators.
- Real job upsert, enrichment/embedding and synthetic resume persistence round trips.
- Read-only startup and API reads; readiness returns 503 without connection details.
- Existing unit tests, hashed dependency install, image build and Compose startup.

Tests use explicitly labeled synthetic fixtures in randomly named disposable
databases. No real job ingestion, Gemini calls, private resumes or fabricated
production analytics are part of this PR's validation.

## Validation recorded for this change

On the managed Linux development instance (Python 3.12, Node 24, PostgreSQL 17
with pgvector), all 103 tests passed, including 10 PostgreSQL integration tests
and 11 unittest subtests. The test run reported six deprecation warnings from
existing AI code and the upstream test client. Hashed dependency installation,
`pip check`, and the Vite production build passed. The digest-pinned Docker image
built successfully with CA verification enabled and ran as UID 10001. Compose
passed health checks on a clean volume and a repeated startup; the migration
service reported three applied migrations on the first run and none on the
second. The empty jobs endpoint correctly returned 404 without seeded listings.

No live Gemini calls or external ingestion were run. No staging or production
release was attempted. GitHub PR creation/review remains subject to API access;
Git fetch access alone does not establish API access.
