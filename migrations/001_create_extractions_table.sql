-- Migration: 001_create_extractions_table.sql
-- Description: Create extractions table for storing PDF extraction results with bounding boxes
-- Created: 2026-01-28

-- Create enum types for status and processing method
CREATE TYPE extraction_status AS ENUM (
    'pending',
    'completed',
    'failed',
    'partial'
);

CREATE TYPE processing_method_type AS ENUM (
    'hybrid',
    'vision_fallback',
    'opendataloader_only'
);

-- Create extractions table
CREATE TABLE IF NOT EXISTS extractions (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- File metadata
    file_name TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes >= 0),
    file_hash TEXT NOT NULL,

    -- Processing status and method
    status extraction_status NOT NULL DEFAULT 'pending',
    processing_method processing_method_type,

    -- Quality and confidence scores
    quality_score DECIMAL(4, 3) CHECK (quality_score >= 0.0 AND quality_score <= 1.0),
    confidence_score DECIMAL(4, 3) CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),

    -- Extracted data (JSONB for flexible schema)
    metadata JSONB,
    sections JSONB,
    figures JSONB,
    tables JSONB,
    references JSONB,
    bounding_boxes JSONB,

    -- Text content
    abstract TEXT,

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
CREATE UNIQUE INDEX IF NOT EXISTS idx_extractions_file_hash ON extractions(file_hash);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_extractions_status ON extractions(status);
CREATE INDEX IF NOT EXISTS idx_extractions_created_at ON extractions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_extractions_processing_method ON extractions(processing_method);

-- Create composite index for filtering by status and date
CREATE INDEX IF NOT EXISTS idx_extractions_status_created_at ON extractions(status, created_at DESC);

-- Add trigger to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_extractions_updated_at
    BEFORE UPDATE ON extractions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE extractions IS 'Stores PDF extraction results with bounding boxes for citations';
COMMENT ON COLUMN extractions.id IS 'Primary key UUID';
COMMENT ON COLUMN extractions.file_name IS 'Original filename (sanitized)';
COMMENT ON COLUMN extractions.file_size_bytes IS 'File size in bytes';
COMMENT ON COLUMN extractions.file_hash IS 'SHA-256 hash for deduplication';
COMMENT ON COLUMN extractions.status IS 'Processing status: pending, completed, failed, or partial';
COMMENT ON COLUMN extractions.processing_method IS 'Method used: hybrid (OpenDataLoader + Gemini), vision_fallback (Gemini Vision only), or opendataloader_only';
COMMENT ON COLUMN extractions.quality_score IS 'OpenDataLoader quality score (0.0-1.0) used for routing decisions';
COMMENT ON COLUMN extractions.confidence_score IS 'Gemini confidence score (0.0-1.0)';
COMMENT ON COLUMN extractions.metadata IS 'Extracted bibliographic metadata (title, authors, journal, year, DOI)';
COMMENT ON COLUMN extractions.sections IS 'Extracted document sections with headings and content';
COMMENT ON COLUMN extractions.figures IS 'Extracted figures with captions and bounding boxes';
COMMENT ON COLUMN extractions.tables IS 'Extracted tables with captions and data';
COMMENT ON COLUMN extractions.references IS 'Extracted citations and references';
COMMENT ON COLUMN extractions.bounding_boxes IS 'Element bounding boxes for citation features (x1, y1, x2, y2, page)';
COMMENT ON COLUMN extractions.abstract IS 'Extracted abstract text';
COMMENT ON COLUMN extractions.error_message IS 'Error details if extraction failed';
COMMENT ON COLUMN extractions.retry_count IS 'Number of retry attempts';
COMMENT ON COLUMN extractions.processing_time_seconds IS 'Total processing time in seconds';
COMMENT ON COLUMN extractions.cost_estimate_usd IS 'Estimated API cost in USD';
COMMENT ON COLUMN extractions.webhook_url IS 'Optional webhook URL for completion notifications';
