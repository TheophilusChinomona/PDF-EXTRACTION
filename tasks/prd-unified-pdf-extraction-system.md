# PRD: Unified PDF Extraction System

## Implementation Location

This PRD spans **two codebases** that must be modified together:

| Codebase | Path | Language | Primary Changes |
|----------|------|----------|-----------------|
| **PDF-Extraction** | `C:\Users\theoc\Desktop\Work\PDF-Extraction` | Python/FastAPI | Migrations, API endpoints, PGMQ/Firebase clients |
| **Academy Scrapper** | `C:\Users\theoc\Desktop\Work\Academy Scrapper` | C#/.NET + Python | ValidationAgent updates, API client, DB migrations |

**Start with:** PDF-Extraction (database migrations and API endpoints)
**Then:** Academy Scrapper (ValidationAgent integration and API client)

---

## Introduction

The PDF extraction pipeline currently spans two separate codebases with inconsistent ID schemes:
- **Academy Scrapper** (C#/.NET): URL discovery, crawling, PDF download, Firebase storage
- **PDF-Extraction** (Python/FastAPI): Document classification, extraction pipeline, Gemini/OpenDataLoader

This creates a critical ID mismatch where `parsed_questions.file_id` (TEXT) and `extractions.scraped_file_id` (UUID) reference the same `scraped_files` table using different key types, making it impossible to trace a document's complete journey.

This PRD defines a unified system where a single UUID (`scraped_file_id`) tracks documents from URL discovery through validation, with a validation-first approach that rejects non-academic documents early to save API tokens.

## Goals

- Establish single UUID (`scraped_file_id`) as the authoritative document identifier across all tables
- Implement validation-first pipeline to reject non-academic documents before extraction (saving ~20% tokens)
- Automate file renaming based on extracted metadata (e.g., `Grade-12-Mathematics-P1-2025-Nov.pdf`)
- Create unified database schema shared between Academy Scrapper and PDF-Extraction
- Enable PGMQ-based async queue processing for validation and extraction
- Support big-bang migration of existing data to unified ID scheme
- Achieve full end-to-end integration in a single release

## User Stories

### US-001: Add scraped_file_id UUID to Academy Scrapper tables
**Description:** As a developer, I need all Academy Scrapper tables to use UUID foreign keys so documents can be tracked consistently.

**Acceptance Criteria:**
- [ ] `parsed_questions` table has `scraped_file_id UUID` column referencing `scraped_files(id)`
- [ ] `parser_jobs` table has `scraped_file_id UUID` column referencing `scraped_files(id)`
- [ ] Migration script populates UUID from existing `file_id` TEXT lookup
- [ ] Legacy `file_id` TEXT column retained for backward compatibility
- [ ] Migration runs successfully on production database

### US-002: Create validation_results table with UUID FK
**Description:** As a developer, I need validation results linked via UUID so validation status is queryable alongside extraction data.

**Acceptance Criteria:**
- [ ] `validation_results` table created with `scraped_file_id UUID` as primary FK
- [ ] Table includes: status, confidence_score, subject, grade, year, paper_type, paper_number, session, syllabus
- [ ] Status check constraint: 'correct', 'rejected', 'review_required', 'pending', 'error'
- [ ] Indexes on `scraped_file_id`, `status`, and `confidence_score`
- [ ] Migration runs successfully

### US-003: Create validation_jobs table for batch tracking
**Description:** As a developer, I need to track validation job progress for monitoring and debugging.

**Acceptance Criteria:**
- [ ] `validation_jobs` table created with progress tracking fields
- [ ] Fields include: total_files, processed_files, accepted_files, rejected_files, review_required_files, failed_files
- [ ] Status check constraint: 'pending', 'queued', 'running', 'completed', 'failed', 'paused', 'cancelled'
- [ ] Migration runs successfully

### US-004: Create extraction_jobs unified job tracking table
**Description:** As a developer, I need a single job tracking table that replaces the legacy `parser_jobs` table.

**Acceptance Criteria:**
- [ ] `extraction_jobs` table created with `scraped_file_id UUID` FK
- [ ] Fields include: job_type, status, priority, started_at, completed_at, items_extracted, errors_count
- [ ] job_type check: 'extraction', 'memo_extraction', 'parsing'
- [ ] Data migrated from legacy `parser_jobs` table
- [ ] Migration runs successfully

### US-005: Implement automatic validation trigger on download
**Description:** As a system, I want validation to automatically start when a PDF is downloaded so no manual intervention is needed.

**Acceptance Criteria:**
- [ ] Database trigger fires when `scraped_files.status` changes to 'downloaded'
- [ ] Trigger enqueues message to `validation_queue` via PGMQ
- [ ] Message contains: `scraped_file_id`, `storage_url`, `file_name`, `triggered_at`
- [ ] `scraped_files.status` updated to 'validating'
- [ ] Trigger tested with INSERT and UPDATE operations

### US-006: Implement lenient validation decision logic
**Description:** As a system, I want to auto-approve documents with confidence >= 40% (flagged if < 70%) to reduce manual review burden.

**Acceptance Criteria:**
- [ ] Documents with confidence >= 70% marked as 'validated' (proceed to extraction)
- [ ] Documents with confidence 40-69% marked as 'validated' with `low_confidence` flag
- [ ] Documents with confidence < 40% marked as 'rejected'
- [ ] `scraped_files` updated with appropriate status
- [ ] Low confidence flag stored in `validation_results.metadata`

### US-007: Implement file rename after validation
**Description:** As a system, I want validated files renamed using standardized naming so they're human-readable in Firebase Storage.

**Acceptance Criteria:**
- [ ] Files renamed from `{uuid}.pdf` to `Grade-{grade}-{subject}-P{paper}-{year}-{session}.pdf`
- [ ] Firebase Storage copy + delete operation for rename
- [ ] `scraped_files.storage_path` and `file_name` updated with new values
- [ ] Duplicate filenames handled with UUID suffix (e.g., `Grade-12-Math-P1-2025-Nov-{uuid8}.pdf`)
- [ ] Memos include `-Memo` suffix in filename

### US-008: Implement extraction trigger after validation
**Description:** As a system, I want validated documents automatically queued for extraction so the pipeline flows without manual steps.

**Acceptance Criteria:**
- [ ] Database trigger fires when `validation_results.status` changes to 'correct'
- [ ] Trigger enqueues message to `extraction_queue` via PGMQ
- [ ] Message includes: `scraped_file_id`, `storage_url`, `document_type`, metadata (subject, grade, year, session)
- [ ] `scraped_files.status` updated to 'queued_for_extraction'
- [ ] Extraction can skip classification step since doc_type known from validation

### US-009: Create Firebase Storage extraction endpoint
**Description:** As an API consumer, I want to trigger extraction from a Firebase Storage URL so Academy Scrapper can call PDF-Extraction.

**Acceptance Criteria:**
- [ ] `POST /api/extract/from-storage` endpoint created
- [ ] Accepts: `scraped_file_id`, `storage_url`, `doc_type` (optional), `webhook_url` (optional)
- [ ] Downloads PDF from Firebase Storage
- [ ] Skips classification if `doc_type` provided (saves ~200ms per document)
- [ ] Returns 202 with `extraction_id` and `status: processing`
- [ ] Webhook callback sent on completion/failure

### US-010: Create validation API endpoints
**Description:** As an API consumer, I want to query validation status and trigger batch validation.

**Acceptance Criteria:**
- [ ] `POST /api/validation/batch` - trigger batch validation for specified files
- [ ] `GET /api/validation/{job_id}` - get validation job status with progress counts
- [ ] `GET /api/validation/{job_id}/progress` - fast polling endpoint with ETA
- [ ] `GET /api/validation/result/{scraped_file_id}` - get validation result for single document
- [ ] All endpoints return proper JSON responses with documented schema

### US-011: Create review queue API endpoints
**Description:** As an admin, I want to manage documents requiring manual review so I can approve/reject edge cases.

**Acceptance Criteria:**
- [ ] `GET /api/validation/review-queue` - list documents pending review with pagination
- [ ] `POST /api/validation/review/{scraped_file_id}/resolve` - approve or reject with notes
- [ ] Resolution updates `validation_results.status` and triggers extraction if approved
- [ ] Metadata override supported for manual correction before extraction
- [ ] Resolved documents removed from review queue

### US-012: Update scraped_files status flow
**Description:** As a developer, I need the status field to support the full validation-first pipeline.

**Acceptance Criteria:**
- [ ] Status check constraint updated to include: 'pending', 'downloading', 'downloaded', 'validating', 'validated', 'queued_for_extraction', 'extracting', 'completed', 'review_required', 'rejected', 'failed'
- [ ] New `validation_status` column added: 'unvalidated', 'queued', 'validated', 'rejected', 'review_required', 'failed'
- [ ] Migration preserves existing status values
- [ ] Status transitions documented

### US-013: Migrate existing data to unified IDs
**Description:** As a developer, I need all existing records to have UUID foreign keys populated so queries work consistently.

**Acceptance Criteria:**
- [ ] Migration script populates `scraped_file_id` in `parsed_questions` from `file_id` lookup
- [ ] Migration script populates `scraped_file_id` in `parser_jobs` from `file_id` lookup
- [ ] No orphaned records (all have valid UUID FK)
- [ ] Verification query confirms 100% population
- [ ] Rollback script available if needed

### US-014: Create PGMQ client for PDF-Extraction
**Description:** As a developer, I need a PGMQ client in Python to consume from validation and extraction queues.

**Acceptance Criteria:**
- [ ] `app/services/pgmq_client.py` created with send/read/delete/archive operations
- [ ] Connection pooling configured for async operations
- [ ] Visibility timeout handling for message locking
- [ ] Dead letter queue support for failed messages
- [ ] Integration tested with validation_queue and extraction_queue

### US-015: Create Firebase Storage client for PDF-Extraction
**Description:** As a developer, I need to download PDFs from Firebase Storage for extraction.

**Acceptance Criteria:**
- [ ] `app/services/firebase_client.py` created with download and rename operations
- [ ] Supports `gs://` URL format
- [ ] Authentication via service account JSON
- [ ] Streaming download for large files
- [ ] Error handling for missing files and permission errors

## Functional Requirements

- FR-1: All tables referencing `scraped_files` must use `scraped_file_id UUID` as the foreign key
- FR-2: Legacy `file_id TEXT` columns retained for backward compatibility but UUID is authoritative
- FR-3: Validation automatically triggers when a document's status changes to 'downloaded'
- FR-4: Documents with confidence < 40% are rejected and excluded from extraction
- FR-5: Documents with confidence 40-69% are approved with a `low_confidence` flag
- FR-6: Documents with confidence >= 70% proceed directly to extraction
- FR-7: Validated files are renamed in Firebase Storage using pattern: `Grade-{grade}-{subject}-P{paper}-{year}-{session}.pdf`
- FR-8: Extraction queue receives document type from validation (skipping re-classification)
- FR-9: All status transitions logged with timestamps in respective tables
- FR-10: PGMQ queues used for async processing: `validation_queue`, `extraction_queue`, `validation_dead_letter`
- FR-11: Webhook callbacks sent on extraction completion/failure if webhook_url provided
- FR-12: Review queue populated for documents requiring manual intervention
- FR-13: Admin can override validation results and correct metadata before extraction

## Non-Goals (Out of Scope)

- Real-time streaming updates (webhook callbacks are sufficient)
- UI for review queue (API only in this phase)
- Automatic retry logic for failed extractions (manual re-queue supported)
- Multi-tenant isolation (single tenant system)
- Firebase to Supabase storage migration (Firebase remains primary storage)
- Changes to the extraction algorithm itself (only integration changes)
- Academy Scrapper C# code changes beyond API client integration

## Technical Considerations

### Database
- Supabase PostgreSQL with PGMQ extension
- Migrations run via Supabase Dashboard SQL Editor (no CLI available)
- Foreign key constraints with ON DELETE CASCADE where appropriate

### Integration Points
- Academy Scrapper calls `POST /api/extract/from-storage` after PDF download
- ValidationAgent Python worker consumes from `validation_queue`
- PDF-Extraction worker consumes from `extraction_queue`
- Firebase Storage for PDF storage and retrieval

### Performance
- 10 concurrent validation workers (ThreadPoolExecutor)
- Batch extraction up to 100 documents
- PGMQ visibility timeout for message locking (prevents duplicate processing)
- Connection pooling for database and Firebase clients

### Migration Strategy
- Big bang migration: migrate all existing data at once
- Run migration during low-traffic window
- Verification queries before and after
- Rollback scripts prepared but not expected to be needed

## Files to Create/Modify

### New Files - PDF-Extraction Project

| File Path | Purpose | User Story |
|-----------|---------|------------|
| `migrations/009_unify_id_tracking.sql` | Add scraped_file_id UUID FKs to Academy tables | US-001 |
| `migrations/010_validation_tables.sql` | Create validation_results, validation_jobs tables | US-002, US-003 |
| `migrations/011_validation_triggers.sql` | Auto-trigger validation on download, extraction on validation | US-005, US-008 |
| `migrations/012_extraction_jobs.sql` | Create unified extraction_jobs table | US-004 |
| `migrations/013_status_updates.sql` | Update scraped_files status check constraint | US-012 |
| `app/services/pgmq_client.py` | PGMQ queue operations (send/read/delete/archive) | US-014 |
| `app/services/firebase_client.py` | Firebase Storage download and rename operations | US-015 |
| `app/routers/storage_extraction.py` | `POST /api/extract/from-storage` endpoint | US-009 |
| `app/routers/validation.py` | Validation API endpoints (batch, status, progress) | US-010, US-011 |
| `app/db/validation_results.py` | CRUD operations for validation_results table | US-002 |
| `app/db/validation_jobs.py` | CRUD operations for validation_jobs table | US-003 |
| `app/models/validation.py` | Pydantic models for validation requests/responses | US-010 |

### Modified Files - PDF-Extraction Project

| File Path | Changes | User Story |
|-----------|---------|------------|
| `app/main.py` | Register validation router, add PGMQ lifespan hooks | US-010 |
| `app/config.py` | Add PGMQ connection settings, Firebase config | US-014, US-015 |
| `app/db/extractions.py` | Accept scraped_file_id in create, skip classification option | US-009 |
| `app/db/memo_extractions.py` | Accept scraped_file_id in create | US-009 |
| `app/services/pdf_extractor.py` | Add skip_classification option when doc_type known | US-009 |
| `app/services/document_classifier.py` | Allow bypass when doc_type provided | US-009 |

### New Files - Academy Scrapper Project (ValidationAgent)

| File Path | Purpose | User Story |
|-----------|---------|------------|
| `ValidationAgent/file_renamer.py` | Firebase Storage rename logic | US-007 |
| `database/migrations/phase3_unification.sql` | ID standardization for Academy tables | US-001 |

### Modified Files - Academy Scrapper Project

| File Path | Changes | User Story |
|-----------|---------|------------|
| `ValidationAgent/supabase_client.py` | Use scraped_file_id (UUID) as primary FK | US-006 |
| `ValidationAgent/validate_worker.py` | Read from unified PGMQ queue, add file rename step | US-005, US-007 |
| `ValidationAgent/validate_gemini.py` | Include scraped_file_id in output | US-006 |
| `ValidationAgent/config.py` | Add PGMQ queue configuration | US-005 |
| `Services/ExtractionDb/SupabaseParsedQuestionsService.cs` | Use scraped_file_id (UUID) FK | US-001 |
| `Services/ExtractionDb/SupabaseScrapedFilesService.cs` | Return UUID for extraction calls | US-001 |
| `Services/DirectPageScraperService.cs` | Call PDF-Extraction API after download | US-009 |
| `Services/ExtractionApiClient.cs` | New API client for PDF-Extraction service | US-009 |

### Database Migrations Summary

| Migration | Tables Affected | Purpose |
|-----------|-----------------|---------|
| 009 | parsed_questions, parser_jobs | Add scraped_file_id UUID FK |
| 010 | validation_results, validation_jobs | Create validation tables with UUID FKs |
| 011 | scraped_files, validation_results | Add triggers for auto-validation/extraction |
| 012 | extraction_jobs | Create unified job tracking table |
| 013 | scraped_files | Update status check constraint, add validation_status |
| phase3 (Academy) | scraped_files | Add validation_status column |

## Success Metrics

- 100% of documents trackable by single UUID from discovery to completion
- 20%+ reduction in Gemini API costs from validation-first rejections
- Zero orphaned records in any table
- < 5 second latency from download completion to validation start
- 95%+ validation accuracy (verified against manual review)
- End-to-end document processing time < 60 seconds average

## Open Questions

- Should we add a cost_tracking table for unified API cost monitoring?
- What is the retention policy for rejected documents in Firebase Storage?
- Should validation results be cached to avoid re-validating duplicate uploads?
- How should we handle documents that fail extraction after passing validation?

---

*PRD Created: 2026-02-03*
*Based on: UNIFICATION_PLAN.md*
