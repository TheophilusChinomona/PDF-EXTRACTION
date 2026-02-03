# Code Review Report: PDF-Extraction Service

**Date:** 2026-01-28
**Branch:** `ralph/memo-extraction-sidecar`
**Reviewer:** Claude Opus 4.5

## Overview

A well-structured FastAPI microservice implementing a hybrid PDF extraction pipeline (OpenDataLoader + Gemini API) for South African academic exam papers and marking guidelines. The architecture is sound and the codebase follows good separation of concerns.

## Severity Legend
- **CRITICAL** - Must fix before production
- **HIGH** - Should fix soon, potential for bugs or security issues
- **MEDIUM** - Recommended improvement
- **LOW** - Minor style/quality suggestion

---

## CRITICAL Issues

### 1. `time.sleep()` in async retry decorator blocks the event loop
**File:** `app/utils/retry.py:102` and `:138`

The `async_wrapper` uses `time.sleep(delay)` which **blocks the entire event loop** during retries. This means all concurrent requests are frozen during backoff delays (up to 32+ seconds on later retries).

```python
# Line 102 - BLOCKS the event loop
time.sleep(delay)
```

**Fix:** Replace with `await asyncio.sleep(delay)` in the async wrapper.

### 2. CORS allows all origins with credentials
**File:** `app/main.py:74-80`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,  # Dangerous with allow_origins=["*"]
)
```

Setting `allow_credentials=True` with `allow_origins=["*"]` is a security anti-pattern. Browsers won't send cookies with `*` origins, but this signals poor security intent. In production, this should use specific domain allowlists.

### 3. X-Forwarded-For header is spoofable (rate limit bypass)
**File:** `app/middleware/rate_limit.py:27-30`

```python
forwarded_for = request.headers.get("X-Forwarded-For")
if forwarded_for:
    return forwarded_for.split(",")[0].strip()
```

Any client can set `X-Forwarded-For` to bypass rate limiting. Without a trusted proxy configuration, this allows trivial rate limit evasion by sending a different IP in every request.

---

## HIGH Issues

### 4. `response.text` can be None (unchecked) in vision fallback
**File:** `app/services/pdf_extractor.py:316-317`

```python
response_text = response.text
response_data = json.loads(response_text)  # Crashes if None
```

The hybrid path at line 403 checks `if response_text is None`, but the vision fallback at line 316 does not. This will produce a confusing `TypeError` if Gemini returns an empty response via the vision path.

### 5. Duplicate detection returns `str()` instead of JSON
**File:** `app/routers/extraction.py:121-126`

```python
return Response(
    content=str(existing_result),  # Python repr, not valid JSON!
    media_type="application/json",
    ...
)
```

`str(existing_result)` produces Python dict representation (with single quotes, `True`/`False`, etc.), not valid JSON. Should be `json.dumps(existing_result)`.

### 6. Global mutable state for cache names is not thread-safe
**Files:** `app/services/pdf_extractor.py:73` and `app/services/memo_extractor.py:25`

```python
_EXTRACTION_CACHE_NAME: Optional[str] = None
_MEMO_CACHE_NAME: Optional[str] = None
```

These globals are read/written without any locking. Under concurrent requests, two workers could race to create caches simultaneously, wasting API calls and potentially leaving stale references.

### 7. `import json` scattered inside functions instead of at module top
**Files:** Multiple locations in `app/routers/extraction.py` (lines 361, 439, 520, 580, 695)

These repeated inline imports add minor overhead per request and violate PEP 8. Move to module-level imports.

### 8. Async functions wrapping synchronous Supabase calls
**Files:** All functions in `app/db/extractions.py` and `app/db/memo_extractions.py`

All database functions are declared `async` but call synchronous Supabase client methods (`client.table(...).execute()`). This blocks the event loop during database operations. Either use a truly async Supabase client or run these in `asyncio.to_thread()`.

---

## MEDIUM Issues

### 9. `datetime.utcnow()` is deprecated
**File:** `app/main.py:95`

```python
timestamp = datetime.utcnow().isoformat()
```

`datetime.utcnow()` is deprecated in Python 3.12+. Use `datetime.now(datetime.UTC).isoformat()` instead (the webhook sender already does this correctly at `webhook_sender.py:145`).

### 10. Retry decorator applied to sync function called without await
**File:** `app/services/memo_extractor.py:146-147`

```python
@retry_with_backoff()
def extract_memo_with_vision_fallback(...)  # sync function
```

This is a sync function, so the retry decorator returns a sync wrapper. However, `extract_memo_data_hybrid` (which is async) calls it directly at line 332 without `await`. This works because the sync wrapper returns the value directly, but the entire vision fallback (including file upload and API call) runs synchronously and blocks the event loop.

### 11. Error messages leak internal details
**File:** `app/routers/extraction.py:94,294`

```python
detail=f"Corrupted or invalid PDF: {str(e)}"
detail=f"Database error: {str(e)}"
```

Exception messages may contain stack traces, file paths, or database schema details. Production APIs should return generic error messages and log the details server-side.

### 12. Hardcoded `cost_savings_percent: 80` is misleading
**Files:** `app/services/pdf_extractor.py:498` and `app/services/memo_extractor.py:425`

```python
"cost_savings_percent": 80,  # Hardcoded, not actually calculated
```

This is a static claim, not a calculation. If input sizes vary, actual savings will differ. Consider calculating from actual token counts or marking it clearly as an estimate.

### 13. `list_all_extractions` doesn't include memo extractions
**File:** `app/routers/extraction.py:447-525`

The `GET /api/extractions` endpoint only queries the `extractions` table. Users expecting to list memos from this endpoint will get empty results. Should query `memo_extractions` when `doc_type=memo`.

### 14. `GeminiCompatibleModel` `json_schema_extra` is counterproductive
**File:** `app/models/extraction.py:19-24`

```python
model_config = ConfigDict(
    json_schema_extra={
        "additionalProperties": False
    }
)
```

This *adds* `additionalProperties: false` to the schema root, but `_remove_additional_properties()` then *removes* it. These work against each other. The utility already handles Gemini compatibility, so the config is unnecessary.

### 15. No request body size limit at the ASGI level

The 200MB check happens *after* reading the entire file into memory (`content = await file.read()`). A malicious client could send a multi-GB request that exhausts memory before the size check runs. Consider configuring uvicorn's `--limit-request-body` or adding streaming validation.

---

## LOW Issues

### 16. `PartialExtractionError` classes defined after usage
**Files:** `app/services/pdf_extractor.py:543` and `app/services/memo_extractor.py:472`

The exception classes are defined at the bottom of their modules, after the functions that raise them. While Python allows this (late binding), it's unconventional and reduces readability.

### 17. Duplicate `_slug()` function in two models
**Files:** `app/models/extraction.py:146-151` and `app/models/memo_extraction.py:158-163`

The identical `_slug()` helper is defined inline in both `build_canonical_filename()` methods. Extract to a shared utility.

### 18. `import re` inside method bodies
**Files:** `app/models/extraction.py:144` and `app/models/memo_extraction.py:151`

`import re` is done inside `build_canonical_filename()` on every call. Move to module-level.

### 19. `from typing import Any` imported inside function bodies
**Files:** `app/services/pdf_extractor.py:293` and `app/services/memo_extractor.py:218`

```python
from typing import Any
contents_list: list[Any] = [uploaded_file, prompt]
```

Unnecessary inline import. `Any` is already imported at module level in both files.

### 20. No `__init__.py` files verified
The `app/` directory structure should have `__init__.py` files in all packages for explicit package declaration. Missing ones could cause import issues depending on the Python path configuration.

---

## Architecture Observations

**Strengths:**
- Clean separation: models / services / routers / db / middleware
- Hybrid pipeline design is cost-effective and well-reasoned
- Comprehensive test coverage (273 tests)
- Good use of Pydantic for validation
- Proper file cleanup with `finally` blocks
- Quality-based routing with configurable thresholds
- Context caching for cost optimization

**Areas for improvement:**
- The `extractions.py` and `memo_extractions.py` DB modules are nearly identical (~95% code duplication). Consider a generic base or shared utility.
- The extraction router at 742 lines is getting large. Consider splitting memo-specific endpoints into their own router.
- No structured logging (using `print()` in main.py, `logging` elsewhere). Standardize on structured JSON logging for production observability.

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 3     |
| High     | 5     |
| Medium   | 7     |
| Low      | 5     |

**Priority fixes:**
1. Replace `time.sleep()` with `asyncio.sleep()` in the async retry wrapper
2. Fix the `str(existing_result)` JSON serialization bug
3. Address the async/sync mismatch in database and extractor calls
4. Tighten CORS and rate limit IP detection for production
