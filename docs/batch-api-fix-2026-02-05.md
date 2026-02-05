# Fix Batch API Result Processing Failures

**Date:** 2026-02-05

## Problem

The Gemini Batch API submission format was correct - all 92 results came back from Google. The failures were all on the local storage/validation side:

### Issue 1: Missing DB Enum Value (~70 keys failing)
**Error:** `invalid input value for enum processing_method_type: "batch_api"`

- `migrations/001_create_extractions_table.sql` defines the enum with only: `hybrid`, `vision_fallback`, `opendataloader_only`
- `extraction_batch.py:203,214` sets `processing_metadata['method'] = 'batch_api'`
- DB insert functions read this and try to insert it into the `processing_method` column
- PostgreSQL rejects `'batch_api'` because it's not in the enum

### Issue 2: Pydantic Schema Validation (~15 keys failing)
Gemini's batch output is slightly different from interactive output:

- `MemoQuestion.answers` was `List[Dict[str, str]]` but Gemini returns `marks` as `int`
- `MemoQuestion.structured_answer` was `List[Dict[str, str]]` but Gemini returns `mark` as `int` and `points` as `list`
- `MarkingGuideline.meta` was `Dict[str, Union[str, int]]` but Gemini returns `None` for some fields and `list` for others

### Issue 3: Invalid JSON (2 keys)
Gemini returned truncated JSON for 2 responses. Normal batch API behavior, not fixable.

---

## Changes Made

| File | Change |
|------|--------|
| `migrations/020_add_batch_api_processing_method.sql` | **Created** - Adds `batch_api` to `processing_method_type` enum |
| `app/models/memo_extraction.py:64` | Changed `answers` type from `Dict[str, str]` to `Dict[str, Union[str, int, None]]` |
| `app/models/memo_extraction.py:68` | Changed `structured_answer` type from `Dict[str, str]` to `Dict[str, Any]` |
| `app/models/memo_extraction.py:125` | Changed `meta` type from `Dict[str, Union[str, int]]` to `Dict[str, Any]` |

---

## Manual Steps Required

### Step 1: Run the SQL Migration

In Supabase Dashboard SQL Editor (`https://supabase.com/dashboard/project/aqxgnvjqabitfvcnboah`):

```sql
ALTER TYPE processing_method_type ADD VALUE IF NOT EXISTS 'batch_api';
```

### Step 2: Reset Batch Job Status

In Supabase Dashboard SQL Editor:

```sql
UPDATE gemini_batch_jobs
SET status = 'pending', completed_at = NULL, failed_requests = 0, completed_requests = 0
WHERE status = 'succeeded'
AND failed_requests > 0
AND (completed_requests - failed_requests) = 0;
```

### Step 3: Re-poll Batch Jobs

```bash
"C:\Python314\python.exe" -m app.cli poll-batch-jobs --once
```

---

## Expected Result

~80+ extractions should succeed (only 2 invalid JSON responses from Gemini + possible edge-case schema issues remaining).
