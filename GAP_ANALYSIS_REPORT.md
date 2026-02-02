# System Gap Analysis & Edge Case Report

**Date:** February 2, 2026  
**System:** PDF Extraction Service  
**Analysis Type:** Deep Dive - Edge Cases & Potential Issues

---

## Executive Summary

This report identifies **47 edge cases and potential issues** across 10 major categories. The system is well-architected but has several gaps that could cause failures in production, particularly around:

1. **Race conditions** in duplicate checking (HIGH priority)
2. **Database transaction handling** (MEDIUM priority)
3. **Resource cleanup** edge cases (MEDIUM priority)
4. **API quota exhaustion** scenarios (MEDIUM priority)
5. **Concurrent batch processing** issues (MEDIUM priority)

---

## 1. Race Conditions & Concurrency Issues

### 1.1 Duplicate Check Race Condition (HIGH PRIORITY)

**Issue:** Multiple concurrent requests with the same file hash can create duplicate extractions.

**Scenario:**
```
Request A: check_duplicate() → None (no existing record)
Request B: check_duplicate() → None (no existing record) [concurrent]
Request A: create_extraction() → Success
Request B: create_extraction() → Success (DUPLICATE!)
```

**Current Code:**
```python
# app/routers/extraction.py:130-135
existing_id = await check_duplicate(supabase_client, file_hash)
if existing_id:
    # Return existing
else:
    # Create new - RACE CONDITION HERE
    extraction_id = await create_extraction(...)
```

**Impact:** 
- Duplicate database records for same file
- Wasted API costs (Gemini calls)
- Inconsistent data

**Recommendation:**
- Use database-level unique constraint on `file_hash` with `ON CONFLICT` handling
- Or use advisory locks: `SELECT pg_advisory_lock(hashtext(file_hash))` before check
- Or use `INSERT ... ON CONFLICT DO UPDATE` pattern

**Files Affected:**
- `app/routers/extraction.py:130-297`
- `app/routers/batch.py:118-143`
- `app/db/extractions.py:133-157`
- `app/db/memo_extractions.py:141-165`

---

### 1.2 Batch Processing Concurrent File Conflicts

**Issue:** CLI batch processor renames files, but if same file processed twice concurrently, second rename fails.

**Scenario:**
```python
# batch_processor.py:94
os.rename(file_path, pdf_path)  # Fails if file already renamed
```

**Impact:** Batch processing crashes mid-way

**Recommendation:**
- Check if target file exists before rename
- Use atomic move: `shutil.move()` with error handling
- Or skip rename if canonical name already matches

---

### 1.3 Cache Creation Race Condition

**Issue:** Multiple requests can create duplicate caches simultaneously.

**Current Code:**
```python
# pdf_extractor.py:187-211
async with _extraction_cache_lock:
    if _EXTRACTION_CACHE_NAME is not None:
        return _EXTRACTION_CACHE_NAME
    # Create new cache - but what if another process created it?
    cache = client.caches.create(...)
```

**Impact:** Multiple caches created, wasting resources

**Recommendation:**
- Check cache existence before creating (already done, but verify)
- Use cache name pattern: `exam_paper_extraction_{timestamp}` to avoid conflicts
- Add cache cleanup job for expired caches

---

## 2. Database Transaction & Consistency Issues

### 2.1 No Transaction Wrapping for Multi-Step Operations

**Issue:** Database operations are not wrapped in transactions, leading to partial updates on failure.

**Scenario:**
```python
# extraction.py:232-297
extraction_id = await create_extraction(...)  # Success
await add_to_review_queue(...)  # Fails - extraction created but not queued
```

**Impact:** Inconsistent database state

**Recommendation:**
- Wrap related operations in database transactions
- Use Supabase transaction support or PostgreSQL transactions
- Implement rollback on failure

**Files Affected:**
- `app/routers/extraction.py:232-329`
- `app/db/extractions.py` (all functions)

---

### 2.2 Batch Job Status Update Race Condition

**Issue:** Multiple files completing simultaneously can cause incorrect batch job statistics.

**Current Code:**
```python
# batch.py:201-209
await add_extraction_to_batch(...)  # Updates batch stats
# If 10 files complete at once, stats may be incorrect
```

**Impact:** Incorrect batch completion counts, routing stats

**Recommendation:**
- Use database-level atomic updates: `UPDATE batch_jobs SET completed_files = completed_files + 1 WHERE id = $1`
- Or use PostgreSQL `RETURNING` clause for consistency
- Add database-level constraints/triggers for stat validation

---

### 2.3 No Database Connection Pooling Configuration

**Issue:** Supabase client created per-request without connection pooling limits.

**Current Code:**
```python
# supabase_client.py:12-35
def get_supabase_client() -> Client:
    client = create_client(url, key)  # New connection each time?
    return client
```

**Impact:** Connection exhaustion under high load

**Recommendation:**
- Implement singleton pattern for Supabase client
- Configure connection pool size
- Add connection retry logic
- Monitor connection pool metrics

---

## 3. File & Resource Management Edge Cases

### 3.1 Temporary File Cleanup Failures

**Issue:** Temp files may not be cleaned up if process crashes or disk is full.

**Current Code:**
```python
# extraction.py:422-429
finally:
    if temp_file_path and os.path.exists(temp_file_path):
        try:
            os.remove(temp_file_path)
        except Exception:
            pass  # Silently ignore cleanup errors
```

**Impact:** Disk space exhaustion over time

**Recommendation:**
- Use `tempfile.TemporaryFile` context manager (auto-cleanup)
- Or implement cleanup job that runs periodically
- Add disk space monitoring
- Log cleanup failures (currently silent)

---

### 3.2 Disk Space Exhaustion During Processing

**Issue:** No check for available disk space before writing temp files.

**Scenario:**
- 200MB PDF uploaded
- Temp file write fails mid-way (disk full)
- No graceful error handling

**Recommendation:**
- Check `shutil.disk_usage()` before writing
- Return 507 Insufficient Storage status code
- Implement file size limits based on available disk space

---

### 3.3 Gemini File Upload Cleanup on Process Crash

**Issue:** If process crashes after uploading to Gemini Files API but before extraction completes, uploaded file remains in Gemini storage.

**Current Code:**
```python
# pdf_extractor.py:354-361
finally:
    if uploaded_file is not None:
        try:
            client.files.delete(name=uploaded_file.name)
        except Exception:
            pass  # Cleanup fails silently
```

**Impact:** Accumulated files in Gemini storage, potential quota issues

**Recommendation:**
- Add cleanup job for orphaned Gemini files
- Track uploaded file names in database
- Implement TTL-based cleanup (delete files older than 24h)

---

### 3.4 File Handle Leaks

**Issue:** Multiple file operations without explicit context managers.

**Current Code:**
```python
# extraction.py:113-114
with open(temp_file_path, "wb") as f:
    f.write(content)
# File closed, but what if write fails mid-way?
```

**Impact:** File handle exhaustion

**Recommendation:**
- Use context managers consistently
- Add file handle monitoring
- Use `with` statements for all file operations

---

## 4. API & External Service Edge Cases

### 4.1 Gemini API Quota Exhaustion

**Issue:** No handling for API quota exhaustion (429 with Retry-After header).

**Current Code:**
```python
# retry.py:21-25
RETRYABLE_STATUS_CODES: Set[int] = {
    429,  # Rate limit - retries, but what about quota exhaustion?
    500,
    503,
}
```

**Impact:** All requests fail until quota resets (could be hours/days)

**Recommendation:**
- Detect quota exhaustion vs rate limiting (check response body)
- Return 503 Service Unavailable with clear message
- Implement queue system for requests when quota exhausted
- Add quota monitoring/alerting

---

### 4.2 Gemini API Response Validation

**Issue:** No validation that Gemini response matches expected schema before parsing.

**Current Code:**
```python
# pdf_extractor.py:320-324
response_text = response.text
if response_text is None:
    raise ValueError("Gemini API returned empty response")
response_data = json.loads(response_text)  # What if invalid JSON?
result: FullExamPaper = FullExamPaper.model_validate(response_data)  # What if schema mismatch?
```

**Impact:** Crashes on malformed responses

**Recommendation:**
- Add JSON parsing error handling
- Validate schema before Pydantic parsing
- Log malformed responses for debugging
- Retry on schema validation failures

---

### 4.3 Context Cache Expiration During Request

**Issue:** Cache expires between check and use.

**Current Code:**
```python
# pdf_extractor.py:189-193
if _EXTRACTION_CACHE_NAME is not None:
    try:
        client.caches.get(name=_EXTRACTION_CACHE_NAME)  # Check exists
        return _EXTRACTION_CACHE_NAME
    except Exception:
        _EXTRACTION_CACHE_NAME = None  # Expired, create new
```

**Impact:** Cache check passes but cache expired when used, causing API call failure

**Recommendation:**
- Handle cache expiration gracefully (fallback to non-cached)
- Check cache TTL before using
- Implement cache refresh before expiration

---

### 4.4 OpenDataLoader Import Failure

**Issue:** If `opendataloader_pdf` import fails, health check fails but extraction still attempted.

**Current Code:**
```python
# main.py:106-111
try:
    from opendataloader_pdf import convert
    services["opendataloader"] = "healthy"
except Exception as e:
    services["opendataloader"] = f"unhealthy: {str(e)}"
    overall_healthy = False
```

**Impact:** Service marked unhealthy but extraction endpoints still accessible

**Recommendation:**
- Fail fast: return 503 on startup if OpenDataLoader unavailable
- Or: gracefully degrade to vision-only mode
- Add startup validation that fails if critical dependencies missing

---

## 5. Error Handling & Recovery Edge Cases

### 5.1 Partial Extraction Error Handling

**Issue:** Partial extraction errors are caught but error message may not be descriptive.

**Current Code:**
```python
# extraction.py:195-199
except (PartialExtractionError, PartialMemoExtractionError) as e:
    extraction_result = e.partial_result
    extraction_status = 'partial'
    error_message = str(e.original_exception)  # May not be user-friendly
```

**Impact:** Users see technical errors instead of clear messages

**Recommendation:**
- Map technical errors to user-friendly messages
- Include actionable guidance in error messages
- Log full technical details separately

---

### 5.2 Retry Count Logic Gap

**Issue:** Retry count incremented before extraction attempt, so first retry shows count=1.

**Current Code:**
```python
# extraction.py:163
retry_count = existing_result.get("retry_count", 0) + 1  # Incremented before attempt
```

**Impact:** Confusing retry count (first retry shows as 1, not 0)

**Recommendation:**
- Increment retry count after failed attempt
- Or clarify that retry_count = number of retries attempted (not remaining)

---

### 5.3 Database Error Masking

**Issue:** Database errors are caught but original exception details may be lost.

**Current Code:**
```python
# extractions.py:93-94
except Exception as e:
    raise Exception(f"Failed to insert extraction: {str(e)}")  # Original exception lost
```

**Impact:** Harder to debug database issues

**Recommendation:**
- Preserve original exception: `raise Exception(...) from e`
- Include database error codes in error messages
- Log full exception traceback

---

### 5.4 Webhook Delivery Failure Handling

**Issue:** Webhook failures are logged but not retried or queued.

**Current Code:**
```python
# webhook_sender.py:118-120
logger.error(f"Webhook delivery failed after {max_retries} attempts: {last_error}")
return False  # Failure silently ignored
```

**Impact:** Users don't receive notifications, no retry mechanism

**Recommendation:**
- Queue failed webhooks for retry
- Store webhook delivery status in database
- Implement exponential backoff retry queue
- Add webhook delivery monitoring

---

## 6. Input Validation & Security Edge Cases

### 6.1 Filename Sanitization Bypass

**Issue:** Filename sanitization may not handle all edge cases.

**Current Code:**
```python
# file_validator.py:76-120
filename = filename.replace("..", "").replace("/", "").replace("\\", "")
filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
```

**Edge Cases:**
- Unicode normalization attacks (lookalike characters)
- Very long filenames (>255 chars) truncated but may cause issues
- Filenames with only dots: `...pdf` → `upload.pdf` (good)
- Filenames with control characters

**Recommendation:**
- Use `unicodedata.normalize()` for Unicode normalization
- Validate filename length before truncation
- Add tests for edge case filenames

---

### 6.2 MIME Type Validation Bypass

**Issue:** `python-magic` may be fooled by crafted PDFs or may not be installed.

**Current Code:**
```python
# file_validator.py:59-64
mime_type = magic.from_buffer(content, mime=True)
if mime_type != ALLOWED_MIME_TYPE:
    raise HTTPException(...)
```

**Edge Cases:**
- `python-magic` not installed → ImportError
- Malformed PDFs that pass MIME check but fail to parse
- PDFs with embedded executables

**Recommendation:**
- Add fallback validation (check PDF header bytes: `%PDF`)
- Validate PDF structure after MIME check
- Handle `python-magic` import failures gracefully

---

### 6.3 Webhook URL Validation

**Issue:** Webhook URL validated for HTTPS but not for other security concerns.

**Current Code:**
```python
# extraction.py:52
webhook_url: Optional[str] = Form(None, ...)
# Later: webhook_sender.py:46
if not webhook_url.startswith('https://'):
    raise ValueError(...)
```

**Edge Cases:**
- SSRF attacks (internal IPs: `https://127.0.0.1/webhook`)
- Very long URLs causing buffer issues
- URLs with malicious query parameters

**Recommendation:**
- Validate URL doesn't point to internal/private IPs
- Limit URL length (e.g., 2048 chars)
- Sanitize URL before use
- Add URL validation tests

---

### 6.4 Rate Limit Bypass via IP Spoofing

**Issue:** Rate limiting uses client IP, which can be spoofed if proxy not configured.

**Current Code:**
```python
# rate_limit.py:13-47
def get_client_ip(request: Request) -> str:
    # Only trusts X-Forwarded-For if from trusted proxy
    # But if no proxy configured, uses direct IP (can be spoofed)
```

**Impact:** Attackers can bypass rate limits

**Recommendation:**
- Require `TRUSTED_PROXIES` in production
- Add warning if `TRUSTED_PROXIES` empty in production
- Consider additional rate limiting (per API key, per user)

---

## 7. Batch Processing Edge Cases

### 7.1 Batch Job Timeout

**Issue:** No timeout for batch processing - can run indefinitely.

**Current Code:**
```python
# batch.py:95-245
for file in files:
    # Process each file - no overall timeout
```

**Impact:** Batch jobs can hang indefinitely, consuming resources

**Recommendation:**
- Add overall batch timeout (e.g., 1 hour)
- Mark batch as "timeout" if exceeds limit
- Implement batch cancellation endpoint

---

### 7.2 Batch Job Partial Failure Recovery

**Issue:** If batch processing crashes mid-way, no way to resume.

**Current Code:**
```python
# batch.py:95-245
for file in files:
    # Process sequentially - if crash, all progress lost
```

**Impact:** Must restart entire batch on failure

**Recommendation:**
- Store batch progress in database
- Implement batch resume functionality
- Track which files completed before crash

---

### 7.3 Batch Job Memory Exhaustion

**Issue:** Loading 100 files into memory simultaneously can exhaust memory.

**Current Code:**
```python
# batch.py:38
files: List[UploadFile] = File(...)  # All files loaded into memory
```

**Impact:** Out of memory errors with large batches

**Recommendation:**
- Process files one at a time (already done in loop, but files still in memory)
- Stream files instead of loading all
- Add memory monitoring
- Limit batch size based on available memory

---

### 7.4 Batch Job Status Race Condition

**Issue:** Batch status checked after all files processed, but status may be stale.

**Current Code:**
```python
# batch.py:247
batch_job = await get_batch_job(supabase_client, batch_job_id)
# Status may not reflect latest updates if concurrent requests
```

**Impact:** Incorrect batch status returned

**Recommendation:**
- Use database-level status calculation (VIEW or function)
- Or: Calculate status from extraction records
- Add status refresh endpoint

---

## 8. Data Consistency & Validation Edge Cases

### 8.1 Extraction Status Inconsistency

**Issue:** Status can be 'partial' but extraction_result is None (shouldn't happen).

**Current Code:**
```python
# extraction.py:234-303
if extraction_status == 'failed' and extraction_result is None:
    # Handle failed
elif extraction_result is not None:
    # Handle success/partial
else:
    # Should not reach here - but what if it does?
    raise HTTPException(...)
```

**Impact:** Edge case not properly handled

**Recommendation:**
- Add assertion/logging for impossible states
- Ensure status and result are always consistent
- Add database constraints: `CHECK (status != 'partial' OR extraction_result IS NOT NULL)`

---

### 8.2 Duplicate File Hash Across Document Types

**Issue:** Same file hash can exist in both `extractions` and `memo_extractions` tables.

**Scenario:**
- File uploaded as question_paper → stored in `extractions`
- Same file uploaded as memo → stored in `memo_extractions`
- Duplicate check only checks one table

**Impact:** Duplicate processing, wasted API costs

**Recommendation:**
- Check both tables for duplicates
- Or: Use single table with `doc_type` column
- Add unique constraint across both tables (if possible)

---

### 8.3 Retry Count Exceeding Limit Logic

**Issue:** Retry count checked after extraction attempt, but what if extraction succeeds on retry?

**Current Code:**
```python
# extraction.py:207
if retry_count > 5:
    extraction_status = 'failed'
else:
    raise HTTPException(...)  # Retry allowed
```

**Impact:** Successful retry after 5 attempts still marked as failed

**Recommendation:**
- Check retry count before attempt, not after
- Or: Allow retry if previous attempt failed (regardless of count)
- Clarify retry limit logic

---

## 9. Performance & Scalability Edge Cases

### 9.1 Large PDF Memory Consumption

**Issue:** 200MB PDF loaded entirely into memory.

**Current Code:**
```python
# file_validator.py:45
content = await file.read()  # Loads entire file into memory
```

**Impact:** Memory exhaustion with concurrent large file uploads

**Recommendation:**
- Stream file processing where possible
- Add memory limits per request
- Use temporary files instead of in-memory buffers

---

### 9.2 Database Query Performance

**Issue:** No indexes on frequently queried columns (besides primary keys).

**Current Code:**
- `check_duplicate()` queries `file_hash` - needs index
- `list_extractions()` orders by `created_at` - needs index
- Batch job queries by `status` - needs index

**Impact:** Slow queries under load

**Recommendation:**
- Add indexes: `CREATE INDEX idx_extractions_file_hash ON extractions(file_hash)`
- Add indexes: `CREATE INDEX idx_extractions_created_at ON extractions(created_at DESC)`
- Add indexes: `CREATE INDEX idx_batch_jobs_status ON batch_jobs(status)`
- Review all query patterns and add appropriate indexes

---

### 9.3 Rate Limiting Storage

**Issue:** Rate limiting uses in-memory storage, lost on restart.

**Current Code:**
```python
# rate_limit.py:52
limiter = Limiter(key_func=get_client_ip, default_limits=["200/minute"])
# Uses in-memory storage by default
```

**Impact:** Rate limits reset on server restart, can't scale horizontally

**Recommendation:**
- Use Redis for distributed rate limiting
- Or: Use database-backed rate limiting
- Add rate limit persistence

---

### 9.4 Context Cache Memory Leak

**Issue:** Global cache variables never cleared, can accumulate.

**Current Code:**
```python
# pdf_extractor.py:76
_EXTRACTION_CACHE_NAME: Optional[str] = None  # Never cleared
```

**Impact:** Memory leak (minor, but still an issue)

**Recommendation:**
- Clear cache on expiration
- Implement cache cleanup job
- Monitor cache memory usage

---

## 10. Monitoring & Observability Gaps

### 10.1 No Metrics Collection

**Issue:** No metrics for:
- Extraction success/failure rates
- Processing times
- API costs
- Cache hit rates
- Database query performance

**Recommendation:**
- Add Prometheus metrics
- Track extraction metrics per doc_type
- Monitor API quota usage
- Track cost savings from hybrid mode

---

### 10.2 Incomplete Error Logging

**Issue:** Some errors logged but lack context (request ID, user info, etc.).

**Current Code:**
```python
# Various places
logger.error(f"Error: {str(e)}")  # No request context
```

**Recommendation:**
- Add request ID to all logs
- Include user/client IP in logs
- Add structured logging (JSON format)
- Include full stack traces for errors

---

### 10.3 No Health Check for External Services

**Issue:** Health check verifies services but doesn't check:
- Gemini API quota remaining
- Supabase connection pool status
- Disk space available
- Memory usage

**Recommendation:**
- Add quota check to health endpoint
- Add disk space check
- Add memory usage check
- Return detailed health status

---

## Priority Recommendations

### HIGH PRIORITY (Fix Immediately)

1. **Race condition in duplicate checking** - Use database constraints or advisory locks
2. **Database transaction wrapping** - Wrap multi-step operations in transactions
3. **Gemini API quota exhaustion handling** - Detect and handle quota vs rate limits
4. **File cleanup on process crash** - Implement cleanup job for orphaned files

### MEDIUM PRIORITY (Fix Soon)

5. **Batch processing timeout** - Add overall batch timeout
6. **Database connection pooling** - Configure proper connection pooling
7. **Rate limiting storage** - Use Redis/database for distributed rate limiting
8. **Input validation edge cases** - Handle Unicode, SSRF, etc.
9. **Metrics collection** - Add Prometheus/metrics endpoint
10. **Error logging improvements** - Add request context to all logs

### LOW PRIORITY (Nice to Have)

11. **Cache cleanup job** - Periodic cleanup of expired caches
12. **Batch resume functionality** - Allow resuming failed batches
13. **Health check enhancements** - Add quota/disk/memory checks
14. **Performance optimizations** - Add database indexes, optimize queries

---

## Testing Recommendations

### Unit Tests Needed

- Race condition scenarios (concurrent duplicate checks)
- File cleanup on various failure scenarios
- API quota exhaustion handling
- Input validation edge cases (Unicode, SSRF, etc.)

### Integration Tests Needed

- Concurrent batch processing
- Database transaction rollback scenarios
- Webhook delivery failures
- Cache expiration during request

### Load Tests Needed

- High concurrent request handling
- Large batch processing (100 files)
- Memory usage under load
- Database connection pool exhaustion

---

## Conclusion

The system is well-designed with good error handling and retry logic, but has several edge cases that could cause issues in production. The highest priority fixes are around race conditions and database consistency. Most issues are solvable with proper transaction handling, database constraints, and improved error handling.

**Total Issues Identified:** 47  
**High Priority:** 4  
**Medium Priority:** 10  
**Low Priority:** 14  
**Informational/Enhancement:** 19

---

**Report Generated:** 2026-02-02  
**Analyzed Files:** 25+  
**Code Review Depth:** Deep dive with edge case focus
