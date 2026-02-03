-- Migration 013: scraped_files status and validation_status (US-012)
-- Status flow: pending -> downloading -> downloaded -> validating -> validated
--   -> queued_for_extraction -> extracting -> completed
-- Or: review_required, rejected, failed
-- validation_status: unvalidated, queued, validated, rejected, review_required, failed

-- ============================================================================
-- Add validation_status column
-- ============================================================================

ALTER TABLE scraped_files
  ADD COLUMN IF NOT EXISTS validation_status TEXT DEFAULT 'unvalidated';

-- Constrain validation_status
ALTER TABLE scraped_files
  DROP CONSTRAINT IF EXISTS scraped_files_validation_status_check;

ALTER TABLE scraped_files
  ADD CONSTRAINT scraped_files_validation_status_check
  CHECK (validation_status IN ('unvalidated', 'queued', 'validated', 'rejected', 'review_required', 'failed'));

CREATE INDEX IF NOT EXISTS idx_scraped_files_validation_status ON scraped_files(validation_status);

COMMENT ON COLUMN scraped_files.validation_status IS 'Validation pipeline state: unvalidated, queued, validated, rejected, review_required, failed';

-- ============================================================================
-- Update status check constraint
-- ============================================================================
-- Drop existing status constraint if present (name may vary by Academy schema).
-- Then add new constraint with full status set.

DO $$
DECLARE
  r RECORD;
BEGIN
  -- Drop any existing CHECK on scraped_files.status so we can replace with new enum set
  FOR r IN (
    SELECT tc.constraint_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
    WHERE tc.table_schema = 'public' AND tc.table_name = 'scraped_files'
      AND tc.constraint_type = 'CHECK' AND ccu.column_name = 'status'
  ) LOOP
    EXECUTE format('ALTER TABLE scraped_files DROP CONSTRAINT IF EXISTS %I', r.constraint_name);
  END LOOP;
END $$;

ALTER TABLE scraped_files
  ADD CONSTRAINT scraped_files_status_check
  CHECK (status IN (
    'pending', 'downloading', 'downloaded', 'validating', 'validated',
    'queued_for_extraction', 'extracting', 'completed',
    'review_required', 'rejected', 'failed'
  ));

COMMENT ON COLUMN scraped_files.status IS 'Pipeline status: pending, downloading, downloaded, validating, validated, queued_for_extraction, extracting, completed, review_required, rejected, failed';
