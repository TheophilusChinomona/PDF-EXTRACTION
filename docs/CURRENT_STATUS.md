# Current Project Status

Last updated: 2026-02-06

## Exam Sets (Paper Matching)

| Metric | Value |
|--------|-------|
| Total exam_sets | 3,626 |
| Complete pairs (QP + Memo) | 1,121 |
| Matched status | 435 |
| Pairs with both QP and Memo extraction | 8 |

See **docs/exam-sets-overview.md** for schema, SQL queries, CLI usage, and presentation-ready tables.

## Active Batch Jobs

| Job Type | batch_job_id | gemini_batch_job_id | Status | Files | Notes |
|----------|--------------|---------------------|--------|-------|-------|
| Extraction | `f99a233c-8484-4c28-b60e-1269c96b6e83` | `4545e6cf-ec77-4138-9e21-c7cc92a22987` | Pending | 100 | First test of Gemini Batch API for extraction |

## How to Check Status

```bash
# Poll once to check and process completed jobs
python -m app.cli poll-batch-jobs --once

# Or query the database
SELECT id, gemini_job_name, status, total_requests, completed_requests, failed_requests 
FROM gemini_batch_jobs 
ORDER BY created_at DESC 
LIMIT 5;
```

## Recent Changes

### 2026-02-06: Paper Matching & Extraction Pipeline

- Added `scripts/extract_matched_pairs.py` — Run extraction on matched exam_sets (download from Firebase, hybrid pipeline, save to `extractions` / `memo_extractions` with `scraped_file_id`). CLI: `--subject`, `--status`, `--limit`, `--dry-run`, `--no-skip-existing`, `--source-url`.
- Updated `scripts/export_extractions_md.py` — `--exam-sets` mode: fetch matched pairs, write summary markdown, and for pairs with extraction data rebuild JSON to markdown (paired `-qp.md` / `-mg.md`). Supports `--subject`, `--status`, `--limit`, `--output`, `--source-url`.
- Extended `scripts/download_matched_pairs_pdfs.py` — Optional `--source-url`, `--subject`, `--status`, `--limit`; when any is set, query DB for exam_sets (same filters as export) and download those PDFs; when `--source-url` is set, write `SOURCE-LINKS-{slug}.md`. With no args, uses hardcoded English pairs.
- Added `docs/exam-sets-overview.md` — Presentation-ready doc: exam_sets schema, ERD, status/subject stats, sample data, SQL queries, CLI usage, extraction coverage, and **Papers from education.gov.za** (prerequisite: validate then match; then use `--source-url education.gov.za` for extract/export/download).
- **Source URL filter:** The matched-pairs pipeline supports `--source-url` (e.g. `education.gov.za`). Papers from that source must be validated and matched (Academy Scrapper + batch matcher) before they appear in exam_sets; then the same extract/export/download commands work with `--source-url education.gov.za`.

### 2026-02-05: Storage Path Fix & Extraction Resilience

- Added `scripts/diagnose_storage_paths.py` - Diagnose storage_path vs Firebase blob mismatches
- Added `scripts/fix_storage_paths.py` - Fix mismatched storage_path values (`--dry-run` / `--run`)
- Updated `scripts/run_extraction_batch_from_validated.py` - Added `--min-files`, `--force` flags, download progress logging, and actionable error messages when all downloads fail
- Added `docs/CONTRIB.md` - Contributing guide with scripts reference and environment setup
- Added `docs/RUNBOOK.md` - Operational runbook with deployment, monitoring, troubleshooting, and rollback

### 2026-02-04: Gemini Batch API Implementation

- Added `app/services/gemini_batch.py` - Core batch API operations
- Added `app/services/extraction_batch.py` - Batch extraction processor
- Added `app/services/validation_batch.py` - Batch validation processor
- Added `app/services/batch_job_poller.py` - Background job poller
- Added `app/db/gemini_batch_jobs.py` - Database CRUD
- Added `migrations/018_gemini_batch_jobs.sql` - Tracking table
- Added `scripts/run_extraction_batch_from_validated.py` - Test script
- Updated `app/config.py` - Added batch_api_threshold, FIREBASE_CREDENTIALS_PATH fallback
- Updated `app/db/batch_jobs.py` - Added 'batch_api' to valid_methods
- Updated `app/cli.py` - Added poll-batch-jobs command

### Key Environment Variables Added

- `SUPABASE_SERVICE_ROLE_KEY` - Bypasses RLS for scripts
- `FIREBASE_CREDENTIALS_PATH` - Fallback for `FIREBASE_SERVICE_ACCOUNT_JSON`

## Validated-Not-Extracted Stats

As of 2026-02-04:
- Total validation_results (status=correct): ~10,239
- Already extracted (extractions + memo_extractions): ~10
- Available for extraction: ~9,700+

## Next Steps

1. **Exam sets:** Run extraction on matched pairs: `python scripts/extract_matched_pairs.py --subject english --status matched --limit 10`; then export: `python scripts/export_extractions_md.py --exam-sets --subject english --status matched`.
2. Run `python scripts/diagnose_storage_paths.py --validated-only` to identify storage path mismatches (if needed).
3. Run `python scripts/fix_storage_paths.py --dry-run` then `--run` to fix paths (if needed).
4. Re-run extraction batch: `python scripts/run_extraction_batch_from_validated.py`; poll: `python -m app.cli poll-batch-jobs --once`.
5. Run additional batches to process remaining validated files.
