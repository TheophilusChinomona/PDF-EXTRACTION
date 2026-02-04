-- Migration 016: Document versions table (US-008) – duplicate tracking for exam sets
-- Depends on: exam_sets (014), scraped_files

CREATE TABLE IF NOT EXISTS document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exam_set_id UUID NOT NULL REFERENCES exam_sets(id) ON DELETE CASCADE,
    original_id UUID NOT NULL REFERENCES scraped_files(id) ON DELETE CASCADE,
    duplicate_id UUID NOT NULL REFERENCES scraped_files(id) ON DELETE CASCADE,
    slot TEXT NOT NULL CHECK (slot IN ('question_paper', 'memo')),
    is_active BOOLEAN NOT NULL DEFAULT false,
    uploaded_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),

    UNIQUE(exam_set_id, duplicate_id)
);

CREATE INDEX IF NOT EXISTS idx_document_versions_exam_set ON document_versions(exam_set_id);
CREATE INDEX IF NOT EXISTS idx_document_versions_original ON document_versions(original_id);
CREATE INDEX IF NOT EXISTS idx_document_versions_duplicate ON document_versions(duplicate_id);

COMMENT ON TABLE document_versions IS 'Tracks duplicate QP/Memo per exam set slot; one version marked active for reconstruction.';
