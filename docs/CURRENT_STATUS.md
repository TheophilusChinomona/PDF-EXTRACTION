# Current Project Status

Last updated: 2026-02-04

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

1. Wait for current batch job to complete (check with poll-batch-jobs)
2. Verify extraction results are correctly stored
3. Run additional batches to process remaining validated files
4. Consider adding parallel PDF downloads for faster submission
