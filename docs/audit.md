# Repository dependency audit

The multi-source feature starts at main `20fb0d2` and preserves the existing open PR #1 (`8f28077`, NULL-safe AI batch selection) and PR #2 (`fb2a91e`, versioned migrations/runtime). Their branches were integrated into the feature branch, with a README-only conflict resolved by retaining both descriptions. Main was not merged or changed. Migrations 001–003 are unchanged.

The active implementation uses Python.org and three public posting APIs, PostgreSQL/pgvector, FastAPI, React, optional Airflow and optional Gemini. See the root README for the current architecture and docs/multisource-validation.md for verification. The earlier runtime audit is superseded by these implementation and validation records.
