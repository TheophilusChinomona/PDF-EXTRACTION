# PRD: Memo Extraction Sidecar

## Introduction

The PDF Extraction service currently extracts **question papers** into structured JSON using a hybrid pipeline (OpenDataLoader + Gemini API). This PRD covers adding a parallel **memo/marking guideline extraction** module -- a "sidecar" that shares infrastructure but uses memo-specific prompts, schemas, and a dedicated database table. The goal is to archive marking guidelines from all SA matric subjects in a structured, queryable format.

## Goals

- Extract marking guidelines from any SA matric subject into structured JSON
- Capture ALL valid answers listed in memos (not just the minimum required)
- Preserve marker instructions ("Mark the first TWO only", "Accept any order")
- Handle all memo structures: Section A (key-value), Section B (fact lists), Section C (essays)
- Store memo extractions in a dedicated Supabase table
- Provide both API and standalone CLI access to the extraction pipeline
- Reuse existing hybrid pipeline infrastructure (OpenDataLoader, caching, retry)

## User Stories

### US-001: Create Memo Pydantic Models
**Priority:** 1

Create `app/models/memo_extraction.py` with models extending `GeminiCompatibleModel`:
- `EssayStructure`: introduction (List[str]), body_sections (List[Dict]), conclusion (List[str])
- `MemoQuestion`: id, text, type, model_answers (Union[List[str], Dict[str, List[str]]]), answers, structured_answer, marks, max_marks, marker_instruction, notes, essay_structure
- `MemoSection`: section_id (str), questions (List[MemoQuestion])
- `MarkingGuideline`: meta (Dict), sections (List[MemoSection]), processing_metadata (Dict)
- All optional fields default to None
- Must validate against `Sample PDFS/outputs/Sample output-marking guideline.json`

### US-002: Create Memo Extraction Service
**Priority:** 2

Create `app/services/memo_extractor.py` mirroring pdf_extractor.py:
- `MEMO_EXTRACTION_SYSTEM_INSTRUCTION` from `Sample PDFS/outputs/memo sample system prompt.md`
- Separate memo cache: `_MEMO_CACHE_NAME` global + `get_or_create_memo_cache()`
- `extract_memo_with_vision_fallback()` -- uploads PDF to Gemini Files API
- `extract_memo_data_hybrid()` -- main async hybrid pipeline
- `PartialMemoExtractionError` exception class
- Import (not copy) `_remove_additional_properties()` and `_estimate_token_count()` from pdf_extractor.py
- System prompt rules: extract ALL valid answers, capture marker instructions, skip preamble

### US-003: Add CLI Entry Point for Memo Extraction
**Priority:** 3

Add `if __name__ == "__main__"` block to memo_extractor.py:
- Accepts file path as CLI argument
- Prints JSON output to stdout
- Auto-saves to `{input_filename}_memo_result.json` alongside input PDF
- Handles missing args and errors gracefully

### US-004: Create Memo Database Functions
**Priority:** 4

Create `app/db/memo_extractions.py` mirroring `app/db/extractions.py`:
- `create_memo_extraction()` -- insert MarkingGuideline into memo_extractions table
- `get_memo_extraction()` -- retrieve by UUID
- `check_memo_duplicate()` -- check file_hash
- `update_memo_extraction_status()` -- update status + optional error
- `list_memo_extractions()` -- paginated list with status filter
- `update_memo_extraction()` -- full update for retries

### US-005: Add doc_type Routing to API
**Priority:** 5

Modify `POST /api/extract` to accept `doc_type` parameter:
- `doc_type: str = Form("question_paper")` -- default preserves backward compatibility
- Validates `doc_type` is `"question_paper"` or `"memo"` (400 otherwise)
- Routes to memo pipeline when `doc_type == "memo"`
- Memo results stored in `memo_extractions` table
- Existing behavior unchanged when doc_type omitted

### US-006: Create Supabase memo_extractions Table Schema
**Priority:** 6

SQL migration `migrations/004_create_memo_extractions_table.sql`:
- Columns: id (UUID PK), file_name, file_size_bytes, file_hash (unique, indexed), status (indexed), processing_method, quality_score, subject, year, session, grade, total_marks, sections (JSONB), processing_metadata (JSONB), processing_time_seconds, cost_estimate_usd, webhook_url, retry_count, error_message, created_at, updated_at
- Index on file_hash for deduplication
- Index on status for filtered queries

## Non-Goals

- No auto-grading logic (extraction only)
- No linking between question paper and memo extractions (future feature)
- No batch memo processing endpoint (single-file only)
- No UI (API and CLI only)
- No custom prompt per subject (single generic prompt)

## Technical Considerations

- Reuse `_remove_additional_properties()` from pdf_extractor.py (import, not duplicate)
- Reuse `extract_pdf_structure()` from opendataloader_extractor.py
- Reuse `@retry_with_backoff()` from app/utils/retry.py
- Reuse `get_gemini_client()` from app/services/gemini_client.py
- MarkingGuideline uses Union types -- ensure Gemini schema compatibility
- Memo PDFs often have tabular layouts -- OpenDataLoader table extraction is critical
- memo_extractions table is independent from extractions (no foreign keys)

## Reference Files

- Sample output: `Sample PDFS/outputs/Sample output-marking guideline.json`
- System prompt: `Sample PDFS/outputs/memo sample system prompt.md`
- Schema reference: `Sample PDFS/outputs/memo-sample-schemas.py`
- Existing extractor: `app/services/pdf_extractor.py`
- Existing DB functions: `app/db/extractions.py`
- Existing models: `app/models/extraction.py`
