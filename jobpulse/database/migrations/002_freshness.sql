ALTER TABLE jobs ADD COLUMN IF NOT EXISTS source VARCHAR(100);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMP;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_active BOOLEAN;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS source_job_id VARCHAR(255);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS employment_type VARCHAR(100);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS salary VARCHAR(255);

-- Repair nulls even when an earlier manual setup already added the columns.
UPDATE jobs SET source = 'python.org' WHERE source IS NULL;
UPDATE jobs SET first_seen_at = COALESCE(created_timestamp, CURRENT_TIMESTAMP)
    WHERE first_seen_at IS NULL;
UPDATE jobs SET last_seen_at = COALESCE(created_timestamp, CURRENT_TIMESTAMP)
    WHERE last_seen_at IS NULL;
UPDATE jobs SET is_active = TRUE WHERE is_active IS NULL;
ALTER TABLE jobs ALTER COLUMN source SET DEFAULT 'python.org';
ALTER TABLE jobs ALTER COLUMN source SET NOT NULL;
ALTER TABLE jobs ALTER COLUMN first_seen_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE jobs ALTER COLUMN first_seen_at SET NOT NULL;
ALTER TABLE jobs ALTER COLUMN last_seen_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE jobs ALTER COLUMN last_seen_at SET NOT NULL;
ALTER TABLE jobs ALTER COLUMN is_active SET DEFAULT TRUE;
ALTER TABLE jobs ALTER COLUMN is_active SET NOT NULL;
CREATE INDEX IF NOT EXISTS jobs_active_source_idx ON jobs (source, is_active);
