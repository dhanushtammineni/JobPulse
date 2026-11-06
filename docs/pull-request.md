# Prepared draft PR description

Title: Replace Kafka with board-scoped multi-source job ingestion

JobPulse ingestion now uses Python.org and configurable public Greenhouse, Lever, and Ashby board adapters, with no broker dependency. Stable board/listing identities update existing rows when URLs change, preserve known fields and first-seen timestamps, and restrict stale sweeps to successful complete snapshots of the same board. Semantic changes retain but invalidate AI artifacts; revision guards reject obsolete AI results.

The API and React client now use bounded server pagination and source/keyword/location/company/employment/workplace filters, source attribution, recorded timestamps, and external application links. Airflow orchestrates isolated source tasks followed by validation and bounded optional AI batches. Docker Compose includes the frontend and migration ordering.

Dependencies and database compatibility:
- Based on audited main `20fb0d2`; preserves the existing commits under review in #1 (AI batch corrections) and #2 (migrations/runtime). Those commits are included here until they merge; their implementation and migration files were not recreated or overwritten.
- Original migrations 001–003 are unchanged. New migrations 004–006 add source identity/status, stale artifact tracking, duplicate-candidate lookup and provider metadata without deleting existing records or job foreign keys.
- `/jobs` changes from an unbounded array to `{items,total,page,page_size,ingestion}`; empty results return HTTP 200. The frontend is updated in the same branch.

Validation:
- Locked application environment: 131 tests passed, 11 subtests passed, including real PostgreSQL integration tests; 3 optional Airflow tests skipped there and all 3 passed separately in a real Airflow 2.11 runtime.
- Actual Airflow DagBag discovery passed; frontend rendering/request tests: 2 passed; production build passed; npm audit: 0 vulnerabilities after compatible inherited dependency patches.
- Both Docker images built with verification enabled. Compose migrations/readiness, four synthetic source imports repeated without duplicates, and Nginx-proxied filters/details passed in a disposable validation stack.
- No live Gemini calls. Existing application records were preserved.

External checks still blocked — keep this PR in draft:
- The operator-authorized Stripe, Palantir US/global, Ramp and Python.org live checks all returned proxy HTTP 403 before data could be fetched. Each source: fetched/inserted/updated/skipped=0, failed run=1. Disposable databases were removed. No successful live ingestion is claimed.
- Official Lever documentation was read; official Greenhouse/Ashby contract verification remains blocked by network policy.
- Required domains and the user-selected board settings are saved in the cloud environment draft but have not been applied. Apply them and rerun `scripts/validate_public_sources.py --limit 20`, which imports only a disposable 20-job sample per source and tests repeated upserts without AI.
- Applicable source/board redistribution terms still require review before production use.

See `docs/multisource-validation.md` for the file manifest, actual checks, limitations and remaining work. Do not merge automatically.
