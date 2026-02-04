-- Migration 018: Gemini Batch API job tracking
-- Tracks batch jobs submitted to Gemini Batch API (validation or extraction).

BEGIN;

CREATE TABLE IF NOT EXISTS gemini_batch_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gemini_job_name TEXT NOT NULL UNIQUE,
    job_type TEXT NOT NULL CHECK (job_type IN ('validation', 'extraction')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled', 'expired')),
    total_requests INT NOT NULL,
    completed_requests INT DEFAULT 0,
    failed_requests INT DEFAULT 0,
    source_job_id UUID,
    request_metadata JSONB,
    result_file_name TEXT,
    error_message TEXT,
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gemini_batch_jobs_status ON gemini_batch_jobs(status);
CREATE INDEX IF NOT EXISTS idx_gemini_batch_jobs_source_job_id ON gemini_batch_jobs(source_job_id);
CREATE INDEX IF NOT EXISTS idx_gemini_batch_jobs_job_type ON gemini_batch_jobs(job_type);

COMMENT ON TABLE gemini_batch_jobs IS 'Tracks Gemini Batch API jobs for validation and extraction (50% cost, ~24h turnaround)';

COMMIT;
