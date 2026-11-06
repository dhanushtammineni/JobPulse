-- Preserve provider categories and other non-normalized public posting fields.
ALTER TABLE jobs ADD COLUMN source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
