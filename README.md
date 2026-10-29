# JobPulse

A Python job ingestion and AI intelligence project built with FastAPI,
PostgreSQL/pgvector and React. Existing AI workflows include enrichment, semantic
search, resume extraction and deterministic matching. Public authentication,
additional sources and the complete AI frontend are planned work.

Start with the [runtime and migrations guide](docs/runtime.md) for Docker Compose,
native setup, schema upgrades and tests. The [baseline audit](docs/audit.md) records
existing features, gaps and the separate PR sequence. This change delivers the
migration/runtime foundation only; it is not a completed public deployment.

```mermaid
flowchart LR
    PythonOrg[Python.org] --> Ingestion[Python ingestion]
    Ingestion --> PostgreSQL[PostgreSQL 17 + pgvector]
    Migrations[Versioned SQL migrations] --> PostgreSQL
    PostgreSQL --> API[FastAPI]
    API --> React[React / Vite]
    Gemini[Gemini: optional AI workflows] --> PostgreSQL
```


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

The DAG is [jobpulse/dags/jobpulse_ingestion.py](jobpulse/dags/jobpulse_ingestion.py), with ID `jobpulse_ingestion`. It runs hourly by default using `0 * * * *`, with catchup disabled and one active DAG run at a time. The schedule and retry settings are configurable through environment variables:

- `JOBPULSE_AIRFLOW_SCHEDULE` (default: `0 * * * *`)
- `JOBPULSE_AIRFLOW_RETRIES` (default: `2`)
- `JOBPULSE_AIRFLOW_RETRY_DELAY_MINUTES` (default: `5`)

The DAG only orchestrates the existing `jobpulse.ingestion.pipeline.run_ingestion` function. It does not contain scraper or database logic. The ingestion function fails on an empty or invalid source response before calling the database, so a failed fetch cannot mark jobs stale.

For a local Airflow installation, make the repository importable by the scheduler and webserver, and expose the existing database variables (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`) to the Airflow worker environment. Do not put credentials in the DAG file. Then point Airflow at the repository's `jobpulse/dags` directory:

```powershell
$env:AIRFLOW_HOME = "$PWD\.airflow"
$env:AIRFLOW__CORE__DAGS_FOLDER = "$PWD\jobpulse\dags"
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
