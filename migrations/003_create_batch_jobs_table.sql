-- Migration: 003_create_batch_jobs_table.sql
-- Description: Create batch_jobs table for batch PDF processing
-- Created: 2026-01-28

-- Create enum type for batch job status
CREATE TYPE batch_status AS ENUM (
    'pending',
    'processing',
    'completed',
    'failed',
    'partial'
);

-- Create batch_jobs table
CREATE TABLE IF NOT EXISTS batch_jobs (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Job status and counts
    status batch_status NOT NULL DEFAULT 'pending',
    total_files INTEGER NOT NULL CHECK (total_files > 0 AND total_files <= 100),
    completed_files INTEGER NOT NULL DEFAULT 0 CHECK (completed_files >= 0),
    failed_files INTEGER NOT NULL DEFAULT 0 CHECK (failed_files >= 0),

    -- Routing statistics (JSONB for flexibility)
    -- Format: {"hybrid": count, "vision_fallback": count, "pending": count}
    routing_stats JSONB NOT NULL DEFAULT '{"hybrid": 0, "vision_fallback": 0, "pending": 0}'::jsonb,

    -- Array of extraction IDs
    extraction_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],

    -- Cost tracking
    cost_estimate_usd DECIMAL(10, 6) CHECK (cost_estimate_usd >= 0),
    cost_savings_usd DECIMAL(10, 6) CHECK (cost_savings_usd >= 0),

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    estimated_completion TIMESTAMPTZ,

    -- Webhook integration
    webhook_url TEXT,

    -- Constraints
    CONSTRAINT valid_counts CHECK (completed_files + failed_files <= total_files)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_batch_jobs_status ON batch_jobs(status);
CREATE INDEX IF NOT EXISTS idx_batch_jobs_created_at ON batch_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_batch_jobs_status_created_at ON batch_jobs(status, created_at DESC);

-- Add trigger to automatically update updated_at timestamp
CREATE TRIGGER update_batch_jobs_updated_at
    BEFORE UPDATE ON batch_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE batch_jobs IS 'Batch processing jobs for multiple PDF extractions';
COMMENT ON COLUMN batch_jobs.id IS 'Primary key UUID';
COMMENT ON COLUMN batch_jobs.status IS 'Job status: pending, processing, completed, failed, or partial';
COMMENT ON COLUMN batch_jobs.total_files IS 'Total number of files in batch (max 100)';
COMMENT ON COLUMN batch_jobs.completed_files IS 'Number of successfully completed extractions';
COMMENT ON COLUMN batch_jobs.failed_files IS 'Number of failed extractions';
COMMENT ON COLUMN batch_jobs.routing_stats IS 'Routing method distribution: {"hybrid": N, "vision_fallback": M, "pending": K}';
COMMENT ON COLUMN batch_jobs.extraction_ids IS 'Array of extraction UUIDs for this batch';
COMMENT ON COLUMN batch_jobs.cost_estimate_usd IS 'Total estimated API cost in USD';
COMMENT ON COLUMN batch_jobs.cost_savings_usd IS 'Total cost savings vs pure vision approach in USD';
COMMENT ON COLUMN batch_jobs.created_at IS 'Timestamp when batch job created';
COMMENT ON COLUMN batch_jobs.updated_at IS 'Timestamp of last update';
COMMENT ON COLUMN batch_jobs.estimated_completion IS 'Estimated completion timestamp';
COMMENT ON COLUMN batch_jobs.webhook_url IS 'Optional webhook URL for completion notifications';
