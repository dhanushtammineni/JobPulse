# JobPulse

## Batch-selection regression tests

Run the suite with `python -m pytest -q`. PostgreSQL integration tests skip
unless `JOBPULSE_TEST_POSTGRES_DSN` is set; an explicitly configured connection
that fails is reported as a test failure. No Gemini credentials are needed.

For example, against a disposable PostgreSQL instance:

```sh
export JOBPULSE_TEST_POSTGRES_DSN='host=127.0.0.1 port=5432 dbname=jobpulse_test user=jobpulse'
python -m pytest -q tests/test_batch_selection_postgres.py
```

Use a test database, never production. The tests create session-local temporary
tables and roll back on cleanup; no application schema or existing records are
modified. Plain PostgreSQL is sufficient for these selection-only tests: vectors
and AI persistence are controlled fixtures, and no pgvector distance operators
are exercised. The environment needs pytest plus the repository dependencies
and the existing API test dependencies (FastAPI, httpx, and python-dotenv).

## Ingestion freshness

JobPulse currently uses the Python.org HTML job board at `https://www.python.org/jobs/` as its authoritative source. The parser reads the canonical listing `href` values and resolves them with `urljoin`; it does not construct job URLs from titles or IDs.

Python.org also publishes `https://www.python.org/jobs/feed/rss/`. The RSS feed returns canonical links and stable GUIDs, but currently contains fewer items than the HTML board and does not provide `posted_date` as a structured field. HTML remains the primary source so the existing model continues to receive the complete listing fields. RSS is a possible future change-detection supplement, not a replacement chosen blindly.

Each complete ingestion run upserts by canonical URL and updates `last_seen_at`. Existing records receive these fields:

- `source`: source name, currently `python.org`
- `first_seen_at`: first successful observation
- `last_seen_at`: most recent successful observation
- `is_active`: whether the record is currently eligible for API results

Listings missing from a successful run are retained as history. They are marked inactive after seven days without being observed; they are not deleted. Kafka consumer events use the same upsert path but do not perform a whole-source stale sweep.

Run one ingestion pass with:

```powershell
python main.py
```

Start the API with:

```powershell
python -m uvicorn api:app --reload --port 8000
```

## Airflow orchestration

The DAG is [dags/jobpulse_ingestion.py](dags/jobpulse_ingestion.py), with ID `jobpulse_ingestion`. It runs hourly by default using `0 * * * *`, with catchup disabled and one active DAG run at a time. The schedule and retry settings are configurable through environment variables:

- `JOBPULSE_AIRFLOW_SCHEDULE` (default: `0 * * * *`)
- `JOBPULSE_AIRFLOW_RETRIES` (default: `2`)
- `JOBPULSE_AIRFLOW_RETRY_DELAY_MINUTES` (default: `5`)

The DAG only orchestrates the existing `jobpulse.ingestion.pipeline.run_ingestion` function. It does not contain scraper or database logic. The ingestion function fails on an empty or invalid source response before calling the database, so a failed fetch cannot mark jobs stale.

For a local Airflow installation, make the repository importable by the scheduler and webserver, and expose the existing database variables (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`) to the Airflow worker environment. Do not put credentials in the DAG file. Then point Airflow at the repository's `dags` directory:

```powershell
$env:AIRFLOW_HOME = "$PWD\.airflow"
$env:AIRFLOW__CORE__DAGS_FOLDER = "$PWD\dags"
$env:PYTHONPATH = "$PWD"
airflow db migrate
airflow users create --username admin --firstname Job --lastname Pulse --role Admin --email admin@example.com
airflow scheduler
airflow webserver --port 8080
```

Trigger it manually from the Airflow UI or CLI:

```powershell
airflow dags trigger jobpulse_ingestion
```

The `start`, `ingest_jobs`, and `finish` tasks expose the run boundary in the Airflow UI. The ingestion task logs fetched, inserted, updated, and stale counts; exceptions propagate to Airflow so retries and failed task state remain visible.
