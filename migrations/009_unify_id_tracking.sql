-- Migration 009: Unify ID tracking (US-001, US-013)
-- Add scraped_file_id UUID to Academy Scrapper tables; retain legacy file_id TEXT.
-- Populate scraped_file_id from file_id lookup (scraped_files.id::text or firestore_doc_id).

-- ============================================================================
-- parsed_questions: add scraped_file_id UUID FK
-- ============================================================================

ALTER TABLE parsed_questions
  ADD COLUMN IF NOT EXISTS scraped_file_id UUID REFERENCES scraped_files(id);

CREATE INDEX IF NOT EXISTS idx_parsed_questions_scraped_file_id ON parsed_questions(scraped_file_id);

COMMENT ON COLUMN parsed_questions.scraped_file_id IS 'UUID FK to scraped_files(id); authoritative. file_id retained for backward compatibility.';

-- ============================================================================
-- parser_jobs: add scraped_file_id UUID FK
-- ============================================================================

ALTER TABLE parser_jobs
  ADD COLUMN IF NOT EXISTS scraped_file_id UUID REFERENCES scraped_files(id);

CREATE INDEX IF NOT EXISTS idx_parser_jobs_scraped_file_id ON parser_jobs(scraped_file_id);

COMMENT ON COLUMN parser_jobs.scraped_file_id IS 'UUID FK to scraped_files(id); authoritative. file_id retained for backward compatibility.';

-- ============================================================================
-- Data migration: populate scraped_file_id from file_id
-- ============================================================================
-- Match file_id to scraped_files.id (as text) or firestore_doc_id for legacy rows.

UPDATE parsed_questions p
SET scraped_file_id = s.id
FROM scraped_files s
WHERE p.scraped_file_id IS NULL
  AND (s.id::text = p.file_id OR (p.file_id IS NOT NULL AND s.firestore_doc_id = p.file_id));

UPDATE parser_jobs j
SET scraped_file_id = s.id
FROM scraped_files s
WHERE j.scraped_file_id IS NULL
  AND (s.id::text = j.file_id OR (j.file_id IS NOT NULL AND s.firestore_doc_id = j.file_id));
