-- Migration: 004_create_memo_extractions_table.sql
-- Description: Create memo_extractions table for storing marking guideline (memo) extraction results
-- Created: 2026-01-28

-- Create memo_extractions table (independent from extractions table)
CREATE TABLE IF NOT EXISTS memo_extractions (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- File metadata
    file_name TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes >= 0),
    file_hash TEXT NOT NULL,

    -- Processing status and method
    status extraction_status NOT NULL DEFAULT 'pending',
    processing_method processing_method_type,

    -- Quality score
    quality_score DECIMAL(4, 3) CHECK (quality_score >= 0.0 AND quality_score <= 1.0),

    -- Memo metadata (extracted from meta dict)
    subject TEXT,
    year INTEGER,
    session TEXT,
    grade TEXT,
    total_marks INTEGER,

    -- Sections data as JSONB (stores all MemoSection objects)
    sections JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Processing metadata (JSONB)
    processing_metadata JSONB DEFAULT '{}'::jsonb,

    -- Error handling
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),

    -- Performance and cost tracking
    processing_time_seconds DECIMAL(10, 3) CHECK (processing_time_seconds >= 0),
    cost_estimate_usd DECIMAL(10, 6) CHECK (cost_estimate_usd >= 0),

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Webhook integration
    webhook_url TEXT
);

-- Create unique index on file_hash for deduplication
CREATE UNIQUE INDEX IF NOT EXISTS idx_memo_extractions_file_hash ON memo_extractions(file_hash);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_memo_extractions_status ON memo_extractions(status);
CREATE INDEX IF NOT EXISTS idx_memo_extractions_created_at ON memo_extractions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memo_extractions_processing_method ON memo_extractions(processing_method);

-- Create composite index for filtering by status and date
CREATE INDEX IF NOT EXISTS idx_memo_extractions_status_created_at ON memo_extractions(status, created_at DESC);

-- Add trigger to automatically update updated_at timestamp (reuses existing function)
CREATE TRIGGER update_memo_extractions_updated_at
    BEFORE UPDATE ON memo_extractions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE memo_extractions IS 'Stores marking guideline (memo) extraction results for SA matric exam papers';
COMMENT ON COLUMN memo_extractions.id IS 'Primary key UUID';
COMMENT ON COLUMN memo_extractions.file_name IS 'Original filename (sanitized)';
COMMENT ON COLUMN memo_extractions.file_size_bytes IS 'File size in bytes';
COMMENT ON COLUMN memo_extractions.file_hash IS 'SHA-256 hash for deduplication';
COMMENT ON COLUMN memo_extractions.status IS 'Processing status: pending, completed, failed, or partial';
COMMENT ON COLUMN memo_extractions.processing_method IS 'Method used: hybrid (OpenDataLoader + Gemini) or vision_fallback (Gemini Vision only)';
COMMENT ON COLUMN memo_extractions.quality_score IS 'OpenDataLoader quality score (0.0-1.0) used for routing decisions';
COMMENT ON COLUMN memo_extractions.subject IS 'Subject name (e.g., "Business Studies P1")';
COMMENT ON COLUMN memo_extractions.year IS 'Exam year (e.g., 2025)';
COMMENT ON COLUMN memo_extractions.session IS 'Exam session: "MAY/JUNE" or "NOV"';
COMMENT ON COLUMN memo_extractions.grade IS 'Grade level (e.g., "12")';
COMMENT ON COLUMN memo_extractions.total_marks IS 'Total marks for the paper';
COMMENT ON COLUMN memo_extractions.sections IS 'Extracted memo sections with questions and answers (JSONB)';
COMMENT ON COLUMN memo_extractions.processing_metadata IS 'Processing metadata including method, cache stats, cost savings';
COMMENT ON COLUMN memo_extractions.error_message IS 'Error details if extraction failed';
COMMENT ON COLUMN memo_extractions.retry_count IS 'Number of retry attempts';
COMMENT ON COLUMN memo_extractions.processing_time_seconds IS 'Total processing time in seconds';
COMMENT ON COLUMN memo_extractions.cost_estimate_usd IS 'Estimated API cost in USD';
COMMENT ON COLUMN memo_extractions.webhook_url IS 'Optional webhook URL for completion notifications';
