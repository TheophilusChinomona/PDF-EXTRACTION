-- Normalized languages table for South African official languages
-- Run this manually in Supabase SQL Editor when ready

CREATE TABLE languages (
  id SERIAL PRIMARY KEY,
  name VARCHAR(50) UNIQUE NOT NULL,
  iso_code VARCHAR(10) UNIQUE NOT NULL
);

INSERT INTO languages (name, iso_code) VALUES
  ('English', 'en'),
  ('Afrikaans', 'af'),
  ('IsiZulu', 'zu'),
  ('IsiXhosa', 'xh'),
  ('Sepedi', 'nso'),
  ('Setswana', 'tn'),
  ('Sesotho', 'st'),
  ('Xitsonga', 'ts'),
  ('SiSwati', 'ss'),
  ('Tshivenda', 've'),
  ('IsiNdebele', 'nr');

-- ============================================================================
-- UPDATED EXTRACTIONS TABLE SCHEMA (for FullExamPaper model)
-- ============================================================================
-- If you have an existing extractions table, you may need to migrate or drop/recreate.
-- This schema is designed for exam paper extraction, not academic papers.

CREATE TABLE IF NOT EXISTS extractions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  -- File info
  file_name VARCHAR(255) NOT NULL,
  file_size_bytes INTEGER NOT NULL,
  file_hash VARCHAR(64) NOT NULL UNIQUE,

  -- Status
  status VARCHAR(20) NOT NULL DEFAULT 'pending',

  -- Exam paper metadata (queryable fields)
  subject VARCHAR(255),
  syllabus VARCHAR(10),
  year INTEGER,
  session VARCHAR(50),
  grade VARCHAR(10),
  language VARCHAR(50) DEFAULT 'English',
  total_marks INTEGER,

  -- Question data (JSON)
  groups JSONB DEFAULT '[]'::jsonb,

  -- Processing info
  processing_method VARCHAR(50),
  quality_score FLOAT,
  processing_metadata JSONB DEFAULT '{}'::jsonb,
  processing_time_seconds FLOAT,
  cost_estimate_usd FLOAT,

  -- Webhook and retry
  webhook_url TEXT,
  retry_count INTEGER DEFAULT 0,
  error_message TEXT,

  -- Optional: FK to normalized languages table
  language_id INTEGER REFERENCES languages(id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_extractions_file_hash ON extractions(file_hash);
CREATE INDEX IF NOT EXISTS idx_extractions_status ON extractions(status);
CREATE INDEX IF NOT EXISTS idx_extractions_subject ON extractions(subject);
CREATE INDEX IF NOT EXISTS idx_extractions_language ON extractions(language);
CREATE INDEX IF NOT EXISTS idx_extractions_year ON extractions(year);
CREATE INDEX IF NOT EXISTS idx_extractions_grade ON extractions(grade);

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_extractions_updated_at ON extractions;
CREATE TRIGGER update_extractions_updated_at
  BEFORE UPDATE ON extractions
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();
