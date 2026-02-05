-- Migration: 020_add_batch_api_processing_method.sql
-- Description: Add 'batch_api' value to processing_method_type enum for Gemini Batch API support
-- Created: 2026-02-05

-- Add 'batch_api' to the processing_method_type enum
-- This is needed because extraction_batch.py sets processing_metadata['method'] = 'batch_api'
-- and the DB insert functions use this value for the processing_method column
ALTER TYPE processing_method_type ADD VALUE IF NOT EXISTS 'batch_api';

-- Update the column comment to document the new value
COMMENT ON COLUMN extractions.processing_method IS 'Method used: hybrid (OpenDataLoader + Gemini), vision_fallback (Gemini Vision only), opendataloader_only, or batch_api (Gemini Batch API)';
