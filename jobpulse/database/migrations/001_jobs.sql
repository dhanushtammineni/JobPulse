-- Compatible with the original manually provisioned jobs table.
CREATE TABLE IF NOT EXISTS jobs (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT NOT NULL,
    posted_date DATE NOT NULL,
    url TEXT NOT NULL,
    created_timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS created_timestamp TIMESTAMP
    NOT NULL DEFAULT CURRENT_TIMESTAMP;
-- Fail transactionally on legacy duplicate URLs rather than deleting records.
CREATE UNIQUE INDEX IF NOT EXISTS jobs_url_unique_idx ON jobs (url);
