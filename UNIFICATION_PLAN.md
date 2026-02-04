# Unified PDF Extraction System - Implementation Plan

> **Goal**: Create a unified system where a document's ID is consistent from URL discovery through extraction, with a single database schema and streamlined pipeline.

---

## Executive Summary

This plan unifies two codebases:
- **Academy Scrapper** (C#/.NET) - URL discovery, crawling, PDF download, Firebase storage
- **PDF-Extraction** (Python/FastAPI) - Document classification, extraction pipeline, Gemini/OpenDataLoader

**Key Outcome**: A single document ID tracks from URL discovery → download → Firebase storage → extraction → parsed questions.

---

## 1. Current State Analysis

### Academy Scrapper (Source System)
| Component | Technology | Tables |
|-----------|------------|--------|
| URL Discovery | C# Crawler | discovered_urls (Firestore) |
| PDF Download | HttpClient/HtmlAgilityPack | scraped_files |
| Storage | Firebase Storage | gs://scrapperdb-f854d/ |
| Parser Queue | PGMQ | parser_queue_high/normal/low |
| Extraction | ExamParserAgent (Gemini 2.5 Flash) | parsed_questions, parser_jobs |
| Database | Supabase + Firebase (dual-write migration) | phase2_pgmq_schema |

### PDF-Extraction (Target Extraction Service)
| Component | Technology | Tables |
|-----------|------------|--------|
| Document Classification | Gemini + heuristics | - |
| Hybrid Extraction | OpenDataLoader + Gemini 3 Flash | extractions, memo_extractions |
| Batch Processing | FastAPI async | batch_jobs |
| **Gemini Batch API** | Validation + extraction for 100+ files (50% cost, ~24h) | gemini_batch_jobs |
| Review Queue | Manual review | review_queue |
| Database | Supabase PostgreSQL | migrations including 018 (gemini_batch_jobs) |

### Critical ID Mismatch Issue
```
Academy Scrapper:
  parsed_questions.file_id (TEXT) → scraped_files.file_id (TEXT)

PDF-Extraction:
  extractions.scraped_file_id (UUID) → scraped_files.id (UUID)
```
**These use different key types to reference the same table!**

---

## 2. Unified Document Flow

> **Key Design Decision**: Validation happens BEFORE extraction to avoid wasting tokens on non-academic documents.

```
┌────────────────────────────────────────────────────────────────────┐
│ PHASE 1: URL DISCOVERY (Academy Scrapper)                          │
├────────────────────────────────────────────────────────────────────┤
│ • Crawler discovers PDF URLs                                        │
│ • Generate: source_url_hash (for deduplication)                    │
│ • Store: discovered_urls table                                      │
│ • Output: url_id (UUID) - first ID in chain                        │
│ • Status: 'discovered'                                              │
└────────────────────────────────────────────────────────────────────┘
                                ↓
┌────────────────────────────────────────────────────────────────────┐
│ PHASE 2: DOWNLOAD & STORAGE (Academy Scrapper)                     │
├────────────────────────────────────────────────────────────────────┤
│ • Download PDF from URL                                             │
│ • Generate: scraped_file_id (UUID) - PRIMARY DOCUMENT ID           │
│ • Calculate: file_hash (SHA-256 for deduplication)                 │
│ • Upload: Firebase Storage → gs://bucket/{domain}/{uuid}.pdf       │
│   (temporary name using UUID, will be renamed after validation)    │
│ • Store: scraped_files table with scraped_file_id                  │
│ • Link: url_id → scraped_file_id (foreign key)                     │
│ • Status: 'downloaded'                                              │
│ • 🔄 ASYNC: Can download more PDFs while validation runs           │
└────────────────────────────────────────────────────────────────────┘
                                ↓ (automatic trigger)
┌────────────────────────────────────────────────────────────────────┐
│ PHASE 3: VALIDATION FIRST (ValidationAgent - Python Worker)        │
├────────────────────────────────────────────────────────────────────┤
│ • Auto-enqueue: scraped_file_id to validation_queue                │
│ • Message: { scraped_file_id, storage_url }                        │
│ • Validate with Gemini Vision (gemini-2.5-flash-lite):             │
│   - Document type (Question Paper, Memo, Study Guide, Other)       │
│   - Academic legitimacy (formal exam vs marketing material)        │
│   - Visual markers (DBE/IEB logos, marks in brackets, headers)     │
│   - Metadata extraction (subject, grade, year, session, syllabus)  │
│ • Confidence scoring: 0-100                                         │
│ • Store: validation_results with scraped_file_id FK                │
│ • 🔄 ASYNC: 10 concurrent validation workers                        │
│                                                                     │
│ ⚡ EARLY REJECTION: Non-academic docs rejected HERE (saves tokens)  │
│   - confidence < 40 → 'rejected' (marketing, study guides, etc.)   │
│   - confidence 40-69 → 'review_required' (manual review queue)     │
│   - confidence ≥ 70 → 'validated' (proceed to rename & extract)    │
└────────────────────────────────────────────────────────────────────┘
                                ↓
┌────────────────────────────────────────────────────────────────────┐
│ PHASE 4: FILE RENAME (Based on Extracted Metadata)                 │
├────────────────────────────────────────────────────────────────────┤
│ • Only for validated documents (confidence ≥ 70)                   │
│ • Rename file in Firebase Storage:                                  │
│   OLD: gs://bucket/{domain}/{uuid}.pdf                              │
│   NEW: gs://bucket/{domain}/Grade-{grade}-{subject}-P{paper}-      │
│        {year}-{session}.pdf                                         │
│                                                                     │
│ • Example: Grade-12-Mathematics-P1-2025-Nov.pdf                    │
│ • Update: scraped_files.storage_path with new path                 │
│ • Update: scraped_files.file_name with standardized name           │
│ • Status: 'validated' (ready for extraction)                       │
└────────────────────────────────────────────────────────────────────┘
                                ↓
┌────────────────────────────────────────────────────────────────────┐
│ PHASE 5: EXTRACTION QUEUE (Only Validated Docs)                    │
├────────────────────────────────────────────────────────────────────┤
│ • Enqueue: scraped_file_id to extraction_queue                     │
│ • Message: { scraped_file_id, storage_url, doc_type, metadata }    │
│ • doc_type already known from validation (question_paper or memo)  │
│ • Create: extraction_jobs record (status: queued)                  │
│ • Status: 'queued_for_extraction'                                   │
│ • 🔄 ASYNC: Can validate new docs while extracting others          │
└────────────────────────────────────────────────────────────────────┘
                                ↓
┌────────────────────────────────────────────────────────────────────┐
│ PHASE 6: EXTRACTION (PDF-Extraction Service)                       │
├────────────────────────────────────────────────────────────────────┤
│ • Consume from extraction_queue                                     │
│ • Download PDF from Firebase Storage (renamed file)                │
│ • doc_type already known → skip classification step                 │
│ • Extract: OpenDataLoader → quality routing → Gemini               │
│   - Question papers → FullExamPaper with QuestionGroups            │
│   - Memos → MarkingGuideline with MemoSections                     │
│ • Store: extractions/memo_extractions with scraped_file_id FK      │
│ • Status: 'extracted'                                               │
│ • 🔄 ASYNC: Multiple extractions can run in parallel               │
└────────────────────────────────────────────────────────────────────┘
                                ↓
┌────────────────────────────────────────────────────────────────────┐
│ PHASE 7: FINAL OUTPUT (Ready for Consumption)                      │
├────────────────────────────────────────────────────────────────────┤
│ • Questions in: parsed_questions (scraped_file_id FK)              │
│ • Extraction in: extractions/memo_extractions                      │
│ • Validation in: validation_results                                 │
│ • All linked by: scraped_file_id (UUID)                            │
│ • File properly named: Grade-12-Mathematics-P1-2025-Nov.pdf        │
│ • Status: 'completed' = ready for API consumption                  │
└────────────────────────────────────────────────────────────────────┘
```

### Status Flow Diagram
```
discovered → downloading → downloaded → validating → validated → queued → extracting → completed ✓
                 ↓              ↓            ↓                       ↓          ↓
               failed        failed     rejected              failed       failed
                                            ↓
                                    review_required
```

### Async Operations (Parallel Processing)

The pipeline supports concurrent operations:

| Operation | Parallelism | Notes |
|-----------|-------------|-------|
| Download PDFs | Multiple simultaneous downloads | HttpClient connection pooling |
| Validation | 10 concurrent workers | ThreadPoolExecutor in ValidationAgent |
| Extraction | Batch processing (up to 100) | Can run while new docs validate |
| Queue processing | PGMQ visibility timeout | Messages locked during processing |

**Example Async Flow:**
```
Time →
Download: [PDF1] [PDF2] [PDF3] [PDF4] [PDF5] ...
Validate:      [PDF1] [PDF2] [PDF3] [PDF4] ...
Rename:              [PDF1] [PDF2] [PDF3] ...
Extract:                   [PDF1] [PDF2] ...
```

### File Naming Convention

**Standard Pattern:** `Grade-{grade}-{subject}-P{paper}-{year}-{session}.pdf`

| Field | Source | Example | Notes |
|-------|--------|---------|-------|
| grade | validation_results.grade | 12 | INTEGER only (not "Grade 12") |
| subject | validation_results.subject | Mathematics | TEXT |
| paper | validation_results.paper_number | 1, 2, 3 | INTEGER only (not "P1") |
| year | validation_results.year | 2025 | INTEGER |
| session | validation_results.session | Nov, Jun | TEXT |

**Examples:**
- `Grade-12-Mathematics-P1-2025-Nov.pdf`
- `Grade-11-Physical-Sciences-P2-2024-Jun.pdf`
- `Grade-10-Life-Sciences-P1-2025-Nov-Memo.pdf` (for memos)

**Edge Cases:**
- Missing fields: Use "Unknown" → `Grade-12-Unknown-Subject-P1-2025.pdf`
- Duplicate names: Append UUID suffix → `Grade-12-Mathematics-P1-2025-Nov-{uuid8}.pdf`

---

## 3. Unified Database Schema

### 3.1 Core Tables (Shared)

#### `scraped_files` (Source of Truth)
```sql
CREATE TABLE scraped_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- External References
    file_id TEXT UNIQUE NOT NULL,  -- Legacy compatibility
    firestore_doc_id TEXT,         -- Firebase Firestore reference

    -- File Metadata
    file_name TEXT NOT NULL,
    file_size_bytes BIGINT,
    file_hash VARCHAR(64),         -- SHA-256 for deduplication

    -- Source Information
    source_url TEXT,
    normalized_url TEXT,           -- For duplicate detection
    domain TEXT,

    -- Document Classification
    document_type TEXT CHECK (document_type IN ('question_paper', 'memo', 'unknown')),
    subject TEXT,
    grade INTEGER,                 -- Just the number: 10, 11, 12 (not "Grade 12")
    paper_number INTEGER,          -- Just the number: 1, 2, 3 (not "P1")
    year INTEGER,
    session TEXT,                  -- 'MAY/JUNE' or 'NOV'
    syllabus TEXT,                 -- 'SC' or 'NSC'
    language TEXT DEFAULT 'English',

    -- Storage
    storage_path TEXT,             -- Firebase Storage path
    storage_bucket TEXT DEFAULT 'scrapperdb-f854d.firebasestorage.app',

    -- Pipeline Status
    status TEXT DEFAULT 'pending' CHECK (status IN (
        'pending', 'downloading', 'downloaded', 'queued',
        'extracting', 'extracted', 'failed', 'rejected'
    )),

    -- Tracking
    user_id TEXT,                  -- Firebase Auth user
    user_email TEXT,
    job_id UUID,                   -- Scraper job reference
    downloaded_at TIMESTAMPTZ,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Indexes
CREATE UNIQUE INDEX idx_scraped_files_file_hash_active
    ON scraped_files(file_hash)
    WHERE status NOT IN ('rejected', 'failed');
CREATE INDEX idx_scraped_files_status ON scraped_files(status);
CREATE INDEX idx_scraped_files_document_type ON scraped_files(document_type);
CREATE INDEX idx_scraped_files_composite ON scraped_files(subject, grade, year);
```

### 3.2 Extraction Tables (PDF-Extraction)

#### `extractions` (Exam Papers)
```sql
CREATE TABLE extractions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scraped_file_id UUID NOT NULL REFERENCES scraped_files(id),

    -- Extraction Results
    subject TEXT,
    syllabus TEXT,
    year INTEGER,
    session TEXT,
    grade TEXT,
    language TEXT DEFAULT 'English',
    total_marks INTEGER,

    -- Extracted Content
    groups JSONB,                  -- Array of QuestionGroup objects

    -- Processing Info
    status TEXT DEFAULT 'pending' CHECK (status IN (
        'pending', 'processing', 'completed', 'failed', 'partial'
    )),
    processing_method TEXT CHECK (processing_method IN (
        'hybrid', 'vision_fallback', 'opendataloader_only'
    )),
    quality_score DECIMAL(3,2),
    processing_time_seconds DECIMAL(10,3),
    cost_estimate_usd DECIMAL(10,6),
    retry_count INTEGER DEFAULT 0,

    -- Metadata
    processing_metadata JSONB,
    webhook_url TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    UNIQUE(scraped_file_id)        -- One extraction per file
);
```

#### `memo_extractions` (Marking Guidelines)
```sql
CREATE TABLE memo_extractions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scraped_file_id UUID NOT NULL REFERENCES scraped_files(id),

    -- Extraction Results
    subject TEXT,
    syllabus TEXT,
    year INTEGER,
    session TEXT,
    grade TEXT,
    total_marks INTEGER,

    -- Extracted Content
    sections JSONB,                -- Array of MemoSection objects

    -- Processing Info (same as extractions)
    status TEXT DEFAULT 'pending',
    processing_method TEXT,
    quality_score DECIMAL(3,2),
    processing_time_seconds DECIMAL(10,3),
    cost_estimate_usd DECIMAL(10,6),
    retry_count INTEGER DEFAULT 0,
    processing_metadata JSONB,
    webhook_url TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(scraped_file_id)
);
```

### 3.3 Parser Tables (Academy Scrapper - Updated)

#### `parsed_questions` (Individual Questions)
```sql
CREATE TABLE parsed_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- UNIFIED FK (new)
    scraped_file_id UUID NOT NULL REFERENCES scraped_files(id),

    -- Legacy FK (keep for backward compatibility)
    file_id TEXT REFERENCES scraped_files(file_id),

    -- Link to extraction
    extraction_id UUID REFERENCES extractions(id),

    -- Question Data
    question_number INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    answer_options JSONB,          -- ["A. ...", "B. ...", ...]
    correct_answer TEXT,
    difficulty TEXT,
    topic TEXT,
    marks INTEGER,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_parsed_questions_scraped_file_id ON parsed_questions(scraped_file_id);
CREATE INDEX idx_parsed_questions_file_id ON parsed_questions(file_id);  -- Legacy
CREATE INDEX idx_parsed_questions_extraction_id ON parsed_questions(extraction_id);
```

#### `extraction_jobs` (Unified Job Tracking)
```sql
-- Replaces parser_jobs, provides unified tracking
CREATE TABLE extraction_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scraped_file_id UUID NOT NULL REFERENCES scraped_files(id),

    -- Job Status
    job_type TEXT CHECK (job_type IN ('extraction', 'memo_extraction', 'parsing')),
    status TEXT DEFAULT 'queued' CHECK (status IN (
        'queued', 'processing', 'completed', 'failed', 'cancelled'
    )),
    priority TEXT DEFAULT 'normal' CHECK (priority IN ('high', 'normal', 'low')),

    -- Progress
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    processing_duration_ms INTEGER,

    -- Results
    items_extracted INTEGER DEFAULT 0,  -- questions_parsed equivalent
    errors_count INTEGER DEFAULT 0,
    error_message TEXT,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.4 Review & Batch Tables

```sql
-- Keep review_queue as-is (PDF-Extraction)
-- Keep batch_jobs as-is (PDF-Extraction)

-- Add unified cost tracking
CREATE TABLE cost_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scraped_file_id UUID REFERENCES scraped_files(id),  -- NULLABLE

    service_name TEXT NOT NULL,     -- 'gemini', 'openai', 'opendata'
    operation_type TEXT NOT NULL,   -- 'classification', 'extraction', 'parsing'
    tokens_used INTEGER,
    cost_usd DECIMAL(10,4) NOT NULL,

    timestamp TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);
```

---

## 4. Tables to Consolidate/Remove

### Merge
| Current | New | Action |
|---------|-----|--------|
| `parser_jobs` (Academy) | `extraction_jobs` | Migrate data, then deprecate |
| `queue_state` (Academy) | Keep as-is | Control table, no change |

### Keep Separate (Different Purposes)
| Table | Project | Reason |
|-------|---------|--------|
| `extractions` | PDF-Extraction | Full paper extraction results |
| `parsed_questions` | Academy | Individual question records |
| `question_groups` | Academy | Hierarchical grouping |
| `preprocessed_images` | Academy | Image caching layer |
| `review_queue` | PDF-Extraction | Manual review workflow |
| `batch_jobs` | PDF-Extraction | Batch orchestration |

### Remove/Deprecate
| Table | Action | Reason |
|-------|--------|--------|
| `parser_jobs` | Deprecate after migration | Replaced by `extraction_jobs` |
| Duplicate Firebase collections | Phase out | Supabase is source of truth |

---

## 5. Implementation Phases

### Phase 1: Database Unification (Week 1-2)

#### 1.1 Migration Scripts
```sql
-- Step 1: Update scraped_files with new status values and validation_status
ALTER TABLE scraped_files
DROP CONSTRAINT IF EXISTS scraped_files_status_check;

ALTER TABLE scraped_files
ADD CONSTRAINT scraped_files_status_check CHECK (status IN (
    'pending', 'downloading', 'downloaded', 'validating', 'validated',
    'queued_for_extraction', 'extracting', 'completed',
    'review_required', 'rejected', 'failed'
));

ALTER TABLE scraped_files
ADD COLUMN IF NOT EXISTS validation_status TEXT DEFAULT 'unvalidated';

-- Step 2: Add scraped_file_id UUID FK to Academy Scrapper tables
ALTER TABLE parsed_questions
    ADD COLUMN scraped_file_id UUID REFERENCES scraped_files(id);

ALTER TABLE parser_jobs
    ADD COLUMN scraped_file_id UUID REFERENCES scraped_files(id);

-- Step 3: Populate UUID from file_id lookup
UPDATE parsed_questions pq
SET scraped_file_id = sf.id
FROM scraped_files sf
WHERE pq.file_id = sf.file_id;

-- Step 4: Create extraction_jobs table
CREATE TABLE extraction_jobs (...);

-- Step 5: Add NOT NULL constraint after backfill
ALTER TABLE parsed_questions
    ALTER COLUMN scraped_file_id SET NOT NULL;
```

#### 1.2 Files to Modify
- `PDF-Extraction/migrations/009_unify_id_tracking.sql` (new)
- `Academy Scrapper/database/migrations/phase3_unification.sql` (new)

### Phase 2: Validation Tables & Triggers (Week 2-3)

#### 2.1 Create Validation Tables with UUID FKs
```sql
-- Migration: 010_validation_tables.sql
-- See Section 3.3 for full schema

-- Create validation_results with scraped_file_id (UUID) FK
-- Create validation_jobs for batch tracking
-- Create PGMQ queues: validation_queue, extraction_queue
```

#### 2.2 Create Triggers
```sql
-- Migration: 011_validation_triggers.sql

-- Trigger 1: After download → enqueue to validation_queue
-- Trigger 2: After validation (status='correct') → rename file → enqueue to extraction_queue
-- See Section 3.4-3.6 for trigger implementations
```

#### 2.3 Files to Create
- `PDF-Extraction/migrations/010_validation_tables.sql`
- `PDF-Extraction/migrations/011_validation_triggers.sql`
- `PDF-Extraction/app/db/validation_results.py`
- `PDF-Extraction/app/db/validation_jobs.py`

### Phase 3: Validation Integration (Week 3-4)

#### 3.1 Update ValidationAgent to Use UUID FKs
```python
# ValidationAgent/supabase_client.py
def save_validation_result(self, result: ValidationResult):
    data = {
        'scraped_file_id': result.scraped_file_id,  # UUID (primary FK)
        'file_id': result.file_id,                   # TEXT (legacy)
        'status': result.status,
        'confidence_score': result.confidence,
        'subject': result.subject,
        'grade': result.grade,
        'year': result.year,
        'paper_type': result.paper_type,
        'paper_number': result.paper_number,
        'session': result.session,
        'visual_cues': result.visual_cues,
        # ... rest of fields
    }
    return self.client.table('validation_results').insert(data).execute()
```

#### 3.2 Add File Rename Logic to ValidationAgent
```python
# After successful validation (confidence >= 70):
# 1. Generate standardized filename from metadata
# 2. Rename file in Firebase Storage
# 3. Update scraped_files.storage_path and file_name
# See Section 3.5 for implementation
```

#### 3.3 Files to Modify
- `Academy Scrapper/ValidationAgent/supabase_client.py` - Use UUID FK
- `Academy Scrapper/ValidationAgent/validate_worker.py` - Add file rename step
- `Academy Scrapper/ValidationAgent/file_renamer.py` - New file for rename logic

### Phase 4: Extraction Integration (Week 4-5)

#### 4.1 Create Storage Extraction Endpoint
```python
# PDF-Extraction: New endpoint that consumes from extraction_queue
@router.post("/api/extract/from-storage")
async def extract_from_storage(
    scraped_file_id: UUID,
    storage_url: str,
    doc_type: str,  # Already known from validation
    metadata: dict,  # Subject, grade, year from validation
    webhook_url: Optional[str] = None
):
    """
    Extract from Firebase Storage URL.
    Called after validation completes.
    doc_type already known - skip classification step.
    """
    # Download PDF from Firebase Storage
    pdf_bytes = await download_from_firebase(storage_url)

    # Skip classification (already done in validation)
    # Process through extraction pipeline
    result = await extract_pdf(
        pdf_bytes,
        scraped_file_id,
        doc_type,
        skip_classification=True
    )

    return result
```

#### 4.2 Modify Extraction to Skip Classification
Since validation already determined doc_type, extraction can skip the classification step:
- Saves ~200ms per document
- Reduces Gemini API calls

#### 4.3 Files to Modify
- `PDF-Extraction/app/routers/storage_extraction.py` - New endpoint
- `PDF-Extraction/app/services/firebase_client.py` - Firebase Storage client
- `PDF-Extraction/app/services/pdf_extractor.py` - Add skip_classification option
- `PDF-Extraction/app/services/document_classifier.py` - Allow bypass

### Phase 5: End-to-End Integration (Week 5-6)

#### 5.1 Modify Academy Scrapper Download Flow
```csharp
// After successful PDF download and Firebase upload:
public async Task ProcessDownloadedPdf(ScrapedFile file)
{
    // 1. Upload to Firebase Storage with UUID name
    file.StoragePath = $"gs://bucket/{domain}/{file.Id}.pdf";
    await _firebaseStorage.Upload(file);

    // 2. Insert to scraped_files with status='downloaded'
    // This triggers validation automatically (DB trigger)
    file.Status = "downloaded";
    await _supabaseClient.Insert(file);

    // 3. Validation runs async (Python worker)
    // 4. File renamed after validation
    // 5. Extraction triggered after rename
    // All handled by PGMQ + triggers
}
```

#### 5.2 Remove Duplicate ExamParserAgent Extraction
- **Keep**: Gemini 2.5 Flash preprocessing for image enhancement
- **Remove**: Redundant extraction logic in ExamParserAgent
- **Use**: PDF-Extraction service as single extraction point

### Phase 3: Validation Agent Integration (Week 3-4)

> **Key Change**: Validation now happens BEFORE extraction to avoid wasting tokens on rejected documents.

The Validation Agent is a **Python-based microservice** that uses Gemini Vision to classify documents, extract metadata, and rename files. Currently it runs **manually** - we'll integrate it as an **automatic** step triggered immediately after download.

#### 3.1 Validation Agent Current State

**Components:**
- `validate_worker.py` - Background worker (Firebase Realtime DB + Supabase PGMQ)
- `validate_gemini.py` - Gemini Vision API integration
- `validation_schema.py` - Structured output schema
- `supabase_client.py` - Database operations
- `concurrent_processor.py` - Parallel processing (10 workers)

**Current Tables:**
- `validation_results` - Classification results (status, confidence, metadata)
- `validation_jobs` - Job tracking (progress, counts, errors)
- `file_registry` - File discovery and status tracking

**Current Issue:** Uses `file_id` (TEXT/Firestore doc ID), not `scraped_file_id` (UUID)

#### 3.2 Why Validate First?

| Approach | Tokens Used | Cost |
|----------|-------------|------|
| **Extract First** | Validation + Extraction for ALL docs | High (wastes on rejected) |
| **Validate First** | Validation for ALL + Extraction for VALIDATED only | Low (rejects early) |

**Token Savings Example:**
- 1000 PDFs downloaded
- 200 rejected (marketing, study guides, etc.)
- Extract First: 1000 extractions × ~10K tokens = 10M tokens
- Validate First: 800 extractions × ~10K tokens = 8M tokens
- **Savings: 2M tokens (~20%)**

#### 3.3 Unified Validation Flow (Validate First)

```
┌────────────────────────────────────────────────────────────────────┐
│ DOWNLOAD COMPLETED                                                  │
├────────────────────────────────────────────────────────────────────┤
│ • PDF downloaded from source URL                                    │
│ • Uploaded to Firebase Storage: gs://bucket/{domain}/{uuid}.pdf    │
│ • scraped_files record created with scraped_file_id (UUID)         │
│ • Status: scraped_files.status = 'downloaded'                      │
└────────────────────────────────────────────────────────────────────┘
                                ↓ (automatic trigger on download)
┌────────────────────────────────────────────────────────────────────┐
│ VALIDATION QUEUE (PGMQ)                                            │
├────────────────────────────────────────────────────────────────────┤
│ • Enqueue: scraped_file_id to validation_queue                     │
│ • Message: { scraped_file_id, storage_url }                        │
│ • Create: validation_jobs record (status: queued)                  │
│ • Update: scraped_files.status = 'validating'                      │
└────────────────────────────────────────────────────────────────────┘
                                ↓
┌────────────────────────────────────────────────────────────────────┐
│ VALIDATION WORKER (Python)                                         │
├────────────────────────────────────────────────────────────────────┤
│ • Poll queue (1s interval)                                          │
│ • Read PDF from Firebase Storage (GCS) - no download needed        │
│ • Validate with Gemini Vision (gemini-2.5-flash-lite)              │
│ • Extracts metadata:                                                │
│   - document_type: Question Paper, Memo, Study Guide, Other        │
│   - subject: Mathematics, Physical Sciences, etc.                  │
│   - grade: 10, 11, 12                                               │
│   - year: 2024, 2025                                                │
│   - session: Nov, Jun, Mar                                          │
│   - paper_number: P1, P2, P3                                        │
│   - syllabus: NSC, CAPS, IEB                                        │
│ • Confidence scoring (0-100)                                        │
│ • Visual cues detected (logos, marks in brackets, headers)         │
└────────────────────────────────────────────────────────────────────┘
                                ↓
┌────────────────────────────────────────────────────────────────────┐
│ VALIDATION DECISION                                                 │
├────────────────────────────────────────────────────────────────────┤
│ • confidence ≥ 70 → 'validated' (proceed to rename & extract)      │
│ • confidence 40-69 → 'review_required' (manual review queue)       │
│ • confidence < 40 → 'rejected' (marketing, study guides, etc.)     │
│                                                                     │
│ ⚡ EARLY REJECTION: Rejected docs skip extraction (saves tokens)   │
└────────────────────────────────────────────────────────────────────┘
                                ↓ (only for validated docs)
┌────────────────────────────────────────────────────────────────────┐
│ FILE RENAME (Standard Naming Pattern)                              │
├────────────────────────────────────────────────────────────────────┤
│ • Rename file in Firebase Storage using extracted metadata:        │
│                                                                     │
│   OLD PATH: gs://bucket/{domain}/{uuid}.pdf                         │
│   NEW PATH: gs://bucket/{domain}/Grade-{grade}-{subject}-          │
│             P{paper}-{year}-{session}.pdf                          │
│                                                                     │
│ • Firebase Storage rename operation:                                │
│   1. Copy object to new path                                        │
│   2. Delete original object                                         │
│                                                                     │
│ • Update database:                                                  │
│   - scraped_files.storage_path = new path                           │
│   - scraped_files.file_name = standardized name                     │
│   - scraped_files.subject = extracted subject                       │
│   - scraped_files.grade = extracted grade                           │
│   - scraped_files.year = extracted year                             │
│   - scraped_files.session = extracted session                       │
│   - scraped_files.document_type = question_paper or memo           │
└────────────────────────────────────────────────────────────────────┘
                                ↓
┌────────────────────────────────────────────────────────────────────┐
│ EXTRACTION QUEUE (Only Validated & Renamed)                        │
├────────────────────────────────────────────────────────────────────┤
│ • Enqueue: scraped_file_id to extraction_queue                     │
│ • Message includes validated metadata (skips re-classification)    │
│ • Update: scraped_files.status = 'queued_for_extraction'           │
└────────────────────────────────────────────────────────────────────┘
                                ↓
┌────────────────────────────────────────────────────────────────────┐
│ EXTRACTION (PDF-Extraction Service)                                │
├────────────────────────────────────────────────────────────────────┤
│ • Consume from extraction_queue                                     │
│ • doc_type already known → skip classification (saves tokens)      │
│ • Extract question/memo content with OpenDataLoader + Gemini       │
│ • Store: extractions/memo_extractions with scraped_file_id FK      │
│ • Update: scraped_files.status = 'completed'                       │
└────────────────────────────────────────────────────────────────────┘
                                ↓
┌────────────────────────────────────────────────────────────────────┐
│ REVIEW QUEUE (for review_required docs)                            │
├────────────────────────────────────────────────────────────────────┤
│ • Docs with confidence 40-69 go to manual review                   │
│ • Admin can:                                                        │
│   - Approve → proceeds to rename & extraction                       │
│   - Reject → marked as rejected, no extraction                      │
│   - Override metadata → manual correction before rename             │
└────────────────────────────────────────────────────────────────────┘
```

#### 4.3 Validation Tables (Unified Schema)

```sql
-- Validation Results (updated to use UUID FK)
CREATE TABLE validation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- UNIFIED FK (new)
    scraped_file_id UUID NOT NULL REFERENCES scraped_files(id),

    -- Legacy FK (keep for backward compatibility)
    file_id TEXT REFERENCES scraped_files(file_id),

    -- Link to extraction
    extraction_id UUID REFERENCES extractions(id),

    -- File Info
    filename TEXT,
    gcs_uri TEXT,
    content_hash VARCHAR(64),

    -- Validation Result
    status TEXT CHECK (status IN (
        'correct', 'rejected', 'review_required', 'pending', 'error'
    )),
    validation_method TEXT CHECK (validation_method IN (
        'gemini_vision', 'regex', 'manual'
    )),
    confidence_score INTEGER CHECK (confidence_score BETWEEN 0 AND 100),

    -- Extracted Metadata
    subject TEXT,
    grade INTEGER,                -- Just the number: 10, 11, 12 (not "Grade 12")
    year INTEGER,
    language TEXT,
    paper_type TEXT,              -- 'Question Paper', 'Memorandum', etc.
    paper_number INTEGER,         -- Just the number: 1, 2, 3 (not "P1")
    syllabus TEXT,                -- 'CAPS', 'NSC', 'IEB'
    region TEXT,

    -- Rejection Info
    rejection_reason TEXT,
    validation_logic TEXT,        -- Explanation of decision
    visual_cues JSONB,            -- Array of detected markers

    -- Job Link
    job_id UUID REFERENCES validation_jobs(id),

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_validation_results_scraped_file_id ON validation_results(scraped_file_id);
CREATE INDEX idx_validation_results_status ON validation_results(status);
CREATE INDEX idx_validation_results_confidence ON validation_results(confidence_score);

-- Validation Jobs (updated)
CREATE TABLE validation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Job Info
    job_name TEXT,
    description TEXT,
    source TEXT CHECK (source IN ('automatic', 'manual', 'api', 'batch')),

    -- Status
    status TEXT DEFAULT 'pending' CHECK (status IN (
        'pending', 'queued', 'running', 'completed', 'failed', 'paused', 'cancelled'
    )),

    -- Progress
    total_files INTEGER DEFAULT 0,
    processed_files INTEGER DEFAULT 0,
    accepted_files INTEGER DEFAULT 0,
    rejected_files INTEGER DEFAULT 0,
    review_required_files INTEGER DEFAULT 0,
    failed_files INTEGER DEFAULT 0,

    -- Configuration
    config JSONB DEFAULT '{}'::jsonb,  -- model, max_workers, etc.

    -- Tracking
    created_by TEXT,
    error_message TEXT,

    -- Timestamps
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- PGMQ Queue Setup
SELECT pgmq.create('validation_queue');
SELECT pgmq.create('validation_queue_high');
SELECT pgmq.create('validation_dead_letter');
```

#### 3.4 Automatic Validation Trigger (After Download)

**Database Trigger (Recommended)**
```sql
-- Trigger function to enqueue validation after PDF download
CREATE OR REPLACE FUNCTION trigger_validation_on_download()
RETURNS TRIGGER AS $$
BEGIN
    -- Only trigger when status changes to 'downloaded'
    IF NEW.status = 'downloaded' AND (OLD.status IS NULL OR OLD.status != 'downloaded') THEN
        -- Enqueue to validation queue
        PERFORM pgmq.send(
            'validation_queue',
            jsonb_build_object(
                'scraped_file_id', NEW.id,
                'storage_url', NEW.storage_path,
                'file_name', NEW.file_name,
                'triggered_at', NOW()
            )
        );

        -- Update status to validating
        NEW.status := 'validating';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to scraped_files table
CREATE TRIGGER download_completed_trigger
    BEFORE INSERT OR UPDATE ON scraped_files
    FOR EACH ROW
    EXECUTE FUNCTION trigger_validation_on_download();
```

#### 3.5 File Rename Function

```sql
-- Function to generate standardized filename
CREATE OR REPLACE FUNCTION generate_standardized_filename(
    p_grade INTEGER,           -- Just the number: 12 (not "Grade 12")
    p_subject TEXT,
    p_paper_number INTEGER,    -- Just the number: 1 (not "P1")
    p_year INTEGER,
    p_session TEXT,
    p_document_type TEXT
) RETURNS TEXT AS $$
DECLARE
    v_filename TEXT;
    v_grade TEXT;
    v_subject TEXT;
    v_paper TEXT;
    v_suffix TEXT;
BEGIN
    -- Sanitize inputs - grade and paper_number are now integers
    v_grade := COALESCE(p_grade::TEXT, 'Unknown');
    v_subject := COALESCE(NULLIF(p_subject, ''), 'Unknown-Subject');
    v_paper := COALESCE(p_paper_number::TEXT, '1');

    -- Add memo suffix if applicable
    v_suffix := CASE WHEN p_document_type = 'memo' THEN '-Memo' ELSE '' END;

    -- Build filename: Grade-12-Mathematics-P1-2025-Nov.pdf
    -- Note: P prefix added here, not stored in database
    v_filename := FORMAT(
        'Grade-%s-%s-P%s-%s-%s%s.pdf',
        v_grade,
        REPLACE(v_subject, ' ', '-'),
        v_paper,
        COALESCE(p_year::TEXT, 'Unknown'),
        COALESCE(p_session, 'Unknown'),
        v_suffix
    );

    RETURN v_filename;
END;
$$ LANGUAGE plpgsql;
```

**Python: Firebase Storage Rename**
```python
# ValidationAgent/file_renamer.py
from google.cloud import storage

async def rename_file_in_storage(
    scraped_file_id: UUID,
    old_path: str,
    metadata: ValidationResult,
    db: SupabaseClient
) -> str:
    """Rename file in Firebase Storage based on extracted metadata"""

    # Generate new filename
    new_filename = generate_standardized_filename(
        grade=metadata.grade,
        subject=metadata.subject,
        paper_number=metadata.paper_number,
        year=metadata.year,
        session=metadata.session,
        document_type=metadata.paper_type
    )

    # Extract domain from old path
    # gs://bucket/domain/uuid.pdf → gs://bucket/domain/Grade-12-Math-P1-2025.pdf
    bucket_name = "scrapperdb-f854d.firebasestorage.app"
    domain = old_path.split('/')[3]  # Extract domain from path
    new_path = f"gs://{bucket_name}/{domain}/{new_filename}"

    # Check for duplicates, add suffix if needed
    new_path = await ensure_unique_path(new_path)

    # Firebase Storage rename (copy + delete)
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    old_blob = bucket.blob(old_path.replace(f"gs://{bucket_name}/", ""))
    new_blob_name = new_path.replace(f"gs://{bucket_name}/", "")

    # Copy to new location
    bucket.copy_blob(old_blob, bucket, new_blob_name)

    # Delete original
    old_blob.delete()

    # Update database
    await db.update_scraped_file(
        scraped_file_id,
        storage_path=new_path,
        file_name=new_filename,
        subject=metadata.subject,
        grade=metadata.grade,
        year=metadata.year,
        session=metadata.session,
        document_type=metadata.paper_type
    )

    return new_path

def generate_standardized_filename(
    grade: int,           # Just the number: 12 (not "Grade 12")
    subject: str,
    paper_number: int,    # Just the number: 1 (not "P1")
    year: int,
    session: str,
    document_type: str
) -> str:
    """Generate filename: Grade-12-Mathematics-P1-2025-Nov.pdf"""

    grade_str = str(grade) if grade else "Unknown"
    subject_str = (subject or "Unknown-Subject").replace(" ", "-")
    paper_str = str(paper_number) if paper_number else "1"
    year_str = str(year) if year else "Unknown"
    session_str = session or "Unknown"
    suffix = "-Memo" if document_type == "memo" else ""

    # Note: P prefix added here for display, not stored in database
    return f"Grade-{grade_str}-{subject_str}-P{paper_str}-{year_str}-{session_str}{suffix}.pdf"
```

#### 3.6 Trigger Extraction After Validation

```sql
-- Trigger to enqueue extraction after successful validation
CREATE OR REPLACE FUNCTION trigger_extraction_on_validation()
RETURNS TRIGGER AS $$
BEGIN
    -- Only trigger for validated documents (confidence >= 70)
    IF NEW.status = 'correct' AND (OLD.status IS NULL OR OLD.status != 'correct') THEN
        -- Enqueue to extraction queue
        PERFORM pgmq.send(
            'extraction_queue',
            jsonb_build_object(
                'scraped_file_id', NEW.scraped_file_id,
                'storage_url', (SELECT storage_path FROM scraped_files WHERE id = NEW.scraped_file_id),
                'document_type', NEW.paper_type,
                'metadata', jsonb_build_object(
                    'subject', NEW.subject,
                    'grade', NEW.grade,
                    'year', NEW.year,
                    'session', NEW.session,
                    'syllabus', NEW.syllabus
                ),
                'triggered_at', NOW()
            )
        );

        -- Update scraped_files status
        UPDATE scraped_files
        SET status = 'queued_for_extraction', updated_at = NOW()
        WHERE id = NEW.scraped_file_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to validation_results table
CREATE TRIGGER validation_completed_trigger
    AFTER INSERT OR UPDATE ON validation_results
    FOR EACH ROW
    EXECUTE FUNCTION trigger_extraction_on_validation();
```

#### 4.5 Validation Worker Updates

**Files to Modify:**
- `ValidationAgent/supabase_client.py` - Use scraped_file_id (UUID) as primary FK
- `ValidationAgent/validate_worker.py` - Read from unified validation_queue
- `ValidationAgent/validate_gemini.py` - Include extraction_id in results

**Key Changes:**
```python
# supabase_client.py - Updated insert
def save_validation_result(self, result: ValidationResult):
    data = {
        'scraped_file_id': result.scraped_file_id,  # UUID (new)
        'file_id': result.file_id,                   # TEXT (legacy)
        'extraction_id': result.extraction_id,       # UUID link
        'status': result.status,
        'confidence_score': result.confidence,
        'subject': result.subject,
        'grade': result.grade,
        # ... rest of fields
    }
    return self.client.table('validation_results').insert(data).execute()

# validate_worker.py - Updated queue consumption
async def process_message(self, message: dict):
    scraped_file_id = UUID(message['scraped_file_id'])
    extraction_id = UUID(message['extraction_id'])
    storage_url = message['storage_url']

    # Validate document
    result = await self.validator.validate(storage_url)

    # Save with all links
    result.scraped_file_id = scraped_file_id
    result.extraction_id = extraction_id
    await self.db.save_validation_result(result)

    # Update scraped_files status
    new_status = 'validated' if result.status == 'correct' else result.status
    await self.db.update_scraped_file_status(scraped_file_id, new_status)
```

#### 4.6 Updated scraped_files Status Flow

```
pending → downloading → downloaded → queued → extracting → extracted → validating → validated
                                                    ↓                        ↓
                                                  failed              rejected/review_required
```

Add new status values:
```sql
ALTER TABLE scraped_files
DROP CONSTRAINT scraped_files_status_check;

ALTER TABLE scraped_files
ADD CONSTRAINT scraped_files_status_check CHECK (status IN (
    'pending', 'downloading', 'downloaded', 'queued',
    'extracting', 'extracted',
    'validating', 'validated',  -- NEW
    'review_required',          -- NEW
    'failed', 'rejected'
));

-- Add validation_status column for granular tracking
ALTER TABLE scraped_files
ADD COLUMN validation_status TEXT CHECK (validation_status IN (
    'unvalidated', 'queued', 'validated', 'rejected', 'review_required', 'failed'
)) DEFAULT 'unvalidated';
```

#### 4.7 Files to Modify for Validation Integration

| File | Project | Changes |
|------|---------|---------|
| `ValidationAgent/supabase_client.py` | Academy Scrapper | Use scraped_file_id (UUID) FK |
| `ValidationAgent/validate_worker.py` | Academy Scrapper | Read from unified queue, handle extraction_id |
| `ValidationAgent/validate_gemini.py` | Academy Scrapper | Include extraction_id in output |
| `migrations/010_validation_tables.sql` | PDF-Extraction | Create validation tables with UUID FKs |
| `migrations/011_validation_triggers.sql` | PDF-Extraction | Auto-trigger validation on extraction |
| `app/services/pgmq_client.py` | PDF-Extraction | PGMQ client for queue operations |
| `app/routers/validation.py` | PDF-Extraction | Validation status API endpoints |

---

## 6. API Contract

### PDF-Extraction API (Updated)

#### Extract from Storage
```
POST /api/extract/from-storage
Content-Type: application/json

{
    "scraped_file_id": "uuid",
    "storage_url": "gs://bucket/path/file.pdf",
    "doc_type": "question_paper" | "memo" | null,
    "webhook_url": "https://callback.url/webhook" | null
}

Response 202:
{
    "extraction_id": "uuid",
    "scraped_file_id": "uuid",
    "status": "processing"
}
```

#### Webhook Callback
```
POST {webhook_url}
Content-Type: application/json

{
    "event": "extraction.completed" | "extraction.failed",
    "extraction_id": "uuid",
    "scraped_file_id": "uuid",
    "status": "completed" | "failed" | "partial",
    "doc_type": "question_paper" | "memo",
    "result": { ... }  // Full extraction data
}
```

### Validation API (New Endpoints)

#### Trigger Batch Validation
```
POST /api/validation/batch
Content-Type: application/json

{
    "scraped_file_ids": ["uuid1", "uuid2", ...],  // Optional: specific files
    "source": "manual" | "api",
    "config": {
        "model": "gemini-2.5-flash-lite",
        "max_workers": 10
    }
}

Response 202:
{
    "job_id": "uuid",
    "status": "queued",
    "total_files": 50
}

When scraped_file_ids.length >= BATCH_API_THRESHOLD (default 100), the service submits a Gemini Batch API job and returns:
{
    "job_id": "uuid",
    "status": "batch_submitted",
    "total_files": 100,
    "gemini_batch_job_id": "uuid"
}
Results are applied when the poller processes the completed job (python -m app.cli poll-batch-jobs).
```

#### Get Validation Job Status
```
GET /api/validation/{job_id}

Response 200:
{
    "job_id": "uuid",
    "status": "running" | "completed" | "failed",
    "total_files": 50,
    "processed_files": 35,
    "accepted_files": 30,
    "rejected_files": 3,
    "review_required_files": 2,
    "failed_files": 0
}
```

#### Get Validation Job Progress (Fast Polling)
```
GET /api/validation/{job_id}/progress

Response 200:
{
    "job_id": "uuid",
    "progress_percent": 70,
    "processed_files": 35,
    "total_files": 50,
    "eta_seconds": 45
}
```

#### Get Validation Result for Document
```
GET /api/validation/result/{scraped_file_id}

Response 200:
{
    "scraped_file_id": "uuid",
    "status": "correct" | "rejected" | "review_required",
    "confidence_score": 85,
    "validation_method": "gemini_vision",
    "subject": "Mathematics",
    "grade": 12,
    "year": "2025",
    "paper_type": "Question Paper",
    "syllabus": "NSC",
    "visual_cues": ["DBE logo", "[10] marks", "QUESTION 1"],
    "rejection_reason": null,
    "validated_at": "2026-01-27T10:00:00Z"
}
```

#### Get Documents Pending Review
```
GET /api/validation/review-queue?limit=50&offset=0

Response 200:
{
    "total": 15,
    "items": [
        {
            "scraped_file_id": "uuid",
            "extraction_id": "uuid",
            "confidence_score": 55,
            "reason": "Low confidence - unclear document type",
            "queued_at": "2026-01-27T10:00:00Z"
        }
    ]
}
```

#### Resolve Review Item
```
POST /api/validation/review/{scraped_file_id}/resolve
Content-Type: application/json

{
    "resolution": "approved" | "rejected",
    "reviewer_notes": "Verified as valid NSC paper",
    "override_metadata": {
        "subject": "Mathematics",
        "grade": 12
    }
}

Response 200:
{
    "scraped_file_id": "uuid",
    "new_status": "validated",
    "resolved_by": "admin@example.com",
    "resolved_at": "2026-01-27T11:00:00Z"
}
```

---

## 7. Verification Plan

### 7.1 Database Verification
```sql
-- Verify ID consistency
SELECT
    sf.id as scraped_file_id,
    sf.file_id,
    e.id as extraction_id,
    pq.id as parsed_question_id,
    ej.id as job_id
FROM scraped_files sf
LEFT JOIN extractions e ON e.scraped_file_id = sf.id
LEFT JOIN parsed_questions pq ON pq.scraped_file_id = sf.id
LEFT JOIN extraction_jobs ej ON ej.scraped_file_id = sf.id
WHERE sf.created_at > NOW() - INTERVAL '7 days';

-- Verify no orphaned records
SELECT COUNT(*) FROM parsed_questions WHERE scraped_file_id IS NULL;
SELECT COUNT(*) FROM extraction_jobs WHERE scraped_file_id IS NULL;
```

### 7.2 End-to-End Test
1. Submit URL to Academy Scrapper crawler
2. Verify `scraped_files` record created with UUID
3. Verify PDF uploaded to Firebase with correct path
4. Verify PDF-Extraction API called with `scraped_file_id`
5. Verify `extractions` record links to `scraped_files`
6. Verify validation auto-triggered (DB trigger fired)
7. Verify `validation_results` record created with same `scraped_file_id`
8. Verify `scraped_files.status` updated to 'validated' or 'rejected'
9. Query full document journey by single ID

### 7.3 Test Commands
```bash
# PDF-Extraction health check
curl http://localhost:8000/health

# Test extraction from storage
curl -X POST http://localhost:8000/api/extract/from-storage \
  -H "Content-Type: application/json" \
  -d '{
    "scraped_file_id": "test-uuid",
    "storage_url": "gs://scrapperdb-f854d.firebasestorage.app/test.pdf"
  }'

# Check validation status
curl http://localhost:8000/api/validation/result/test-uuid

# Trigger batch validation (manual)
curl -X POST http://localhost:8000/api/validation/batch \
  -H "Content-Type: application/json" \
  -d '{
    "scraped_file_ids": ["uuid1", "uuid2"],
    "source": "api"
  }'

# Check validation job progress
curl http://localhost:8000/api/validation/{job_id}/progress

# Verify database linkage (full journey)
psql -c "SELECT * FROM scraped_files WHERE id = 'test-uuid'"
psql -c "SELECT * FROM extractions WHERE scraped_file_id = 'test-uuid'"
psql -c "SELECT * FROM validation_results WHERE scraped_file_id = 'test-uuid'"
```

### 7.4 Validation-Specific Tests

```bash
# Test validation trigger (should auto-fire after extraction)
# 1. Insert extraction with status='completed'
psql -c "INSERT INTO extractions (scraped_file_id, status) VALUES ('test-uuid', 'completed')"

# 2. Check if validation queue has message
psql -c "SELECT * FROM pgmq.q_validation_queue"

# 3. Run validation worker
cd "Academy Scrapper/ValidationAgent"
python validate_worker.py --once

# 4. Check validation result
psql -c "SELECT status, confidence_score FROM validation_results WHERE scraped_file_id = 'test-uuid'"

# Test review queue
curl http://localhost:8000/api/validation/review-queue

# Resolve review item
curl -X POST http://localhost:8000/api/validation/review/test-uuid/resolve \
  -H "Content-Type: application/json" \
  -d '{"resolution": "approved", "reviewer_notes": "Verified"}'
```

---

## 8. Files to Create/Modify

### New Files
| File | Project | Purpose |
|------|---------|---------|
| `migrations/009_unify_id_tracking.sql` | PDF-Extraction | Add scraped_file_id UUIDs |
| `migrations/010_validation_tables.sql` | PDF-Extraction | Create validation_results, validation_jobs |
| `migrations/011_validation_triggers.sql` | PDF-Extraction | Auto-trigger validation on extraction |
| `database/migrations/phase3_unification.sql` | Academy Scrapper | ID standardization |
| `app/services/firebase_client.py` | PDF-Extraction | Firebase Storage access |
| `app/services/pgmq_client.py` | PDF-Extraction | PGMQ queue operations |
| `app/routers/storage_extraction.py` | PDF-Extraction | Extract from Firebase URL endpoint |
| `app/routers/validation.py` | PDF-Extraction | Validation API endpoints |
| `app/db/validation_results.py` | PDF-Extraction | Validation results CRUD |
| `app/db/validation_jobs.py` | PDF-Extraction | Validation jobs CRUD |
| `app/models/validation.py` | PDF-Extraction | Validation Pydantic models |
| `Services/ExtractionApiClient.cs` | Academy Scrapper | API integration |

### Modified Files - PDF-Extraction
| File | Changes |
|------|---------|
| `app/main.py` | Register validation router, add PGMQ lifespan |
| `app/db/extractions.py` | Accept scraped_file_id in create |
| `app/db/memo_extractions.py` | Accept scraped_file_id in create |
| `app/routers/extraction.py` | Add post-extraction validation trigger |
| `app/config.py` | Add PGMQ connection settings |

### Modified Files - Academy Scrapper
| File | Changes |
|------|---------|
| `Services/DirectPageScraperService.cs` | Call PDF-Extraction API after download |
| `Services/ExtractionDb/SupabaseParsedQuestionsService.cs` | Use scraped_file_id (UUID) FK |
| `Services/ExtractionDb/SupabaseScrapedFilesService.cs` | Return UUID for extraction calls |
| `ValidationAgent/supabase_client.py` | Use scraped_file_id (UUID) as primary FK |
| `ValidationAgent/validate_worker.py` | Read from unified PGMQ queue, handle extraction_id |
| `ValidationAgent/validate_gemini.py` | Include extraction_id + scraped_file_id in output |
| `ValidationAgent/config.py` | Add PGMQ queue configuration |

### Database Migrations Summary
| Migration | Tables Affected | Purpose |
|-----------|-----------------|---------|
| 009 | parsed_questions, parser_jobs | Add scraped_file_id UUID FK |
| 010 | validation_results, validation_jobs | Create validation tables with UUID FKs |
| 011 | extractions, memo_extractions | Add triggers for auto-validation |
| phase3 (Academy) | scraped_files | Add validation_status column |

---

## 9. Rollback Plan

### If Issues Occur:
1. **Database**: Migrations use ADD COLUMN (non-destructive)
2. **API**: New endpoint doesn't affect existing /api/extract
3. **Legacy Support**: file_id TEXT FK retained for backward compatibility

### Rollback Steps:
```sql
-- Revert to file_id FK if needed
ALTER TABLE parsed_questions DROP COLUMN scraped_file_id;
ALTER TABLE extraction_jobs RENAME TO extraction_jobs_deprecated;
```

---

## 10. Success Criteria

### ID Unification
- [ ] Single UUID (`scraped_file_id`) tracks document from URL → validation
- [ ] All tables link via `scraped_file_id` (UUID)
- [ ] Legacy `file_id` (TEXT) remains for backward compatibility
- [ ] No orphaned records in any table

### Extraction Integration
- [ ] PDF-Extraction service handles Firebase Storage URLs
- [ ] Academy Scrapper calls PDF-Extraction API after download
- [ ] `extractions` table linked to `scraped_files` via UUID FK
- [ ] Webhook notifications work end-to-end

### Validation Integration
- [ ] Validation auto-triggers after extraction completes (DB trigger)
- [ ] `validation_results` table uses `scraped_file_id` (UUID) FK
- [ ] `validation_jobs` tracks batch validation progress
- [ ] ValidationAgent Python worker consumes from unified PGMQ queue
- [ ] Confidence scoring determines document status
- [ ] Review queue populated for low-confidence documents
- [ ] Rejected documents flagged and not served

### Status Flow
- [ ] `scraped_files.status` transitions correctly through all phases
- [ ] `scraped_files.validation_status` tracks validation state
- [ ] Status values: pending → downloaded → queued → extracted → validated

### End-to-End Tests
- [ ] URL discovery → download → extraction → validation → API query
- [ ] Query document by `scraped_file_id` returns full journey
- [ ] Rejected document correctly blocked from consumption
- [ ] Review queue workflow (queue → review → resolve)

---

## Appendix A: Current Table Inventory

### PDF-Extraction Tables
- `extractions` - Exam paper extraction results
- `memo_extractions` - Marking guideline results
- `review_queue` - Manual review items
- `batch_jobs` - Batch processing jobs
- `gemini_batch_jobs` - Gemini Batch API job tracking (validation + extraction, migration 018)

### Academy Scrapper Tables
- `scraped_files` - Core PDF metadata (shared)
- `rejected_pdfs_index` - Failed downloads
- `parsed_questions` - Individual questions
- `parser_jobs` - Parser job tracking (→ extraction_jobs)
- `question_groups` - Question hierarchy
- `questions` - Detailed question data
- `preprocessed_images` - Image cache
- `queue_state` - Queue control
- `cost_tracking` - API costs
- `audit_logs` - Audit trail
- `validation_jobs` - Validation tracking
- `validation_results` - Validation outcomes

### PGMQ Queues
- `parser_queue_high`
- `parser_queue_normal`
- `parser_queue_low`
- `parser_dead_letter`

---

## Appendix B: ID Mapping Reference

| Old ID Type | New ID Type | Notes |
|-------------|-------------|-------|
| `file_id` (TEXT) | `scraped_file_id` (UUID) | UUID is authoritative |
| `extraction_id` (UUID) | No change | Already correct |
| `parser_job_id` (UUID) | `extraction_job_id` (UUID) | Table renamed |

---

*Plan created: 2026-02-03*
*Target completion: 4-5 weeks*
