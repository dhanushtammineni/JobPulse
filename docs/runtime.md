# Runtime and migrations

## Local Docker workflow

Requires Docker Engine with Compose v2. Copy `.env.example` to `.env`, choose a
local database password, then run from the repository root:

```sh
cp .env.example .env
docker compose up --build -d
docker compose ps
docker compose logs migrate
curl --fail http://127.0.0.1:8000/health/ready
```

Compose starts PostgreSQL 17 with pgvector, waits for database health, runs the
one-shot migration service, then starts the non-root API. Ports are bound to
loopback. The default example password is for local development only. The named
volume persists data across `docker compose down`; never use `down -v` against
valuable data. If another local database occupies port 5432, set `DB_PORT=5433`.
`API_PORT` changes the host API port; Vite's existing proxy expects port 8000.

The application starts with an empty database: `/jobs` returns the existing 404
`No jobs found` response. No demo jobs or metrics are silently inserted. With
Python.org access enabled, populate real jobs explicitly:

```sh
docker compose run --rm api python main.py
```

Gemini is optional. The default Compose stack does not forward its key. Supply it
through your deployment's secret configuration only when running AI workflows.
Kafka and Airflow are not started by this PR's stack; their reliability work is
scheduled separately. This local foundation is not yet an authenticated public
production deployment.

## Native Python and frontend

Use Python 3.12 and Node 24 (the versions used for validation):

```sh
python -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
docker compose up -d db
.venv/bin/python -m jobpulse.database.migrate upgrade
.venv/bin/python -m jobpulse.database.migrate check
.venv/bin/python -m uvicorn api:app --reload --port 8000
```

On Windows use `.venv\Scripts\python.exe`. The configuration loads `.env`; exported
process settings take precedence. `DB_HOST`, `DB_NAME`, and `DB_USER` are required.
`DB_PORT` defaults to 5432, `DB_CONNECT_TIMEOUT` to 5 seconds (range 1–60), and
`DB_SSLMODE` to `prefer`. Use `verify-full` with your provider's CA configuration
for an external production database. Never commit credentials or disable TLS
verification to troubleshoot connectivity.

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Vite proxies `/api` to the API on port 8000. `npm run build` checks the frontend
production bundle; frontend hosting and public deployment are later PRs.

## Migration contract

```sh
python -m jobpulse.database.migrate upgrade
python -m jobpulse.database.migrate check
```

The small SQL runner uses the project's existing psycopg2 dependency. Numbered
SQL files are immutable after release. It records their SHA-256 checksums in
`public.schema_migrations`, requires the applied history to be an exact prefix
of this release, and serializes upgrades with a PostgreSQL advisory transaction
lock. All pending files and their history rows commit together or roll back
together. Lock waits are bounded to 30 seconds and SQL statements to 120 seconds.
Migration SQL must not contain transaction controls or operations requiring
execution outside a transaction (such as `CREATE INDEX CONCURRENTLY`). LF line
endings are enforced in Git so checksums match across operating systems.

001 establishes the base jobs table and URL uniqueness. 002 adds and backfills
freshness and rich listing fields. 003 adopts the existing AI and resume tables
and enables pgvector. Existing rows, IDs, first-seen values and AI artifacts are
preserved. Partial nullable freshness columns are backfilled only where null.
Legacy schemas must have the original base columns and compatible AI column
types. Unexpected schemas require inspection rather than destructive repair.
Duplicate legacy URLs fail the upgrade transaction; resolve them with an explicit,
reviewed data migration rather than deleting records automatically.

API startup checks the migration history and required tables; it never migrates.
Legacy `ensure_ai_schema` and `ensure_job_freshness_schema` imports remain as
read-only checks for older scripts. Repository reads/writes contain no runtime
DDL. Run migrations explicitly before ingestion, batch commands, Kafka consumers
or Airflow tasks. A missing migration yields a startup failure with a CLI hint.
`/health/live` checks the process; `/health/ready` checks DB access and schema and
returns 503 on failure without exposing connection details.

Use a separate privileged migration identity to install the vector extension and
apply DDL. An application role needs CONNECT, schema USAGE, table SELECT/INSERT/
UPDATE/DELETE and sequence USAGE, not CREATE or extension permissions. The local
Compose stack uses one development role for simplicity; split identities before
production. This PR does not implement authentication or resume ownership.

Before upgrading an existing deployment, take a database backup and test the
upgrade on a restored copy. There is deliberately no automatic destructive down
migration. Recover a failed upgrade by correcting its prerequisite and rerunning;
recover an incompatible completed release with a tested backup restore or a new
forward migration. Never edit recorded checksums or stamp a database as migrated.
For large legacy tables, plan a maintenance window for index creation/backfills.

## Tests

```sh
.venv/bin/python -m pytest -q tests --ignore=tests/integration
.venv/bin/python -m pip check
```

Integration tests need a disposable PostgreSQL/pgvector instance and a role with
CREATEDB. The explicit opt-in prevents accidentally running database-creating
checks against a normal deployment:

```sh
# DB_* point to the disposable PostgreSQL admin connection.
JOBPULSE_TEST_DATABASES=1 .venv/bin/python -m pytest -q tests/integration
```

Each test creates a random `jobpulse_test_*` database and drops only that database
on completion. Fixtures contain synthetic records under `example.test`, not
production job data or private resumes. Integration tests skip without the opt-in;
a skipped suite does not establish database readiness.

## Dependency updates and managed-cloud builds

`requirements.txt` and `requirements-dev.txt` declare direct dependencies. The
committed locks pin transitive versions and hashes. Regenerate intentionally with
`uv pip compile --python .venv/bin/python --generate-hashes requirements.txt -o
requirements.lock` and the equivalent command for `requirements-dev.txt`, then
rerun tests and builds. Normal installs use `pip --require-hashes` and `npm ci`.

The Dockerfile supports an optional CA build secret for managed proxies:

```sh
docker build --secret id=pip_ca,src=/etc/ssl/certs/ca-certificates.crt -t jobpulse:local .
docker compose up -d --no-build
```

Keep the platform's Docker proxy defaults. Networked containers need the current
session proxy/CA configuration if ingesting externally. Recreate networked
containers when session proxy credentials change. Never bake proxy credentials,
CA session files or real `.env` values into an image.
