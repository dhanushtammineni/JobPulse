-- Support conservative cross-provider candidate lookup on the exact normalized fields.
CREATE INDEX jobs_duplicate_lookup_idx ON jobs
 (lower(btrim(company)), lower(btrim(title)), lower(btrim(location))) WHERE is_active;
