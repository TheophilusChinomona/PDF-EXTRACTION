-- Migration 017: Link validation_results to scraped_files (validation data unification)
-- Populates scraped_file_id via filename matching, syncs validation_status to scraped_files.
-- Keeps file_id column intact for rollback/reference.

BEGIN;

-- ============================================================================
-- Step 1.1: Link single-match records (validation_results with exactly one scraped_files filename match)
-- ============================================================================

WITH filename_counts AS (
  SELECT filename, COUNT(*) AS cnt FROM scraped_files GROUP BY filename
),
single_filenames AS (
  SELECT filename FROM filename_counts WHERE cnt = 1
),
single_ids AS (
  SELECT sf.filename, sf.id
  FROM scraped_files sf
  JOIN single_filenames s ON sf.filename = s.filename
)
UPDATE validation_results vr
SET scraped_file_id = si.id
FROM single_ids si
WHERE vr.scraped_file_id IS NULL AND vr.filename = si.filename;

-- ============================================================================
-- Step 1.2: Handle duplicate matches (same filename in multiple scraped_files – pick most recent)
-- ============================================================================

WITH latest_per_filename AS (
  SELECT DISTINCT ON (filename) filename, id
  FROM scraped_files
  ORDER BY filename, created_at DESC
)
UPDATE validation_results vr
SET scraped_file_id = lp.id
FROM latest_per_filename lp
WHERE vr.scraped_file_id IS NULL AND vr.filename = lp.filename;

-- ============================================================================
-- Step 1.3: Sync validation_status to scraped_files
-- ============================================================================

UPDATE scraped_files sf
SET validation_status = CASE
  WHEN vr.status = 'correct' THEN 'validated'
  WHEN vr.status = 'rejected' THEN 'rejected'
  WHEN vr.status = 'review_required' THEN 'review_required'
  ELSE sf.validation_status
END
FROM validation_results vr
WHERE sf.id = vr.scraped_file_id
  AND sf.validation_status = 'unvalidated';

-- ============================================================================
-- Step 1.4: Add foreign key and index (only if FK not already present)
-- ============================================================================

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) AND NOT a.attisdropped
    WHERE c.conrelid = 'public.validation_results'::regclass
      AND c.contype = 'f'
      AND a.attname = 'scraped_file_id'
  ) THEN
    ALTER TABLE validation_results
      ADD CONSTRAINT fk_validation_results_scraped_file
      FOREIGN KEY (scraped_file_id) REFERENCES scraped_files(id) ON DELETE SET NULL;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_validation_results_scraped_file_id
  ON validation_results(scraped_file_id);

COMMIT;
