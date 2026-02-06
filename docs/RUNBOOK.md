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

**Expected response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-02-06T12:00:00Z"
}
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

**Environment Variables:**
- Ensure `.env` file contains all required variables (see `docs/CONTRIB.md`)
- For production, set `ALLOWED_ORIGINS` to specific domain(s)
- Set `TRUSTED_PROXIES` if behind a load balancer

### Database Migrations

Migrations are applied manually via [Supabase Dashboard SQL Editor](https://supabase.com/dashboard/project/aqxgnvjqabitfvcnboah).

1. Open SQL Editor in Supabase Dashboard
2. Run migration files from `migrations/` directory in numerical order
3. Verify with: `SELECT * FROM information_schema.tables WHERE table_schema = 'public';`

Current migrations: `001` through `019`.

**Migration Checklist:**
- [ ] Backup database before applying migrations
- [ ] Test migrations on staging/dev environment first
- [ ] Verify all tables exist after migration
- [ ] Check for any migration errors in Supabase logs

---

## Monitoring

### Health Check

```bash
curl http://localhost:8000/health
# Expected: {"status": "healthy", ...}
```

**Health Check Endpoints:**
- `/health` - Basic health check
- `/version` - API version info

### Service Logs

```bash
# Docker
docker logs -f pdf-extraction

# Local (logs go to stdout)
# Format: LEVEL: message
```

**Log Levels:**
- `INFO` - Normal operations
- `WARNING` - Non-critical issues
- `ERROR` - Errors that don't stop the service
- `CRITICAL` - Service-stopping errors

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

-- Recent extractions
SELECT id, file_name, subject, grade, year, status, created_at
FROM extractions
ORDER BY created_at DESC
LIMIT 20;
```

### Batch Job Polling

```bash
# One-time check
python -m app.cli poll-batch-jobs --once

# Continuous polling (Ctrl+C to stop)
python -m app.cli poll-batch-jobs --interval 120

# Poll only extraction jobs
python -m app.cli poll-batch-jobs --once --job-type extraction
```

### Performance Metrics

**Key Metrics to Monitor:**
- API response times (should be < 2s for health checks)
- Batch job completion rates
- Gemini API quota usage
- Database connection pool usage
- Error rates (4xx/5xx responses)

**Monitoring Queries:**
```sql
-- Failed extractions in last 24 hours
SELECT count(*) FROM extractions
WHERE status = 'failed'
AND created_at > NOW() - INTERVAL '24 hours';

-- Average processing time per extraction
SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) as avg_seconds
FROM extractions
WHERE status = 'completed';
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

# Or use a different port
python -m uvicorn app.main:app --reload --port 8001
```

### API returns 429 (rate limited)

Wait for the rate limit window to reset. Check headers:
```bash
curl -I http://localhost:8000/api/extractions
# Look for: X-RateLimit-Remaining, X-RateLimit-Reset
```

**Rate Limits:**
- `/health`, `/version`: 200/min
- `/api/extract`: 10/min
- `/api/batch`: 2/min
- Other endpoints: 100/min

### Gemini API errors

```bash
# Verify API key
echo %GEMINI_API_KEY%  # Windows
echo $GEMINI_API_KEY   # Linux/macOS

# Test connectivity
curl "https://generativelanguage.googleapis.com/v1beta/models?key=%GEMINI_API_KEY%"
```

**Common Gemini API Errors:**
- `401 Unauthorized` - Invalid API key
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Gemini service issue (retry)

### Supabase connection fails

```bash
# Verify env vars
echo %SUPABASE_URL%    # Windows
echo $SUPABASE_URL     # Linux/macOS
echo %SUPABASE_KEY%

# Test connection
python -c "from supabase import create_client; import os; c = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY']); print('OK')"
```

**Common Supabase Errors:**
- Connection timeout - Check network/firewall
- `401 Unauthorized` - Invalid API key
- `404 Not Found` - Incorrect project URL

### Batch job stuck in pending

```sql
-- Check job status
SELECT * FROM gemini_batch_jobs WHERE status = 'pending' ORDER BY created_at DESC;

-- If Gemini job completed but wasn't processed, poll manually:
-- python -m app.cli poll-batch-jobs --once
```

**Troubleshooting Steps:**
1. Check Gemini Batch API job status via Google Cloud Console
2. Verify job completed successfully in Gemini dashboard
3. Run poll command manually to process results
4. Check logs for processing errors

### Extraction batch submits fewer files than expected

The script skips files that fail to download. Check the download log for specific errors:
```bash
# Use --min-files to set a threshold
python scripts/run_extraction_batch_from_validated.py --min-files 50

# Or proceed with whatever succeeded
python scripts/run_extraction_batch_from_validated.py --force
```

### Import errors / missing dependencies

```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Verify Python version
python --version  # Should be 3.11+

# Check for conflicting packages
pip list | grep -i <package-name>
```

### CORS errors in browser

**Symptom**: Browser console shows CORS policy errors when calling API.

**Fix**: Update `ALLOWED_ORIGINS` in `.env`:
```env
# Development
ALLOWED_ORIGINS=*

# Production (specific domains)
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
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

# Or checkout previous version
git checkout <commit-hash>
```

### Database Rollback

Migrations are forward-only. To undo a migration:

1. Write a reverse migration SQL script
2. Apply via Supabase Dashboard SQL Editor
3. Test thoroughly before deploying

**⚠️ Warning:** Do not drop tables in production without a backup.

**Backup Before Rollback:**
```sql
-- Create backup table
CREATE TABLE extractions_backup AS SELECT * FROM extractions;

-- Verify backup
SELECT count(*) FROM extractions_backup;
```

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

**⚠️ Warning:** Always verify batch_job_id before deleting records.

### Gemini Batch Job Rollback

```sql
-- Mark Gemini batch job as failed (prevents reprocessing)
UPDATE gemini_batch_jobs 
SET status = 'failed', error_message = 'Manually rolled back'
WHERE id = '<gemini_batch_job_id>';
```

---

## Emergency Procedures

### Service Down

1. **Check health endpoint**: `curl http://localhost:8000/health`
2. **Check logs**: `docker logs pdf-extraction` or check stdout
3. **Restart service**: `docker restart pdf-extraction` or restart uvicorn
4. **Check database connectivity**: See "Supabase connection fails" above
5. **Check disk space**: `df -h` (Linux) or check Windows disk usage

### Data Corruption

1. **Stop service immediately**: Prevent further writes
2. **Identify affected records**: Query for anomalies
3. **Restore from backup**: Use Supabase point-in-time recovery if available
4. **Verify data integrity**: Run validation queries
5. **Resume service**: After verification

### API Key Compromised

1. **Rotate API key immediately**: Generate new key in Google Cloud Console / Supabase Dashboard
2. **Update `.env` file**: Replace compromised key
3. **Restart service**: Apply new configuration
4. **Revoke old key**: Disable compromised key
5. **Monitor for unauthorized usage**: Check API logs

---

## Key Contacts and Resources

| Resource | Location |
|----------|----------|
| Supabase Dashboard | `https://supabase.com/dashboard/project/aqxgnvjqabitfvcnboah` |
| API Docs (running) | `http://localhost:8000/docs` |
| API Reference (static) | `api-documentation.md` |
| Contributing Guide | `docs/CONTRIB.md` |
| Current Status | `docs/CURRENT_STATUS.md` |
| Environment Template | `.env.example` |

---

## Maintenance Windows

**Recommended maintenance schedule:**
- **Weekly**: Review batch job status, check for stuck jobs
- **Monthly**: Review extraction coverage, run database diagnostics
- **Quarterly**: Review and update dependencies, security patches

**Pre-maintenance checklist:**
- [ ] Backup database
- [ ] Notify stakeholders
- [ ] Document changes
- [ ] Test rollback procedure

---

Last updated: 2026-02-06
