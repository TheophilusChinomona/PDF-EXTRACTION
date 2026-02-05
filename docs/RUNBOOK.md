# Runbook

Operational procedures for deploying, monitoring, troubleshooting, and rolling back the PDF-Extraction service.

---

## Deployment

### Local Development

```bash
# 1. Ensure .env is configured (see docs/CONTRIB.md)

# 2. Start dev server with auto-reload
"C:\Python314\python.exe" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. Verify
curl http://localhost:8000/health
```

### Docker Production

```bash
# Build
docker build -t pdf-extraction:latest .

# Run
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  --name pdf-extraction \
  pdf-extraction:latest

# Scale with compose
docker-compose up -d --scale pdf-extraction=3
```

### Database Migrations

Migrations are applied manually via [Supabase Dashboard SQL Editor](https://supabase.com/dashboard/project/aqxgnvjqabitfvcnboah).

1. Open SQL Editor in Supabase Dashboard
2. Run migration files from `migrations/` directory in numerical order
3. Verify with: `SELECT * FROM information_schema.tables WHERE table_schema = 'public';`

Current migrations: `001` through `019`.

---

## Monitoring

### Health Check

```bash
curl http://localhost:8000/health
# Expected: {"status": "healthy", ...}
```

### Service Logs

```bash
# Docker
docker logs -f pdf-extraction

# Local
# Logs go to stdout with format: LEVEL: message
```

### Database Monitoring

```sql
-- Active batch jobs
SELECT id, status, total_files, completed_files, created_at
FROM batch_jobs
WHERE status NOT IN ('completed', 'failed')
ORDER BY created_at DESC;

-- Gemini Batch API jobs
SELECT id, gemini_job_name, status, total_requests, completed_requests, failed_requests
FROM gemini_batch_jobs
ORDER BY created_at DESC
LIMIT 10;

-- Extraction coverage
SELECT
  (SELECT count(*) FROM validation_results WHERE status = 'correct') as validated,
  (SELECT count(*) FROM extractions) as extracted_qp,
  (SELECT count(*) FROM memo_extractions) as extracted_mg;
```

### Batch Job Polling

```bash
# One-time check
python -m app.cli poll-batch-jobs --once

# Continuous polling (Ctrl+C to stop)
python -m app.cli poll-batch-jobs --interval 120
```

---

## Common Issues and Fixes

### All PDF downloads return 404

**Symptom**: `run_extraction_batch_from_validated.py` reports "ALL downloads failed".

**Cause**: `storage_path` values in `scraped_files` don't match actual Firebase Storage blob names.

**Fix**:
```bash
# 1. Diagnose the mismatch pattern
python scripts/diagnose_storage_paths.py --validated-only

# 2. Preview fixes
python scripts/fix_storage_paths.py --dry-run

# 3. Apply fixes
python scripts/fix_storage_paths.py --run

# 4. Verify
python scripts/run_extraction_batch_from_validated.py --dry-run
```

### Server won't start (port in use)

```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/macOS
lsof -ti:8000 | xargs kill -9
```

### API returns 429 (rate limited)

Wait for the rate limit window to reset. Check headers:
```bash
curl -I http://localhost:8000/api/extractions
# Look for: X-RateLimit-Remaining, X-RateLimit-Reset
```

### Gemini API errors

```bash
# Verify API key
echo %GEMINI_API_KEY%

# Test connectivity
curl "https://generativelanguage.googleapis.com/v1beta/models?key=%GEMINI_API_KEY%"
```

### Supabase connection fails

```bash
# Verify env vars
echo %SUPABASE_URL%
echo %SUPABASE_KEY%

# Test connection
python -c "from supabase import create_client; import os; c = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY']); print('OK')"
```

### Batch job stuck in pending

```sql
-- Check job status
SELECT * FROM gemini_batch_jobs WHERE status = 'pending' ORDER BY created_at DESC;

-- If Gemini job completed but wasn't processed, poll manually:
-- python -m app.cli poll-batch-jobs --once
```

### Extraction batch submits fewer files than expected

The script skips files that fail to download. Check the download log for specific errors:
```bash
# Use --min-files to set a threshold
python scripts/run_extraction_batch_from_validated.py --min-files 50

# Or proceed with whatever succeeded
python scripts/run_extraction_batch_from_validated.py --force
```

---

## Rollback Procedures

### Application Rollback

```bash
# Docker: roll back to previous image
docker stop pdf-extraction
docker run -d -p 8000:8000 --env-file .env --name pdf-extraction pdf-extraction:previous-tag

# Git: revert to previous commit
git log --oneline -5
git revert <commit-hash>
```

### Database Rollback

Migrations are forward-only. To undo a migration:

1. Write a reverse migration SQL script
2. Apply via Supabase Dashboard SQL Editor
3. Test thoroughly before deploying

**Do not** drop tables in production without a backup.

### Batch Job Rollback

If a batch job produced bad results:

```sql
-- 1. Find the batch job
SELECT id, created_at FROM batch_jobs WHERE id = '<batch_job_id>';

-- 2. Delete extractions created by this batch
DELETE FROM extractions WHERE batch_job_id = '<batch_job_id>';
DELETE FROM memo_extractions WHERE batch_job_id = '<batch_job_id>';

-- 3. Mark batch job as failed
UPDATE batch_jobs SET status = 'failed' WHERE id = '<batch_job_id>';
```

---

## Key Contacts and Resources

| Resource | Location |
|----------|----------|
| Supabase Dashboard | `https://supabase.com/dashboard/project/aqxgnvjqabitfvcnboah` |
| API Docs (running) | `http://localhost:8000/docs` |
| API Reference (static) | `api-documentation.md` |
| Operations Guide | `OPERATIONS.md` |
| Contributing Guide | `docs/CONTRIB.md` |
| Current Status | `docs/CURRENT_STATUS.md` |

---

Last updated: 2026-02-05
