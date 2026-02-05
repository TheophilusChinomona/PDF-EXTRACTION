---
name: Batch Paper Matching Execution
overview: Fix bugs in the matching infrastructure, enhance the batch matcher to filter correctly, add the missing API endpoint, then run batch matching across all ~10,500 validated documents in AcademyScrapper-Unified to populate exam_sets with QP-Memo pairs.
todos:
  - id: fix-optional-import
    content: Fix missing Optional import in batch_matcher.py (line 9)
    status: completed
  - id: fix-status-filter
    content: Add status='correct' filter to list_validation_results call in batch_matcher.py (line 82)
    status: completed
  - id: add-match-after-validation-endpoint
    content: Add POST /api/exam-sets/match-after-validation endpoint to exam_sets router for validation worker integration
    status: completed
  - id: enhance-batch-script
    content: Add --dry-run, --all, --status-filter flags and progress logging to run_batch_matcher.py
    status: completed
  - id: preflight-query
    content: Run diagnostic queries to understand current DB state before matching
    status: completed
  - id: execute-batch-match
    content: Run the batch matcher across all correct validation results
    status: completed
  - id: verify-results
    content: Query exam_sets table to verify matching results and report statistics
    status: completed
isProject: false
---

# Batch Paper Matching Execution Plan

All work is in `C:\Users\theoc\Desktop\Work\AcademyScrapper-Unified\services\extraction-service\`.

## Current State

- **10,554 validation_results** exist (10,239 correct, 264 rejected, 51 review_required)
- **3,051 Question Papers** and **2,911 Memos** identified by document type
- **exam_sets table** exists but is likely empty or near-empty (no batch matching has been run)
- The matching code is implemented but has 3 bugs/gaps preventing correct operation

## Bugs to Fix (3 issues)

### Bug 1: Missing import in batch_matcher.py

[batch_matcher.py](services/extraction-service/app/services/batch_matcher.py) line 68 uses `Optional[Client]` but `Optional` is not imported from `typing` (line 9 only imports `Any, Dict, Set`).

**Fix:** Add `Optional` to the typing import on line 9.

### Bug 2: Batch matcher processes ALL validation results (including rejected)

`run_batch_matcher()` calls `list_validation_results(client, limit=page_size, offset=offset)` without filtering by status. This means it will also try to match rejected and review_required documents, wasting cycles and potentially creating incorrect exam sets from bad data.

**Fix:** Pass `status="correct"` to `list_validation_results()` on line 82 of [batch_matcher.py](services/extraction-service/app/services/batch_matcher.py):

```python
items, total = await db_validation_results.list_validation_results(
    client,
    status="correct",  # Only match validated documents
    limit=page_size,
    offset=offset,
)
```

### Bug 3: Missing `/api/exam-sets/match-after-validation` endpoint

The validation worker ([validate_worker.py](services/validation-worker/validate_worker.py) line ~630) calls `POST /api/exam-sets/match-after-validation`, but this endpoint does not exist in the [exam_sets router](services/extraction-service/app/routers/exam_sets.py). Only `/match` (manual) and `/batch-match` (batch) exist.

**Fix:** Add a new `POST /api/exam-sets/match-after-validation` endpoint that:

- Accepts JSON body: `{scraped_file_id, subject, grade, year, paper_type, paper_number, session, syllabus}`
- Calls `match_document_to_exam_set()` with the provided metadata
- Returns `{exam_set_id, match_confidence, status}` (including `status: "duplicate"` with `original_exam_set_id` when applicable)

This is critical for the validation worker integration to work going forward.

## Enhance Batch Matcher for Full Run

The current batch matcher has a hard limit of 500 documents per invocation. With ~10,239 correct validation results, we need to either:

- **Option A:** Increase the limit parameter in the script invocation (`python scripts/run_batch_matcher.py 15000`)
- **Option B (preferred):** Update the script to support `--all` flag that removes the limit cap, and add `--dry-run` for safety

**Enhancement to** [run_batch_matcher.py](services/extraction-service/scripts/run_batch_matcher.py):

- Add `--dry-run` flag: query and report matchable documents without creating exam_sets
- Add `--all` flag: remove the 500 limit, process all unlinked documents
- Add `--status-filter` flag: specify which validation status to match (default: `correct`)
- Print progress every 100 documents
- Print summary at end: total scanned, exam sets created, QP-Memo matches made, duplicates found, errors

## Execution Steps

### Step 1: Pre-flight query (read-only)

Run a diagnostic query against the database to understand what we're working with:

```python
# Query current state
- Count of exam_sets (existing matches)
- Count of validation_results by status
- Count of validation_results with status='correct' that have paper_type
- Breakdown of paper_type values (Question Paper vs Memorandum)
- Count of validation_results with missing metadata fields (subject, grade, session)
```

### Step 2: Apply bug fixes

Apply the 3 fixes listed above to the AcademyScrapper-Unified codebase.

### Step 3: Dry run

```bash
cd C:\Users\theoc\Desktop\Work\AcademyScrapper-Unified\services\extraction-service
python scripts/run_batch_matcher.py --dry-run --all
```

Review output to confirm expected match counts before writing.

### Step 4: Execute batch matching

```bash
python scripts/run_batch_matcher.py --all
```

This will:

1. Fetch all `correct` validation_results
2. Skip any already linked to exam_sets
3. For each unlinked document, normalize metadata and find/create exam_set
4. Link QP or Memo to the appropriate slot
5. Handle duplicates via document_versions

### Step 5: Verify results

```sql
-- Total exam sets created
SELECT count(*) FROM exam_sets;

-- Matched vs incomplete
SELECT status, count(*) FROM exam_sets GROUP BY status;

-- Fully matched pairs (both QP and Memo linked)
SELECT count(*) FROM exam_sets 
WHERE question_paper_id IS NOT NULL AND memo_id IS NOT NULL;

-- Incomplete (only QP or only Memo)
SELECT count(*) FROM exam_sets WHERE status = 'incomplete';

-- Duplicates flagged for review
SELECT count(*) FROM exam_sets WHERE status = 'duplicate_review';

-- Sample matched pairs
SELECT es.subject, es.grade, es.paper_number, es.year, es.session,
       qp.filename as qp_file, m.filename as memo_file
FROM exam_sets es
LEFT JOIN scraped_files qp ON es.question_paper_id = qp.id
LEFT JOIN scraped_files m ON es.memo_id = m.id
WHERE es.status = 'matched'
LIMIT 10;
```

## Expected Outcome

```
Matching Flow:
  validation_results (status=correct, ~10,239)
      |
      v
  normalize metadata (subject, grade, paper, year, session)
      |
      v
  find/create exam_set by match key
      |
      +-- QP slot empty? --> link as question_paper_id
      +-- Memo slot empty? --> link as memo_id
      +-- Slot filled? --> create document_version (duplicate)
      |
      v
  exam_sets (estimated ~3,000-4,000 sets, many matched)
```

With ~3,051 QPs and ~2,911 Memos, we expect roughly:

- ~2,500-3,000 exam sets created (one per unique subject+grade+paper+year+session)
- ~2,000+ fully matched pairs (both QP and Memo linked)
- Some incomplete sets (QP or Memo without a counterpart)
- Some duplicates flagged for review

## Files Modified


| File                            | Change                                               |
| ------------------------------- | ---------------------------------------------------- |
| `app/services/batch_matcher.py` | Fix `Optional` import; add `status="correct"` filter |
| `app/routers/exam_sets.py`      | Add `POST /match-after-validation` endpoint          |
| `scripts/run_batch_matcher.py`  | Add `--dry-run`, `--all`, progress logging           |


