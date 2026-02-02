-- Migration: 007_extend_scraped_files_for_firebase.sql
-- Description: Extend scraped_files table with Firebase-specific columns for full Firestore migration
-- Created: 2026-02-02
-- Depends on: 001_phase1_scraped_files_rejected_pdfs.sql (Academy Scrapper)

-- ============================================================================
-- ADD COLUMNS
-- ============================================================================

-- Firebase Storage fields
ALTER TABLE scraped_files ADD COLUMN IF NOT EXISTS storage_path TEXT;
ALTER TABLE scraped_files ADD COLUMN IF NOT EXISTS storage_bucket TEXT DEFAULT 'scrapperdb-f854d.firebasestorage.app';

-- Denormalized document metadata (extracted from metadata JSONB for fast filtering)
ALTER TABLE scraped_files ADD COLUMN IF NOT EXISTS document_type TEXT;
ALTER TABLE scraped_files ADD COLUMN IF NOT EXISTS year INTEGER;
ALTER TABLE scraped_files ADD COLUMN IF NOT EXISTS session TEXT;
ALTER TABLE scraped_files ADD COLUMN IF NOT EXISTS syllabus TEXT;
ALTER TABLE scraped_files ADD COLUMN IF NOT EXISTS language TEXT;

-- User tracking from Firebase Auth
ALTER TABLE scraped_files ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE scraped_files ADD COLUMN IF NOT EXISTS user_email TEXT;

-- Scraper job reference
ALTER TABLE scraped_files ADD COLUMN IF NOT EXISTS job_id TEXT;

-- Original download timestamp from Firestore
ALTER TABLE scraped_files ADD COLUMN IF NOT EXISTS downloaded_at TIMESTAMPTZ;

-- Cross-reference back to Firestore
ALTER TABLE scraped_files ADD COLUMN IF NOT EXISTS firestore_doc_id TEXT;

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Index on document_type for filtering by QP, MG, etc.
CREATE INDEX IF NOT EXISTS idx_scraped_files_document_type ON scraped_files(document_type);

-- Index on year for filtering by exam year
CREATE INDEX IF NOT EXISTS idx_scraped_files_year ON scraped_files(year);

-- Index on storage_path for Firebase Storage lookups
CREATE INDEX IF NOT EXISTS idx_scraped_files_storage_path ON scraped_files(storage_path);

-- Composite index for common query pattern: subject + grade + year
CREATE INDEX IF NOT EXISTS idx_scraped_files_subject_grade_year ON scraped_files(subject, grade, year);

-- Index on firestore_doc_id for cross-reference lookups
CREATE UNIQUE INDEX IF NOT EXISTS idx_scraped_files_firestore_doc_id ON scraped_files(firestore_doc_id)
    WHERE firestore_doc_id IS NOT NULL;

-- Index on session for filtering by exam session (MAY/JUNE, NOV, etc.)
CREATE INDEX IF NOT EXISTS idx_scraped_files_session ON scraped_files(session);

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON COLUMN scraped_files.storage_path IS 'Firebase Storage path within bucket (e.g., scraped_files/filename.pdf)';
COMMENT ON COLUMN scraped_files.storage_bucket IS 'Firebase Storage bucket name';
COMMENT ON COLUMN scraped_files.document_type IS 'Document type: QP (question paper), MG (marking guideline), etc.';
COMMENT ON COLUMN scraped_files.year IS 'Exam year (e.g., 2025)';
COMMENT ON COLUMN scraped_files.session IS 'Exam session/term: MAY/JUNE, NOV, FEB/MAR, etc.';
COMMENT ON COLUMN scraped_files.syllabus IS 'Syllabus type: NSC, IEB, etc.';
COMMENT ON COLUMN scraped_files.language IS 'Document language: English, Afrikaans, etc.';
COMMENT ON COLUMN scraped_files.user_id IS 'Firebase Auth UID of the user who scraped this file';
COMMENT ON COLUMN scraped_files.user_email IS 'Email of the user who scraped this file';
COMMENT ON COLUMN scraped_files.job_id IS 'Scraper job ID reference';
COMMENT ON COLUMN scraped_files.downloaded_at IS 'When the file was originally downloaded (from Firestore)';
COMMENT ON COLUMN scraped_files.firestore_doc_id IS 'Original Firestore document ID for cross-reference';

-- ============================================================================
-- VERIFICATION
-- ============================================================================

SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
    AND table_name = 'scraped_files'
ORDER BY ordinal_position;
