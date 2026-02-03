-- Migration 010: Validation tables (US-002, US-003)
-- validation_results: one row per scraped_file validation outcome
-- validation_jobs: batch job progress for validation runs

-- ============================================================================
-- validation_results
-- ============================================================================

CREATE TABLE IF NOT EXISTS validation_results (
  scraped_file_id UUID NOT NULL PRIMARY KEY REFERENCES scraped_files(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK (status IN ('correct', 'rejected', 'review_required', 'pending', 'error')),
  confidence_score NUMERIC(5,4),
  subject TEXT,
  grade TEXT,
  year INTEGER,
  paper_type TEXT,
  paper_number INTEGER,
  session TEXT,
  syllabus TEXT,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_validation_results_status ON validation_results(status);
CREATE INDEX IF NOT EXISTS idx_validation_results_confidence_score ON validation_results(confidence_score);

COMMENT ON TABLE validation_results IS 'Validation outcome per scraped file; status drives extraction trigger.';
COMMENT ON COLUMN validation_results.status IS 'correct=proceed to extraction, rejected, review_required, pending, error';

-- ============================================================================
-- validation_jobs
-- ============================================================================

CREATE TABLE IF NOT EXISTS validation_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status TEXT NOT NULL CHECK (status IN ('pending', 'queued', 'running', 'completed', 'failed', 'paused', 'cancelled')),
  total_files INTEGER NOT NULL DEFAULT 0,
  processed_files INTEGER NOT NULL DEFAULT 0,
  accepted_files INTEGER NOT NULL DEFAULT 0,
  rejected_files INTEGER NOT NULL DEFAULT 0,
  review_required_files INTEGER NOT NULL DEFAULT 0,
  failed_files INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_validation_jobs_status ON validation_jobs(status);
CREATE INDEX IF NOT EXISTS idx_validation_jobs_created_at ON validation_jobs(created_at);

COMMENT ON TABLE validation_jobs IS 'Batch validation job progress for monitoring.';
