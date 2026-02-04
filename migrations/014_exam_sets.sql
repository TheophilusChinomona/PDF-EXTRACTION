-- Migration 014: Exam sets table (US-001) – QP–Memo linking
-- Depends on: scraped_files (007, 008)

CREATE TABLE IF NOT EXISTS exam_sets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Exam identity (matching key)
    subject TEXT NOT NULL,
    grade INTEGER NOT NULL,
    paper_number INTEGER NOT NULL,
    year INTEGER NOT NULL,
    session TEXT NOT NULL,
    syllabus TEXT,

    -- Linked documents
    question_paper_id UUID REFERENCES scraped_files(id),
    memo_id UUID REFERENCES scraped_files(id),

    -- Matching info
    match_method TEXT CHECK (match_method IN (
        'automatic', 'manual', 'filename', 'content'
    )),
    match_confidence INTEGER CHECK (match_confidence BETWEEN 0 AND 100),
    matched_at TIMESTAMPTZ,
    matched_by TEXT,

    -- Status
    status TEXT DEFAULT 'incomplete' CHECK (status IN (
        'incomplete',
        'matched',
        'verified',
        'mismatch',
        'duplicate_review'
    )),

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_exam_sets_match_key
    ON exam_sets(subject, grade, paper_number, year, session, COALESCE(syllabus, ''));
CREATE INDEX IF NOT EXISTS idx_exam_sets_matching
    ON exam_sets(subject, grade, paper_number, year, session);
CREATE INDEX IF NOT EXISTS idx_exam_sets_qp ON exam_sets(question_paper_id) WHERE question_paper_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_exam_sets_memo ON exam_sets(memo_id) WHERE memo_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_exam_sets_status ON exam_sets(status);

COMMENT ON TABLE exam_sets IS 'Matched question paper and memo pairs; unique per (subject, grade, paper_number, year, session, syllabus).';
