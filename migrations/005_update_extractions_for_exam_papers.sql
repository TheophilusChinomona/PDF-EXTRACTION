-- Migration: 005_update_extractions_for_exam_papers.sql
-- Description: Update extractions table to match FullExamPaper model (exam papers, not academic papers)
-- Created: 2026-01-29
-- Purpose: Align database schema with actual Python models being used

-- Drop old columns that aren't used (academic paper fields)
ALTER TABLE extractions
    DROP COLUMN IF EXISTS metadata,
    DROP COLUMN IF EXISTS sections,
    DROP COLUMN IF EXISTS figures,
    DROP COLUMN IF EXISTS "references",
    DROP COLUMN IF EXISTS bounding_boxes,
    DROP COLUMN IF EXISTS abstract,
    DROP COLUMN IF EXISTS confidence_score;

-- Add exam paper metadata columns
ALTER TABLE extractions
    ADD COLUMN IF NOT EXISTS subject TEXT,
    ADD COLUMN IF NOT EXISTS syllabus TEXT,
    ADD COLUMN IF NOT EXISTS year INTEGER,
    ADD COLUMN IF NOT EXISTS session TEXT,
    ADD COLUMN IF NOT EXISTS grade TEXT,
    ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'English',
    ADD COLUMN IF NOT EXISTS total_marks INTEGER DEFAULT 150;

-- Add groups JSONB column for question groups
ALTER TABLE extractions
    ADD COLUMN IF NOT EXISTS groups JSONB NOT NULL DEFAULT '[]'::jsonb;

-- Add processing_metadata JSONB column
ALTER TABLE extractions
    ADD COLUMN IF NOT EXISTS processing_metadata JSONB DEFAULT '{}'::jsonb;

-- Add indexes for exam paper queries
CREATE INDEX IF NOT EXISTS idx_extractions_subject ON extractions(subject);
CREATE INDEX IF NOT EXISTS idx_extractions_year ON extractions(year DESC);
CREATE INDEX IF NOT EXISTS idx_extractions_grade ON extractions(grade);
CREATE INDEX IF NOT EXISTS idx_extractions_session ON extractions(session);

-- Create composite index for common exam paper queries
CREATE INDEX IF NOT EXISTS idx_extractions_subject_grade_year ON extractions(subject, grade, year DESC);

-- Update comments to reflect exam paper focus
COMMENT ON TABLE extractions IS 'Stores exam paper extraction results with question groups and metadata';
COMMENT ON COLUMN extractions.subject IS 'Subject name, e.g., "Business Studies P1"';
COMMENT ON COLUMN extractions.syllabus IS 'Syllabus type: "SC" (South African Curriculum) or "NSC" (National Senior Certificate)';
COMMENT ON COLUMN extractions.year IS 'Examination year, e.g., 2025';
COMMENT ON COLUMN extractions.session IS 'Examination session: "MAY/JUNE" or "NOV"';
COMMENT ON COLUMN extractions.grade IS 'Grade level, e.g., "12"';
COMMENT ON COLUMN extractions.language IS 'Document language: "English", "Afrikaans", "IsiZulu", etc.';
COMMENT ON COLUMN extractions.total_marks IS 'Total marks for the exam paper';
COMMENT ON COLUMN extractions.groups IS 'Question groups (JSONB array of QuestionGroup objects)';
COMMENT ON COLUMN extractions.processing_metadata IS 'Processing metadata including method, quality scores, cost estimates, cache stats';
