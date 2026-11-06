# Multi-source implementation and verification — 6 November 2026

Implementation is available for review, but the complete definition of done is **blocked by external network access**. No production-readiness or successful live-ingestion claim is made.

## Branch audit and dependencies

- Feature branch: `feat/multisource-ingestion-no-kafka`.
- Latest main was checked again before publication: `20fb0d2b922d3a0bd4d1e0741ae0ceb834564534`.
- Open PR #1 (`8f28077`) contains AI batch eligibility/progress fixes; open PR #2 (`fb2a91e`) contains versioned migrations and runtime setup. Both existing commits are preserved on this feature branch rather than duplicated. The README merge conflict was resolved by retaining their documentation before rewriting it around the completed implementation.
- Main has not been merged into or changed remotely by this work. Migrations `001_jobs.sql`, `002_freshness.sql`, and `003_ai.sql` match PR #2 byte-for-byte.
- New migrations: `004_multisource.sql`, `005_duplicate_lookup.sql`, `006_source_metadata.sql`. Existing IDs, job rows, AI artifacts, resume records and foreign keys are preserved. Conflicting legacy identities fail transactionally for operator review.

## Verified results

| Check | Actual result |
| --- | --- |
| Locked application environment, full backend suite with both PostgreSQL opt-ins | **131 passed, 11 subtests passed**; 3 optional Airflow tests skipped in this environment |
| Real PostgreSQL integration coverage | 17 tests included in the passing suite; random databases cleaned up |
| Real Airflow 2.11 runtime tests | **3 passed**, separately covering the 3 skipped tests |
| Airflow scheduler DagBag discovery from `dags/` | `jobpulse_ingestion` discovered; no import errors |
| Frontend Node rendering/request tests | **2 passed**; all four sources rendered with attribution, escaped descriptions and external application links |
| Production frontend build | Passed with Vite 8.3.6 |
| Dependency consistency | `pip check` passed in application and optional Airflow environments |
| Frontend dependency audit | **0 vulnerabilities** after compatible patches to the inherited Vite/transitive lock |
| API Docker build | Passed; pinned Python image, hash-verified lock, non-root runtime |
| Frontend Docker build | Passed; pinned Node/Nginx image digests, `npm ci`, TLS verification retained |
| Compose startup / migration ordering | Database healthy; migrations complete; API healthy; Nginx frontend started |
| Compose functional checks | All six migrations current; removed broker module absent; all four synthetic source imports idempotent; Nginx-proxied source filters and job details returned expected database data; public-facing local port returned HTML and readiness JSON |
| Reusable local development helper | Repeated startup applied only pending migrations; current API starts successfully |

The backend regression suite verifies stable IDs with changed URLs, field updates/hashes, missing-value preservation, unchanged-job behavior, first-seen preservation, scoped freshness, incomplete/failing boards, conservative duplicate candidates, retained/stale AI artifacts, revision guards against obsolete AI writes, metadata merging, filtering, migration adoption/rollback and concurrent migration serialization. The validation harness itself is tested with mocked providers and real PostgreSQL: 25 fetched/20 sampled/20 inserted/20 unchanged on repeat/1 deliberate update/5 unsampled per source, and its original database remains untouched. Those are synthetic test results, **not live board results**.

No live Gemini calls were made. Existing deprecation warnings concern Starlette's HTTPX TestClient compatibility, `datetime.utcnow`, and Airflow 3 migration guidance; they did not fail tests. Airflow scheduler execution against real external providers and paid AI calls were not run.

## Authorized live validation

The operator selected Stripe (Greenhouse), Palantir (Lever US/global), Ramp (Ashby) and Python.org. The validator attempted the exact public endpoints in a random disposable PostgreSQL database with a 20-job import limit. Every request was denied by the configured proxy before a valid source response could be obtained. It did not bypass policy, import sample stand-ins, call Gemini, or touch the existing JobPulse database. The disposable databases were removed.

| Source / board | Fetched | Inserted | Updated | Skipped | Failed runs | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Python.org | 0 | 0 | 0 | 0 | 1 | Proxy HTTP 403 |
| Greenhouse / stripe | 0 | 0 | 0 | 0 | 1 | Proxy HTTP 403 |
| Lever / palantir (US/global) | 0 | 0 | 0 | 0 | 1 | Proxy HTTP 403 |
| Ashby / ramp | 0 | 0 | 0 | 0 | 1 | Proxy HTTP 403 |

The official Lever API repository documentation was read successfully. The official Greenhouse and Ashby documentation hosts are blocked too; their final contract/sample verification remains outstanding. The adapters and deterministic fixture coverage must not be presented as successful live contract verification.

Saved environment-draft additions (not yet applied to the running policy): `www.python.org`, `boards-api.greenhouse.io`, `api.lever.co`, `api.eu.lever.co`, `api.ashbyhq.com`, `developers.greenhouse.io`, `developers.ashbyhq.com`, and `api.github.com`. User-selected source/board JSON settings, pacing, disabled-by-default AI settings, and refreshed installation/start instructions were also saved. Draft saving does not apply network access or publish the environment. Review and save the environment settings, then publish when appropriate; recheck source and GitHub access after the configuration is applied.

## Remaining external checks

1. Apply the saved network settings; re-read official Greenhouse and Ashby contracts and verify field fixtures against them.
2. Rerun `scripts/validate_public_sources.py --limit 20` against the authorized public boards. Confirm all requested per-source counts, normalization and repeated-upsert checks using real public responses. If a board itself refuses access or its applicable terms disallow this use, report that instead of bypassing it.
3. Complete GitHub PR creation if API access remains blocked. The feature branch can use the existing authenticated Git proxy; GitHub REST/GraphQL requests currently return Forbidden. Do not request a new token solely because the API route is blocked.
4. Review the two existing PR dependencies, API response contract change (`/jobs` array → paginated envelope; empty results now HTTP 200), and migrations before merge. No automatic merge is authorized or performed.

## Publication result

The feature branch was successfully pushed to GitHub. Creating the requested draft PR with `gh pr create --draft --base main` returned `Post https://api.github.com/graphql: Forbidden`. No PR was created and nothing was merged. The complete prepared description is saved in [pull-request.md](pull-request.md); retry after API access is restored. GitHub supplied this branch-specific creation link: https://github.com/dhanushtammineni/JobPulse/pull/new/feat/multisource-ingestion-no-kafka .

The isolated Compose test stack and its own disposable database volume were removed after functional validation. The existing JobPulse development database and its volume were retained.

## File manifest

Paths below compare the final feature worktree to audited main and include the retained PR #1/#2 dependency files. `A` means added, `M` modified, and `D` removed.

| Status | File |
| --- | --- |
| A | `.dockerignore` |
| A | `.env.example` |
| A | `.gitattributes` |
| M | `.gitignore` |
| M | `Dockerfile` |
| M | `README.md` |
| M | `api.py` |
| A | `compose.yaml` |
| M | `config.py` |
| A | `dags/jobpulse_ingestion.py` |
| A | `docs/audit.md` |
| A | `docs/multisource-validation.md` |
| A | `docs/pull-request.md` |
| A | `docs/runtime.md` |
| A | `frontend/.dockerignore` |
| A | `frontend/Dockerfile` |
| A | `frontend/nginx.conf` |
| M | `frontend/package-lock.json` |
| M | `frontend/package.json` |
| M | `frontend/src/App.jsx` |
| M | `frontend/src/components/JobCard.jsx` |
| M | `frontend/src/components/JobDetails.jsx` |
| M | `frontend/src/components/SearchFilters.jsx` |
| M | `frontend/src/index.css` |
| M | `frontend/src/services/api.js` |
| A | `frontend/tests/multisource.test.mjs` |
| M | `jobpulse/ai/batch_embeddings.py` |
| M | `jobpulse/ai/embeddings.py` |
| M | `jobpulse/ai/enrichment.py` |
| M | `jobpulse/ai/matching.py` |
| M | `jobpulse/dags/jobpulse_ingestion.py` |
| M | `jobpulse/database/connections.py` |
| A | `jobpulse/database/ingestion.py` |
| A | `jobpulse/database/listings.py` |
| A | `jobpulse/database/migrate.py` |
| A | `jobpulse/database/migrations/001_jobs.sql` |
| A | `jobpulse/database/migrations/002_freshness.sql` |
| A | `jobpulse/database/migrations/003_ai.sql` |
| A | `jobpulse/database/migrations/004_multisource.sql` |
| A | `jobpulse/database/migrations/005_duplicate_lookup.sql` |
| A | `jobpulse/database/migrations/006_source_metadata.sql` |
| M | `jobpulse/database/repository.py` |
| M | `jobpulse/ingestion/fetch.py` |
| A | `jobpulse/ingestion/http.py` |
| M | `jobpulse/ingestion/models.py` |
| M | `jobpulse/ingestion/pipeline.py` |
| A | `jobpulse/ingestion/sources/__init__.py` |
| D | `jobpulse/messaging/__init__.py` |
| D | `jobpulse/messaging/consumer.py` |
| D | `jobpulse/messaging/producer.py` |
| M | `pytest.ini` |
| A | `requirements-airflow.lock` |
| A | `requirements-airflow.txt` |
| A | `requirements-dev.lock` |
| A | `requirements-dev.txt` |
| A | `requirements.lock` |
| M | `requirements.txt` |
| M | `scripts/smoke_resume.py` |
| A | `scripts/validate_public_sources.py` |
| D | `test_producer.py` |
| A | `tests/integration/conftest.py` |
| A | `tests/integration/test_migrations_postgres.py` |
| A | `tests/integration/test_multisource_postgres.py` |
| M | `tests/test_ai_repository.py` |
| A | `tests/test_airflow_dag.py` |
| M | `tests/test_batch_embeddings.py` |
| A | `tests/test_batch_selection_postgres.py` |
| D | `tests/test_kafka_producer_lazy.py` |
| A | `tests/test_multisource_api.py` |
| A | `tests/test_multisource_pipeline.py` |
| A | `tests/test_runtime_config.py` |
| A | `tests/test_source_adapters.py` |
