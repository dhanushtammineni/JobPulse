-- Adopt the existing AI tables without deleting stored artifacts.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS job_ai_enrichment (
            job_id BIGINT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
            skills JSONB NOT NULL DEFAULT '[]'::jsonb,
            category VARCHAR(255),
            seniority VARCHAR(100),
            experience_years INTEGER,
            employment_type VARCHAR(100),
            responsibilities JSONB NOT NULL DEFAULT '[]'::jsonb,
            requirements JSONB NOT NULL DEFAULT '[]'::jsonb,
            summary TEXT,
            model VARCHAR(255),
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            enriched_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

ALTER TABLE job_ai_enrichment ADD COLUMN IF NOT EXISTS experience_years INTEGER;

CREATE TABLE IF NOT EXISTS job_embeddings (
            job_id BIGINT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
            embedding vector NOT NULL,
            embedding_model VARCHAR(255) NOT NULL,
            dimensions INTEGER NOT NULL CHECK (dimensions > 0),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

CREATE TABLE IF NOT EXISTS resume_profiles (
            id UUID PRIMARY KEY,
            name TEXT,
            summary TEXT,
            skills JSONB NOT NULL,
            technologies JSONB NOT NULL,
            experience JSONB NOT NULL,
            education JSONB NOT NULL,
            projects JSONB NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );

CREATE TABLE IF NOT EXISTS resume_embeddings (
            resume_id UUID PRIMARY KEY REFERENCES resume_profiles(id) ON DELETE CASCADE,
            embedding vector NOT NULL,
            embedding_model TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );

CREATE INDEX IF NOT EXISTS job_ai_enrichment_status_idx
        ON job_ai_enrichment (status);

CREATE INDEX IF NOT EXISTS job_ai_enrichment_model_idx
        ON job_ai_enrichment (model);

CREATE INDEX IF NOT EXISTS job_embeddings_model_idx
        ON job_embeddings (embedding_model);
