-- Migration: 006_add_constraints_and_indexes.sql
-- Description: Add unique partial indexes, performance indexes, and CHECK constraints (Gap Bridge Phase 1A)
-- Created: 2026-02-02
-- Purpose: Prevent duplicate extractions by file_hash for completed/pending, improve query performance

-- =============================================================================
-- EXTRACTIONS TABLE
-- =============================================================================

-- Drop existing non-partial unique index if present (replaced by partial unique index)
DROP INDEX IF EXISTS idx_extractions_file_hash;

-- Unique partial index: one completed/pending extraction per file_hash
CREATE UNIQUE INDEX IF NOT EXISTS idx_extractions_file_hash_completed_pending
    ON extractions(file_hash)
    WHERE status IN ('completed', 'pending');

-- Non-unique index on file_hash for lookups (unique enforced only for completed/pending via partial index above)
CREATE INDEX IF NOT EXISTS idx_extractions_file_hash ON extractions(file_hash);

-- CHECK: when status is 'partial', groups must be set (Gap 8.1)
ALTER TABLE extractions
    DROP CONSTRAINT IF EXISTS chk_extractions_partial_has_groups;
ALTER TABLE extractions
    ADD CONSTRAINT chk_extractions_partial_has_groups
    CHECK (status != 'partial' OR groups IS NOT NULL);

-- =============================================================================
-- MEMO_EXTRACTIONS TABLE
-- =============================================================================

-- Drop existing non-partial unique index if present (replaced by partial unique index)
DROP INDEX IF EXISTS idx_memo_extractions_file_hash;

-- Unique partial index: one completed/pending memo extraction per file_hash
CREATE UNIQUE INDEX IF NOT EXISTS idx_memo_extractions_file_hash_completed_pending
    ON memo_extractions(file_hash)
    WHERE status IN ('completed', 'pending');

-- Non-unique index on file_hash for lookups (unique enforced only for completed/pending via partial index above)
CREATE INDEX IF NOT EXISTS idx_memo_extractions_file_hash ON memo_extractions(file_hash);

-- memo_extractions uses 'sections' (NOT NULL); no partial CHECK needed for sections.
-- Optional: CHECK that partial status has sections (already NOT NULL DEFAULT '[]')
-- Skipped: sections is NOT NULL so constraint would be redundant.

COMMENT ON INDEX idx_extractions_file_hash_completed_pending IS 'Ensures at most one completed/pending extraction per file_hash';
COMMENT ON INDEX idx_memo_extractions_file_hash_completed_pending IS 'Ensures at most one completed/pending memo extraction per file_hash';
