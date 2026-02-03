-- Migration 012: Extraction jobs table (US-004)
-- Unified job tracking; replaces legacy parser_jobs for new flows.
-- Data from parser_jobs migrated where scraped_file_id is populated (after 009).

CREATE TABLE IF NOT EXISTS extraction_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scraped_file_id UUID NOT NULL REFERENCES scraped_files(id) ON DELETE CASCADE,
  job_type TEXT NOT NULL CHECK (job_type IN ('extraction', 'memo_extraction', 'parsing')),
  status TEXT NOT NULL DEFAULT 'pending',
  priority INTEGER NOT NULL DEFAULT 0,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  items_extracted INTEGER,
  errors_count INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_extraction_jobs_scraped_file_id ON extraction_jobs(scraped_file_id);
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_status ON extraction_jobs(status);
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_job_type ON extraction_jobs(job_type);

COMMENT ON TABLE extraction_jobs IS 'Unified extraction job tracking per scraped file.';

-- Migrate from parser_jobs where scraped_file_id is set (run after 009).
-- Only inserts scraped_file_id + defaults so it works regardless of parser_jobs column set.
INSERT INTO extraction_jobs (scraped_file_id, job_type, status, priority, errors_count)
SELECT j.scraped_file_id, 'parsing', 'pending', 0, 0
FROM parser_jobs j
WHERE j.scraped_file_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM extraction_jobs e WHERE e.scraped_file_id = j.scraped_file_id
  );
