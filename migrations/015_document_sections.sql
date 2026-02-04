-- Migration 015: Document sections table (US-002) – cover, instructions, marker notes, info sheet
-- Depends on: scraped_files

CREATE TABLE IF NOT EXISTS document_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scraped_file_id UUID NOT NULL REFERENCES scraped_files(id) ON DELETE CASCADE,

    section_type TEXT NOT NULL CHECK (section_type IN (
        'cover_page',
        'student_instructions',
        'marker_notes',
        'information_sheet',
        'mark_breakdown',
        'appendix'
    )),

    title TEXT,
    content JSONB NOT NULL DEFAULT '{}',
    raw_text TEXT,

    page_start INTEGER,
    page_end INTEGER,

    extraction_method TEXT,
    confidence_score INTEGER CHECK (confidence_score BETWEEN 0 AND 100),

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),

    UNIQUE(scraped_file_id, section_type)
);

CREATE INDEX IF NOT EXISTS idx_document_sections_file ON document_sections(scraped_file_id);
CREATE INDEX IF NOT EXISTS idx_document_sections_type ON document_sections(section_type);

COMMENT ON TABLE document_sections IS 'Extracted sections per document: cover, instructions, marker notes, information sheet, etc.';
