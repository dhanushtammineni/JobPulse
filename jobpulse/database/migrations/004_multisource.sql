-- Forward-only extension of 001..003. Existing IDs and AI foreign keys remain intact.
ALTER TABLE jobs ALTER COLUMN company DROP NOT NULL;
ALTER TABLE jobs ALTER COLUMN location DROP NOT NULL;
ALTER TABLE jobs ALTER COLUMN posted_date DROP NOT NULL;
ALTER TABLE jobs ADD COLUMN source_board TEXT NOT NULL DEFAULT '';
ALTER TABLE jobs ADD COLUMN apply_url TEXT;
ALTER TABLE jobs ADD COLUMN salary_currency TEXT;
ALTER TABLE jobs ADD COLUMN workplace_type TEXT;
ALTER TABLE jobs ADD COLUMN content_hash CHAR(64);
ALTER TABLE jobs ADD COLUMN semantic_revision BIGINT NOT NULL DEFAULT 0;

-- Replace legacy global URL uniqueness with provider-board-scoped uniqueness.
-- Drop only constraints/indexes whose sole key is jobs.url, not unrelated indexes.
DO $$
DECLARE item RECORD; url_att SMALLINT;
BEGIN
 SELECT attnum INTO url_att FROM pg_attribute WHERE attrelid='jobs'::regclass AND attname='url';
 FOR item IN SELECT conname FROM pg_constraint WHERE conrelid='jobs'::regclass
             AND contype='u' AND conkey=ARRAY[url_att] LOOP
  EXECUTE format('ALTER TABLE jobs DROP CONSTRAINT %I', item.conname);
 END LOOP;
 FOR item IN SELECT i.indexrelid::regclass AS name FROM pg_index i
             WHERE i.indrelid='jobs'::regclass AND i.indisunique AND NOT i.indisprimary
             AND i.indnkeyatts=1 AND i.indkey[0]=url_att LOOP
  EXECUTE format('DROP INDEX %s', item.name);
 END LOOP;
END $$;
UPDATE jobs SET source_job_id=COALESCE(substring(url FROM '/jobs/([0-9]+)/'),url)
 WHERE source='python.org' AND source_job_id IS NULL;
-- Duplicate pre-existing identities fail migration atomically; never discard records.
CREATE UNIQUE INDEX jobs_source_identity_idx ON jobs(source, source_board, source_job_id)
 WHERE source_job_id IS NOT NULL;
CREATE UNIQUE INDEX jobs_source_url_idx ON jobs(source, source_board, url);
CREATE INDEX jobs_last_seen_idx ON jobs(source, source_board, last_seen_at);
CREATE INDEX jobs_active_posted_idx ON jobs(posted_date DESC NULLS LAST, id DESC) WHERE is_active;
CREATE INDEX jobs_company_filter_idx ON jobs(lower(company)) WHERE is_active;
CREATE INDEX jobs_workplace_filter_idx ON jobs(workplace_type, employment_type) WHERE is_active;
ALTER TABLE job_embeddings ADD COLUMN is_stale BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE ingestion_runs (
 id UUID PRIMARY KEY, source TEXT NOT NULL, source_board TEXT NOT NULL,
 started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TIMESTAMPTZ,
 status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed')),
 fetched INTEGER NOT NULL DEFAULT 0, inserted INTEGER NOT NULL DEFAULT 0,
 updated INTEGER NOT NULL DEFAULT 0, unchanged INTEGER NOT NULL DEFAULT 0,
 failed INTEGER NOT NULL DEFAULT 0, stale INTEGER NOT NULL DEFAULT 0, error_type TEXT
);
CREATE INDEX ingestion_runs_board_idx ON ingestion_runs(source,source_board,started_at DESC);
CREATE TABLE job_duplicate_candidates (
 job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 candidate_job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 reason TEXT NOT NULL, detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 review_status TEXT NOT NULL DEFAULT 'pending',
 PRIMARY KEY(job_id,candidate_job_id), CHECK(job_id < candidate_job_id)
);
