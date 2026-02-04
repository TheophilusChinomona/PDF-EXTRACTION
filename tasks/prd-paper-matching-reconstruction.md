# PRD: Paper Matching & Reconstruction Service

## Implementation Location

This PRD is implemented **primarily in one codebase** with minor changes to another:

| Codebase | Path | Language | Changes |
|----------|------|----------|---------|
| **PDF-Extraction** (PRIMARY) | `C:\Users\theoc\Desktop\Work\PDF-Extraction` | Python/FastAPI | 95% of work - all new tables, services, APIs |
| **Academy Scrapper** (MINOR) | `C:\Users\theoc\Desktop\Work\Academy Scrapper` | Python | ValidationAgent: call matcher after validation |

**Work in:** PDF-Extraction for all implementation
**Minor touch:** Academy Scrapper's ValidationAgent (2 files only)

---

## Introduction

The extraction pipeline currently processes question papers (QP) and memos independently with no linkage between them. Additionally, valuable document sections like student instructions, marker notes, cover pages, and information sheets are skipped during extraction.

This service extends the pipeline to:
1. **Match QP ↔ Memo** pairs based on metadata (subject, grade, paper, year, session)
2. **Extract all document sections** separately from questions/answers
3. **Enable paper reconstruction** from database (rebuild complete papers including all sections)

This runs as a separate workstream that can be developed in parallel with the Unified PDF Extraction System.

## Goals

- Automatically match question papers to their corresponding memos with 95%+ accuracy
- Extract and store all document sections: cover page, student instructions, marker notes, information sheet
- Create `exam_sets` table linking paired QP/Memo documents
- Support version tracking for duplicate documents with admin manual resolution
- Enable partial paper reconstruction (QP-only or Memo-only when pair incomplete)
- Provide API endpoints for exam set management and paper reconstruction
- Run batch matching job to scan and link unlinked documents

## User Stories

### US-001: Create exam_sets table for QP-Memo linking
**Description:** As a developer, I need a table to store matched exam paper pairs so QPs and Memos are linked.

**Acceptance Criteria:**
- [ ] `exam_sets` table created with fields: subject, grade, paper_number, year, session, syllabus
- [ ] `question_paper_id` and `memo_id` UUID foreign keys to `scraped_files`
- [ ] `match_method` field: 'automatic', 'manual', 'filename', 'content'
- [ ] `match_confidence` integer 0-100
- [ ] `status` field: 'incomplete', 'matched', 'verified', 'mismatch'
- [ ] Unique constraint on (subject, grade, paper_number, year, session, syllabus)
- [ ] Migration runs successfully

### US-002: Create document_sections table for extracted sections
**Description:** As a developer, I need a table to store document sections (instructions, marker notes, etc.) separately from questions.

**Acceptance Criteria:**
- [ ] `document_sections` table created with `scraped_file_id` UUID FK
- [ ] `section_type` field: 'cover_page', 'student_instructions', 'marker_notes', 'information_sheet', 'mark_breakdown', 'appendix'
- [ ] `content` JSONB field for structured section data
- [ ] `raw_text` TEXT field for plain text version
- [ ] `page_start` and `page_end` integer fields for location tracking
- [ ] Unique constraint on (scraped_file_id, section_type)
- [ ] Migration runs successfully

### US-003: Implement subject normalization
**Description:** As a system, I need to normalize subject names so "Maths", "Mathematics", and "Math" all match.

**Acceptance Criteria:**
- [ ] Normalization function handles common variations (see Appendix B in plan)
- [ ] "maths", "math", "mathematics" → "Mathematics"
- [ ] "physical science", "physics" → "Physical Sciences"
- [ ] "life science", "biology" → "Life Sciences"
- [ ] Case-insensitive matching
- [ ] Unknown subjects preserved with title case

### US-004: Implement grade normalization
**Description:** As a system, I need to normalize grade values to integers so "Grade 12", "Gr 12", "12" all match.

**Acceptance Criteria:**
- [ ] Function extracts integer from strings like "Grade 12", "Gr 12"
- [ ] Integer inputs passed through unchanged
- [ ] Returns `None` for unparseable values
- [ ] Stored as INTEGER in database (not "Grade 12" string)

### US-005: Implement paper number normalization
**Description:** As a system, I need to normalize paper numbers to integers so "P1", "Paper 1", "1" all match.

**Acceptance Criteria:**
- [ ] Function extracts integer from strings like "P1", "Paper 1"
- [ ] Integer inputs passed through unchanged
- [ ] Defaults to 1 if unparseable
- [ ] Stored as INTEGER in database (not "P1" string)

### US-006: Implement session normalization
**Description:** As a system, I need to normalize session names so "May", "June", "May/June" all match.

**Acceptance Criteria:**
- [ ] "may", "june", "may/june", "may-june" → "May/June"
- [ ] "nov", "november" → "November"
- [ ] "feb", "march", "feb/march", "supplementary" → "February/March"
- [ ] Case-insensitive matching

### US-007: Implement automatic matching algorithm
**Description:** As a system, I want documents automatically matched to exam sets during validation so pairs are linked without manual intervention.

**Acceptance Criteria:**
- [ ] Matching runs after validation extracts metadata
- [ ] Match key: (subject, grade, paper_number, year, session, syllabus)
- [ ] If exam_set exists: link document to appropriate slot (QP or Memo)
- [ ] If no exam_set exists: create new incomplete exam_set
- [ ] Status updated to 'matched' when both QP and Memo linked
- [ ] Match confidence calculated (25 subject + 20 grade + 20 paper + 20 year + 15 session = 100)

### US-008: Implement duplicate document handling with version tracking
**Description:** As a system, I want to keep all versions of duplicate documents and flag them for admin review.

**Acceptance Criteria:**
- [ ] When duplicate detected (same slot already filled), create `document_versions` record
- [ ] Track: original_id, duplicate_id, uploaded_at, is_active flag
- [ ] Flag exam_set for manual resolution (add to review queue)
- [ ] Admin can set which version is "active"
- [ ] Non-active versions retained but not used in reconstruction

### US-009: Extract cover page section
**Description:** As a system, I want to extract cover page metadata so it can be displayed in reconstructed papers.

**Acceptance Criteria:**
- [ ] Extract: organization, certificate type, grade, subject, paper number, session/year
- [ ] Extract: total marks, time allowed, page count
- [ ] Store as JSONB in `document_sections` with `section_type = 'cover_page'`
- [ ] Include `page_start = 1`, `page_end = 1`

### US-010: Extract student instructions section
**Description:** As a system, I want to extract student instructions from question papers so they're available for reconstruction.

**Acceptance Criteria:**
- [ ] Extract numbered instruction items from page 2 (typically)
- [ ] Extract general notes (e.g., "Diagrams are NOT necessarily drawn to scale")
- [ ] Store as JSONB with `header`, `items[]`, `notes[]` structure
- [ ] `section_type = 'student_instructions'`
- [ ] Only extracted from question papers (not memos)

### US-011: Extract marker notes section
**Description:** As a system, I want to extract marker notes from memos so they're available for reconstruction.

**Acceptance Criteria:**
- [ ] Extract "Notes to Markers" content (pages 2-6 typically)
- [ ] Extract marking color codes, cognitive verbs, essay marking rubrics
- [ ] Extract section-specific marking instructions
- [ ] Store as JSONB with `header`, `preamble`, `sections[]`, `cognitive_verbs{}`, `essay_marking{}` structure
- [ ] `section_type = 'marker_notes'`
- [ ] Only extracted from memos (not question papers)

### US-012: Extract information sheet section
**Description:** As a system, I want to extract the information sheet (formulae) from question papers so it's available for reconstruction.

**Acceptance Criteria:**
- [ ] Detect information sheet (typically last page)
- [ ] Extract formulae with names and LaTeX notation
- [ ] Extract reference tables and constants if present
- [ ] Store as JSONB with `header`, `formulae[]`, `tables[]`, `constants[]` structure
- [ ] `section_type = 'information_sheet'`
- [ ] Handle case where no information sheet exists (null)

### US-013: Create batch matching job
**Description:** As a system, I want a scheduled job that scans unlinked documents and creates/updates exam sets.

**Acceptance Criteria:**
- [ ] Job queries documents not linked to any exam_set
- [ ] Runs matching algorithm for each unlinked document
- [ ] Creates exam_sets or links to existing ones
- [ ] Logs progress: total scanned, matched, newly created, errors
- [ ] Can be triggered manually via API or scheduled (cron)
- [ ] Idempotent (safe to run multiple times)

### US-014: Create exam sets list API endpoint
**Description:** As an API consumer, I want to list exam sets with filtering so I can find specific papers.

**Acceptance Criteria:**
- [ ] `GET /api/exam-sets` endpoint with query params: subject, grade, year, session, status
- [ ] Returns list with QP/Memo linkage status
- [ ] Pagination support (limit, offset)
- [ ] Sort by year DESC, subject ASC default

### US-015: Create exam set detail API endpoint
**Description:** As an API consumer, I want to get full exam set details including linked documents and sections.

**Acceptance Criteria:**
- [ ] `GET /api/exam-sets/{exam_set_id}` endpoint
- [ ] Returns exam set metadata plus linked QP and Memo file info
- [ ] Includes section availability flags (has_instructions, has_marker_notes, etc.)
- [ ] Returns match_confidence and match_method

### US-016: Create paper reconstruction API endpoint
**Description:** As an API consumer, I want to reconstruct complete papers from the database so users can view full documents.

**Acceptance Criteria:**
- [ ] `GET /api/exam-sets/{exam_set_id}/question-paper/full` returns complete QP
- [ ] Response includes: cover_page, instructions, questions[], information_sheet
- [ ] `GET /api/exam-sets/{exam_set_id}/memo/full` returns complete memo
- [ ] Response includes: cover_page, marker_notes, answers[], mark_breakdown
- [ ] Partial reconstruction works when only QP or only Memo available
- [ ] Missing sections return null (not error)

### US-017: Create document sections API endpoints
**Description:** As an API consumer, I want to query sections for individual documents.

**Acceptance Criteria:**
- [ ] `GET /api/documents/{scraped_file_id}/sections` returns all sections
- [ ] `GET /api/documents/{scraped_file_id}/sections/{section_type}` returns specific section
- [ ] 404 if section doesn't exist
- [ ] Includes extraction metadata (method, confidence, page range)

### US-018: Create manual match API endpoint
**Description:** As an admin, I want to manually link QP and Memo when automatic matching fails.

**Acceptance Criteria:**
- [ ] `POST /api/exam-sets/match` accepts `question_paper_id` and `memo_id`
- [ ] Creates or updates exam_set with `match_method = 'manual'`
- [ ] Calculates and stores match_confidence
- [ ] Returns created/updated exam_set

### US-019: Update extraction pipeline to extract sections
**Description:** As a developer, I need the extraction pipeline to call section extraction before question extraction.

**Acceptance Criteria:**
- [ ] Section extraction runs after validation, before question extraction
- [ ] All section types extracted in single pass (cover, instructions, info sheet for QP; cover, marker notes for Memo)
- [ ] Sections stored in `document_sections` table
- [ ] Question/answer extraction unchanged
- [ ] Processing time increase < 30% from section extraction

### US-020: Integrate matching into validation flow
**Description:** As a developer, I need documents matched to exam sets immediately after validation.

**Acceptance Criteria:**
- [ ] Matching called after `validation_results` record created
- [ ] `exam_set_id` stored in `scraped_files.metadata` for reference
- [ ] Exam set status updated based on match result
- [ ] Duplicate detection triggers review queue entry

## Functional Requirements

- FR-1: Each exam set uniquely identified by (subject, grade, paper_number, year, session, syllabus)
- FR-2: Subject, grade, paper_number, and session values normalized before matching
- FR-3: Grade stored as INTEGER (12), not string ("Grade 12")
- FR-4: Paper number stored as INTEGER (1), not string ("P1")
- FR-5: Exam sets created via batch job scanning unlinked documents
- FR-6: Duplicate documents tracked with version history and manual resolution
- FR-7: All document sections extracted in single pass: cover_page, student_instructions/marker_notes, information_sheet
- FR-8: Partial reconstruction supported (QP-only or Memo-only)
- FR-9: Match confidence calculated from metadata field matches
- FR-10: Section extraction stores both structured JSONB and raw text versions
- FR-11: API returns null for missing sections (not errors)
- FR-12: Manual matching overrides automatic matching

## Non-Goals (Out of Scope)

- PDF regeneration from database (reconstruction returns JSON, not PDF)
- OCR improvements or alternative extraction methods
- Cross-syllabus matching (NSC paper won't match IEB memo)
- Automatic duplicate resolution (admin manual review required)
- Real-time matching notifications (batch job is sufficient)
- UI for exam set management (API only in this phase)
- Historical version comparison (only track which is active)

## Technical Considerations

### Database
- `exam_sets` table with composite unique constraint
- `document_sections` table with JSONB content storage
- `document_versions` table for duplicate tracking
- Indexes on matching key fields for fast lookups

### Section Extraction
- Gemini Vision API for section identification and extraction
- Single prompt extracts all sections to minimize API calls
- LaTeX notation for mathematical formulae in information sheets
- Page range tracking for audit trail

### Matching Algorithm
- Runs during validation (automatic) or via batch job (catchup)
- Normalization functions for fuzzy matching
- Confidence scoring based on field match counts
- Batch job idempotent and safe for concurrent runs

### Integration
- Section extraction added to existing pipeline (not replacement)
- Exam set linking via foreign keys to `scraped_files`
- API endpoints follow existing patterns in PDF-Extraction

## Files to Create/Modify

### New Files - PDF-Extraction Project

| File Path | Purpose | User Story |
|-----------|---------|------------|
| `migrations/014_exam_sets.sql` | Create exam_sets table for QP-Memo linking | US-001 |
| `migrations/015_document_sections.sql` | Create document_sections table | US-002 |
| `migrations/016_document_versions.sql` | Create document_versions table for duplicate tracking | US-008 |
| `app/services/exam_matcher.py` | Matching algorithm and normalization functions | US-003, US-004, US-005, US-006, US-007 |
| `app/services/section_extractor.py` | Extract cover, instructions, marker notes, info sheet | US-009, US-010, US-011, US-012 |
| `app/services/batch_matcher.py` | Batch job for scanning/linking unlinked documents | US-013 |
| `app/db/exam_sets.py` | CRUD operations for exam_sets table | US-001, US-007 |
| `app/db/document_sections.py` | CRUD operations for document_sections table | US-002 |
| `app/db/document_versions.py` | CRUD operations for document_versions table | US-008 |
| `app/routers/exam_sets.py` | Exam sets API endpoints (list, detail, match) | US-014, US-015, US-018 |
| `app/routers/reconstruction.py` | Paper reconstruction API endpoints | US-016 |
| `app/routers/document_sections.py` | Document sections API endpoints | US-017 |
| `app/models/exam_sets.py` | Pydantic models for exam sets | US-014, US-015 |
| `app/models/document_sections.py` | Pydantic models for document sections | US-017 |
| `app/models/reconstruction.py` | Pydantic models for reconstruction responses | US-016 |
| `app/utils/normalizers.py` | Subject, grade, paper, session normalization functions | US-003, US-004, US-005, US-006 |
| `scripts/run_batch_matcher.py` | CLI script to trigger batch matching job | US-013 |

### Modified Files - PDF-Extraction Project

| File Path | Changes | User Story |
|-----------|---------|------------|
| `app/main.py` | Register exam_sets, reconstruction, document_sections routers | US-014, US-016, US-017 |
| `app/services/pdf_extractor.py` | Call section_extractor before question extraction | US-019 |
| `app/db/extractions.py` | Link to exam_set after extraction | US-020 |
| `app/db/memo_extractions.py` | Link to exam_set after extraction | US-020 |

### Modified Files - Academy Scrapper Project (ValidationAgent)

| File Path | Changes | User Story |
|-----------|---------|------------|
| `ValidationAgent/validate_worker.py` | Call exam matching after validation completes | US-020 |
| `ValidationAgent/supabase_client.py` | Add exam_set_id to scraped_files.metadata | US-020 |

### Database Migrations Summary

| Migration | Tables Created | Purpose |
|-----------|----------------|---------|
| 014 | exam_sets | QP-Memo linking with match metadata |
| 015 | document_sections | Store extracted sections (cover, instructions, etc.) |
| 016 | document_versions | Track duplicate documents with version history |

### Folder Structure After Implementation

```
app/
├── db/
│   ├── exam_sets.py           # NEW
│   ├── document_sections.py   # NEW
│   └── document_versions.py   # NEW
├── models/
│   ├── exam_sets.py           # NEW
│   ├── document_sections.py   # NEW
│   └── reconstruction.py      # NEW
├── routers/
│   ├── exam_sets.py           # NEW
│   ├── reconstruction.py      # NEW
│   └── document_sections.py   # NEW
├── services/
│   ├── exam_matcher.py        # NEW
│   ├── section_extractor.py   # NEW
│   └── batch_matcher.py       # NEW
├── utils/
│   └── normalizers.py         # NEW
└── main.py                    # MODIFIED

migrations/
├── 014_exam_sets.sql          # NEW
├── 015_document_sections.sql  # NEW
└── 016_document_versions.sql  # NEW

scripts/
└── run_batch_matcher.py       # NEW
```

## Success Metrics

- 95%+ automatic matching accuracy (verified against manual review)
- 100% of validated documents linked to an exam set
- < 30% increase in processing time from section extraction
- Zero data loss in reconstruction (all extracted content queryable)
- < 1% duplicate detection false positives

## Open Questions

- Should we extract mark breakdown tables as separate section type?
- How do we handle multi-language papers (English and Afrikaans versions)?
- Should information sheets be deduplicated across papers (same formulae for Math P1 and P2)?
- What is the retention policy for non-active document versions?

---

*PRD Created: 2026-02-03*
*Based on: PAPER_MATCHING_PLAN.md*
*Separate workstream from Unified PDF Extraction System*
