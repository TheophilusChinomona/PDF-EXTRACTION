-- Migration 019: Drop Firestore cross-reference column (Firestore fully migrated to Supabase)
-- Rule: Firebase only for hosting frontend + auth + PDF storage; Supabase for all data.
-- firestore_doc_id was used during migration; no longer needed.

-- Drop the unique index first (depends on the column)
DROP INDEX IF EXISTS idx_scraped_files_firestore_doc_id;

-- Drop the column
ALTER TABLE scraped_files DROP COLUMN IF EXISTS firestore_doc_id;

COMMENT ON TABLE scraped_files IS 'Source PDFs from Firebase Storage; metadata in Supabase only (no Firestore).';
