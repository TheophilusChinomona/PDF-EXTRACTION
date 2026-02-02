# Plan: Bridge Gap Analysis - PDF Extraction Service

## Scope
Address 28 actionable items from the 47 identified gaps (4 HIGH, 10 MEDIUM, 14 LOW). Organized into 5 phases by priority and dependency order.

---

## Phase 1: Database Integrity (HIGH)

### 1A. New migration `migrations/006_add_constraints_and_indexes.sql`
- Add unique partial index on `extractions(file_hash)` WHERE status IN ('completed', 'pending')
- Add unique partial index on `memo_extractions(file_hash)` WHERE status IN ('completed', 'pending')
- Add performance indexes: `file_hash`, `created_at DESC`, `status` on both tables
- Add CHECK constraint: `status != 'partial' OR groups IS NOT NULL` (Gap 8.1)

### 1B. Fix duplicate check race condition (Gap 1.1, 8.2)
**Files:** `app/db/extractions.py`, `app/db/memo_extractions.py`
- Change `create_extraction()` to use upsert pattern with ON CONFLICT handling
- Fix `raise Exception(...)` to use `raise ... from e` throughout (Gap 5.3)
- Add cross-table duplicate check helper

**File:** `app/routers/extraction.py:129-135`
- Check BOTH `extractions` and `memo_extractions` tables for duplicates before processing
- Handle constraint violation gracefully (return existing record on conflict)

### 1C. Supabase client singleton (Gap 2.3)
**File:** `app/db/supabase_client.py`
- Currently creates a **new client on every call** - confirmed by reading code
- Add module-level singleton with thread-safe initialization

---

## Phase 2: Resource Management & API Reliability (HIGH/MEDIUM)

### 2A. Temp file cleanup (Gap 3.1, 3.3)
**Files:** `app/routers/extraction.py:109-172`, `app/routers/batch.py:99+`
- Replace manual `os.path.join(tempfile.gettempdir(), ...)` with `tempfile.NamedTemporaryFile(delete=False)`
- Log cleanup failures instead of silently passing
- Add prefix `pdf_extraction_` for easy identification of orphaned files

### 2B. Gemini API quota vs rate limit detection (Gap 4.1)
**File:** `app/utils/retry.py:157-196`
- Add quota exhaustion detection in `_should_retry_exception()`
- Check for "quota exceeded", "billing", "insufficient quota" in error messages
- Do NOT retry on quota exhaustion (return immediately with descriptive error)
- Current code retries all 429s - need to distinguish rate limit from quota

### 2C. Gemini response validation (Gap 4.2)
**Files:** `app/services/pdf_extractor.py`, `app/services/memo_extractor.py`
- Wrap `json.loads()` in try/except with descriptive error
- Wrap `model_validate()` in try/except, log malformed response for debugging
- On schema validation failure, attempt partial extraction before failing

### 2D. Batch rename safety (Gap 1.2)
**File:** `app/services/batch_processor.py`
- Check if target exists before rename
- Use `shutil.move()` instead of `os.rename()`

---

## Phase 3: Input Validation & Security (MEDIUM)

### 3A. Filename sanitization hardening (Gap 6.1)
**File:** `app/services/file_validator.py:76-120`
- Add `unicodedata.normalize('NFKD', filename)` before sanitization
- Handle control characters explicitly
- Add Windows reserved name check (CON, PRN, AUX, NUL, COM1, LPT1)

### 3B. Webhook SSRF protection (Gap 6.3)
**File:** `app/services/webhook_sender.py:45-47`
- After HTTPS check, resolve hostname and block private/internal IPs
- Block: 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16
- Add URL length limit (2048 chars)

### 3C. Retry count logic fix (Gap 5.2, 8.3)
**File:** `app/routers/extraction.py:163`
- Check retry count BEFORE attempting extraction, not after
- If retry_count >= 5, reject immediately with clear message

---

## Phase 4: Observability (MEDIUM)

### 4A. Request ID middleware
**New file:** `app/middleware/request_id.py`
- Generate UUID per request, pass via `request.state.request_id`
- Return in `X-Request-ID` response header
- Register in `app/main.py`

### 4B. Structured logging with request context (Gap 10.2)
**Files:** `app/middleware/logging.py`, key service files
- Include request_id in all log messages
- Add structured fields: file_name, doc_type, processing_method
- Replace bare `f"Error: {str(e)}"` with contextual messages

### 4C. Enhanced health check (Gap 10.3)
**File:** `app/main.py` (health endpoint)
- Add disk space check via `shutil.disk_usage()`
- Return detailed status per dependency (already partially done)
- Add `X-Health-Detail` header with degraded components

---

## Phase 5: Batch & Low Priority (LOW)

### 5A. Batch timeout (Gap 7.1)
**File:** `app/routers/batch.py`
- Wrap batch processing loop in `asyncio.wait_for(timeout=3600)`
- On timeout, mark batch as "partial", return completed extractions

### 5B. Rate limit documentation (Gap 9.3)
**File:** `app/middleware/rate_limit.py`
- Add docstring noting in-memory limitation
- Add TODO comment for Redis backend in production

### 5C. Context cache cleanup (Gap 9.4, 3.2)
**Files:** `app/services/pdf_extractor.py`, `app/services/memo_extractor.py`
- Handle cache-not-found error gracefully when cache expires mid-request
- Clear global `_EXTRACTION_CACHE_NAME` on expiration

---

## Files Modified (Summary)

| File | Phases |
|------|--------|
| `migrations/006_add_constraints_and_indexes.sql` | 1A (new) |
| `app/db/supabase_client.py` | 1C |
| `app/db/extractions.py` | 1B |
| `app/db/memo_extractions.py` | 1B |
| `app/routers/extraction.py` | 1B, 2A, 3C |
| `app/routers/batch.py` | 2A, 5A |
| `app/utils/retry.py` | 2B |
| `app/services/pdf_extractor.py` | 2C, 5C |
| `app/services/memo_extractor.py` | 2C, 5C |
| `app/services/batch_processor.py` | 2D |
| `app/services/file_validator.py` | 3A |
| `app/services/webhook_sender.py` | 3B |
| `app/middleware/request_id.py` | 4A (new) |
| `app/middleware/logging.py` | 4B |
| `app/middleware/rate_limit.py` | 5B |
| `app/main.py` | 4A, 4C |

---

## Verification

After each phase:
1. Run `pytest tests/ -v` - all existing tests must pass
2. Run `python -m mypy app/` - type checks pass
3. Manual test: Upload a PDF via `/api/extract` and verify response

Phase-specific checks:
- **Phase 1:** Upload same PDF twice concurrently - no duplicates created
- **Phase 2:** Upload malformed PDF - graceful error, temp files cleaned
- **Phase 3:** Send webhook to `https://127.0.0.1/test` - blocked by SSRF check
- **Phase 4:** Check response headers for `X-Request-ID`
- **Phase 5:** Start 100-file batch - timeout triggers after configured limit
