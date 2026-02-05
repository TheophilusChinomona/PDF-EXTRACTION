# PDF-Extraction Agent Instructions

## Database State (Last Updated: Feb 5, 2026)

### Summary Statistics

| Table | Total | Status Breakdown |
|-------|-------|------------------|
| **scraped_files** | 35,944 | validated: 10,239 / rejected: 264 / review_required: 51 / unvalidated: 25,390 |
| **validation_results** | 10,554 | correct: 10,239 / rejected: 264 / review_required: 51 |
| **extractions** | 70 | all completed |
| **memo_extractions** | 62 | all completed |
| **file_registry** | 2,841 | all validated |
| **batch_jobs** | 11 | completed: 7 / pending: 3 |
| **gemini_batch_jobs** | 2 | both succeeded |

### Document Types (scraped_files)
- Question Paper: 3,051
- Memorandum: 2,911
- Other: 198
- Study Guide: 10

### Top Subjects
| Subject | Count |
|---------|-------|
| Mathematics | 1,283 |
| Chemistry | 487 |
| Physics | 450 |
| Biology | 362 |
| History | 349 |
| English | 319 |
| Accounting | 282 |
| English Literature | 282 |
| English Language | 250 |
| Further Mathematics | 217 |

### Grade Distribution
| Grade | Count |
|-------|-------|
| Grade 12 | 2,635 |
| Grade 10 | 1,056 |
| Grade 11 | 789 |
| Grade 9 | 109 |

### Exam Levels
| Level | Count |
|-------|-------|
| Grade 12 | 5,996 |
| GCSE | 4,380 |
| A Level | 2,619 |
| AS Level | 1,235 |
| IGCSE | 429 |

### Syllabuses
| Syllabus | Count |
|----------|-------|
| Other | 2,400 |
| NSC | 1,720 |
| IEB | 1,227 |
| Unknown | 292 |
| Cambridge | 68 |
| CAPS | 68 |

### Year Coverage
- Range: 2008-2025
- Peak years: 2019 (731), 2022 (713), 2018 (591)

### Extraction Coverage Gap
- **Validated Question Papers:** 2,829 available
- **Extracted:** 70 (only **2.5%** coverage)
- **Validated Memos:** 2,674 available  
- **Memo Extracted:** 62 (only **2.3%** coverage)

### scraped_file_id Linkage (Current State)
- **All 70 extractions** and **all 62 memo_extractions** have `scraped_file_id` set (linked to `scraped_files`).
- Orphan records were resolved by `scripts/register_and_link_extractions.py`, which creates missing `scraped_files` from Firebase Storage paths and links them.

### Full Database Schema (Supabase)

**Public schema (26 tables):**

| Table | Description |
|-------|-------------|
| `scraped_files` | Source PDFs from Firebase Storage; has storage_path, storage_bucket |
| `extractions` | Extracted question papers; link via scraped_file_id → scraped_files.id |
| `memo_extractions` | Extracted marking guidelines; link via scraped_file_id |
| `validation_results` | Validation outcomes; has scraped_file_id |
| `file_registry` | Discovered files registry |
| `batch_jobs` | Local batch processing jobs |
| `gemini_batch_jobs` | Gemini Batch API job tracking |
| `validation_jobs` | Validation job tracking |
| `extraction_jobs` | Extraction job tracking |
| `exam_sets` | QP + Memo pairs |
| `document_sections` | Extracted sections per document |
| `document_versions` | Document version tracking |
| `review_queue` | Manual review queue |
| `extraction_documents` | OCR pipeline document metadata |
| `extraction_pages` | Extracted text per page |
| `extraction_elements` | Detected elements (questions, images, etc.) |
| `extraction_spatial_links` | Links between elements |
| `preprocessed_images` | Vision OCR pipeline |
| `layout_maps` | Layout analysis |
| `extracted_elements` | Extracted elements |
| `question_groups` | Question group hierarchy |
| `questions` | Parsed questions |
| `question_media` | Question media references |
| `question_options` | Question options |
| `question_answers` | Question answers |
| `parsed_questions` | Parsed question data |

**PGMQ schema (message queues):**
- `a_validation_queue`, `a_validation_queue_high` – validation jobs
- `a_extraction_queue` – extraction jobs
- `a_validation_dead_letter` – failed validation messages

**Other schemas:** `auth`, `storage`, `realtime`, `net`, `vault`, `supabase_functions`, `supabase_migrations` (Supabase-managed).

### Academy Scrapper Relationship

The same Supabase database is shared by two projects:

1. **Academy Scrapper** (`C:\Users\theoc\Desktop\Work\Academy Scrapper`):
   - **Scapper.Console/SAPdfScraper** – C# backend that scrapes PDFs and writes to Firebase Storage and `scraped_files`
   - **Scapper.Console/ValidationAgent** – Python validation agent; uses PGMQ queues and writes `validation_results`
   - **Scrapper.FE** – React frontend

2. **PDF-Extraction** (this project):
   - Python FastAPI extraction service; reads from Firebase Storage (paths from `scraped_files`), writes `extractions` and `memo_extractions`

**Storage:** Firebase (GCS) is used only for file storage. `scraped_files.storage_path` and `scraped_files.storage_bucket` are the source of truth for PDF locations. Extractions and memo_extractions should always link via `scraped_file_id` to get storage paths and consistent IDs.

---

## Database Query Scripts

These scripts are available in `scripts/` for querying and managing the Supabase database.

### Quick Stats
```bash
# Get extraction/validation status summary
python scripts/query_extraction_stats.py

# Full database summary (all tables)
python scripts/full_db_summary.py

# Check revalidation progress
python scripts/check_revalidate_progress.py
```

### Upload Local Extractions
```bash
# Dry run - see what would be uploaded
python scripts/upload_local_extractions.py --dry-run

# Upload all local JSON extractions to Supabase (links scraped_file_id when match found)
python scripts/upload_local_extractions.py
```

### Backfill scraped_file_id (match existing scraped_files only)
```bash
# Report matches only (no writes)
python scripts/backfill_scraped_file_ids.py --dry-run

# Link orphan extractions/memo_extractions to existing scraped_files
python scripts/backfill_scraped_file_ids.py
```

### Register Missing PDFs and Link (create scraped_files from Firebase)
When PDFs exist in Firebase Storage but have no `scraped_files` row, use this script to list storage, create `scraped_files` records, and link extractions:
```bash
# Dry run - report what would be created and linked
python scripts/register_and_link_extractions.py --dry-run

# Create scraped_files (from storage path or metadata match) and link all orphans
python scripts/register_and_link_extractions.py
```
Uses `app/services/firebase_client.list_blobs()` to list paths under `pdfs/`; matches by filename then by metadata (subject, year, document type).

### Batch Job Management
```bash
# Poll Gemini batch jobs for completion (once)
python -m app.cli poll-batch-jobs --once

# Poll continuously every 60 seconds
python -m app.cli poll-batch-jobs --interval 60

# Poll only extraction jobs
python -m app.cli poll-batch-jobs --once --job-type extraction
```

### Run Batch Extraction
```bash
# Dry run batch extraction from validated files
python scripts/run_extraction_batch_from_validated.py --dry-run

# Run actual batch extraction
python scripts/run_extraction_batch_from_validated.py
```

### Paper Matching (QP–Memo / exam_sets)

Match question papers to memos and populate `exam_sets`. Scripts live in **AcademyScrapper-Unified** (`services/extraction-service/`). Run from that directory; ensure `.env` has `SUPABASE_SERVICE_ROLE_KEY` so the app bypasses RLS.

```bash
cd C:\Users\theoc\Desktop\Work\AcademyScrapper-Unified\services\extraction-service

# Pre-flight: show validation_results and exam_sets counts (read-only)
python scripts/diagnose_matching_state.py

# Dry run: report how many would be matched/created, no writes
python scripts/run_batch_matcher.py --dry-run --all

# Run batch matching for all unlinked correct validation results
python scripts/run_batch_matcher.py --all

# Optional: limit to N documents, or filter by validation status
python scripts/run_batch_matcher.py 500
python scripts/run_batch_matcher.py --status-filter correct --all

# After matching: verify exam_sets counts and sample pairs
python scripts/verify_matching_results.py
```

API alternative (extraction-service must be running): `POST /api/exam-sets/batch-match?limit=500` (or higher).

---

## Script Details

### `scripts/query_extraction_stats.py`
Quick summary of:
- Validation results by status (correct, rejected, review_required, pending, error)
- Extraction jobs by status
- Extractions and memo_extractions counts
- Gemini batch jobs status
- Scraped files and exam sets counts

### `scripts/full_db_summary.py`
Comprehensive query of ALL tables with:
- Record counts
- Column schemas
- Sample records (most recent 3)
- Aggregate statistics (by subject, language, grade)

### `scripts/upload_local_extractions.py`
Uploads local JSON extractions from `Sample PDFS/` and `test_batch/` to Supabase:
- Parses JSON files as FullExamPaper or MarkingGuideline
- Looks up `scraped_file_id` from scraped_files (by filename or metadata) so records link to Firebase storage
- Detects memos vs question papers from filename/content
- Skips duplicates (by file_hash)
- Supports `--dry-run` flag

### `scripts/backfill_scraped_file_ids.py`
Links existing extractions and memo_extractions that have `scraped_file_id = NULL` to **existing** scraped_files only:
- Match by normalized filename (strip hash prefix) or by subject + year + grade + session when unique
- Use `--dry-run` to report matches without updating

### `scripts/register_and_link_extractions.py`
For orphans whose PDFs are in Firebase but not in `scraped_files`: lists blob paths via `firebase_client.list_blobs()`, matches each extraction by filename or by metadata (subject, year, document type), creates `scraped_files` rows (with `storage_path` when found, else null), and sets `scraped_file_id` on extractions/memo_extractions. Handles duplicate `file_id` by reusing existing scraped_file. Use `--dry-run` to report only; `--bucket` to override default bucket.

### Paper matching (AcademyScrapper-Unified extraction-service)
- **`scripts/diagnose_matching_state.py`** – Pre-flight: counts of validation_results by status, exam_sets, and sample metadata. Read-only.
- **`scripts/run_batch_matcher.py`** – Scans `validation_results` (default status=correct) not yet linked to exam_sets; creates/updates exam_sets and links QP or Memo. Flags: `--dry-run` (no writes), `--all` (no limit), `--status-filter correct`. Requires `SUPABASE_SERVICE_ROLE_KEY` in `.env`.
- **`scripts/verify_matching_results.py`** – Post-run: total exam_sets, by status, fully matched pairs, incomplete, duplicate_review, sample pairs.

---

## Common Database Queries

### Using Python
```python
import sys
sys.path.insert(0, '.')
from app.db.supabase_client import get_supabase_client

client = get_supabase_client()

# Count extractions
result = client.table("extractions").select("*", count="exact", head=True).execute()
print(f"Total extractions: {result.count}")

# Get recent extractions
recent = client.table("extractions").select("*").order("created_at", desc=True).limit(10).execute()
for ext in recent.data:
    print(f"{ext['file_name']} - {ext['subject']}")

# Filter by status
completed = client.table("extractions").select("*").eq("status", "completed").execute()

# Filter by subject (partial match)
math = client.table("extractions").select("*").ilike("subject", "%mathematics%").execute()
```

### Key Tables Reference

| Table | Primary Key | Key Columns |
|-------|-------------|-------------|
| `scraped_files` | id (UUID) | filename, storage_path, validation_status |
| `extractions` | id (UUID) | file_name, file_hash, subject, grade, year, status |
| `memo_extractions` | id (UUID) | file_name, file_hash, subject, grade, year, status |
| `validation_results` | scraped_file_id | status, confidence_score, subject, grade |
| `gemini_batch_jobs` | id (UUID) | gemini_job_name, job_type, status, total_requests |
| `batch_jobs` | id (UUID) | status, total_files, completed_files |

---

## Bug Fixes Applied

### Gemini Batch API File URI Fix (Feb 5, 2026)
**File:** `app/services/gemini_batch.py`

The Batch API requires full file URIs (`https://generativelanguage.googleapis.com/v1beta/files/xxx`) 
not just file names (`files/xxx`).

Fixed by using `uploaded.uri` instead of `uploaded.name` in:
- `build_validation_request()`
- `build_extraction_request()`
