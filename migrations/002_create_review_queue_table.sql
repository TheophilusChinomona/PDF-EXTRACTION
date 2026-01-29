-- Migration: 002_create_review_queue_table.sql
-- Description: Create review queue table for manual review of failed extractions
-- Created: 2026-01-28

-- Create enum type for resolution status
CREATE TYPE review_resolution AS ENUM (
    'fixed',
    'false_positive',
    'unable_to_process'
);

-- Create review_queue table
CREATE TABLE IF NOT EXISTS review_queue (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign key to extraction
    extraction_id UUID NOT NULL REFERENCES extractions(id) ON DELETE CASCADE,

    -- Error information
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,

    -- Processing context
    processing_method processing_method_type,
    quality_score DECIMAL(4, 3) CHECK (quality_score >= 0.0 AND quality_score <= 1.0),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),

    -- Review status
    resolution review_resolution,
    reviewer_notes TEXT,

    -- Timestamps
    queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,

    -- Constraint: reviewed_at must be set if resolution is set
    CONSTRAINT resolution_reviewed_check CHECK (
        (resolution IS NULL AND reviewed_at IS NULL) OR
        (resolution IS NOT NULL AND reviewed_at IS NOT NULL)
    )
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_review_queue_extraction_id ON review_queue(extraction_id);
CREATE INDEX IF NOT EXISTS idx_review_queue_pending ON review_queue(queued_at DESC) WHERE resolution IS NULL;
CREATE INDEX IF NOT EXISTS idx_review_queue_resolution ON review_queue(resolution);
CREATE INDEX IF NOT EXISTS idx_review_queue_queued_at ON review_queue(queued_at DESC);

-- Add comments for documentation
COMMENT ON TABLE review_queue IS 'Manual review queue for failed extractions that exceeded retry limit';
COMMENT ON COLUMN review_queue.id IS 'Primary key UUID';
COMMENT ON COLUMN review_queue.extraction_id IS 'Foreign key to extractions table';
COMMENT ON COLUMN review_queue.error_type IS 'Classification of error (e.g., gemini_api_error, validation_error)';
COMMENT ON COLUMN review_queue.error_message IS 'Detailed error message for debugging';
COMMENT ON COLUMN review_queue.processing_method IS 'Method that was attempted: hybrid or vision_fallback';
COMMENT ON COLUMN review_queue.quality_score IS 'OpenDataLoader quality score if available';
COMMENT ON COLUMN review_queue.retry_count IS 'Number of retries before queuing for review';
COMMENT ON COLUMN review_queue.resolution IS 'Manual review resolution: fixed, false_positive, or unable_to_process';
COMMENT ON COLUMN review_queue.reviewer_notes IS 'Human reviewer notes and actions taken';
COMMENT ON COLUMN review_queue.queued_at IS 'Timestamp when added to review queue';
COMMENT ON COLUMN review_queue.reviewed_at IS 'Timestamp when manual review completed';
