# PDF-Extraction Service

Microservice for extracting structured data from academic PDFs using hybrid OpenDataLoader + Gemini pipeline. Achieves 80% cost reduction and 95%+ accuracy.

---

## Current Project State (Feb 2026)

### Gemini Batch API Implementation (COMPLETE)

The service now supports **Gemini Batch API** for both validation and extraction, providing 50% cost savings on large batches (100+ files). Key components:

| File | Purpose |
|------|---------|
| `app/services/gemini_batch.py` | Core batch API: create_batch_job, poll_batch_job, download_batch_results |
| `app/services/validation_batch.py` | Batch validation: submit_validation_batch, process_validation_batch_results |
| `app/services/extraction_batch.py` | Batch extraction: submit_extraction_batch, process_extraction_batch_results |
| `app/services/batch_job_poller.py` | Background poller for pending Gemini batch jobs |
| `app/db/gemini_batch_jobs.py` | CRUD for gemini_batch_jobs table |
| `migrations/018_gemini_batch_jobs.sql` | Database table for tracking Gemini batch jobs |

### Key CLI Commands

```bash
# Poll pending Gemini Batch API jobs
python -m app.cli poll-batch-jobs --once
python -m app.cli poll-batch-jobs --interval 120

# Test extraction batch from validated files
python scripts/run_extraction_batch_from_validated.py --dry-run
python scripts/run_extraction_batch_from_validated.py
```

### API Endpoints with Batch Support

- `POST /api/batch` - Add `use_batch_api=true` for Gemini Batch API mode
- `POST /api/validation/batch` - Automatically uses Batch API when >= 100 files
- `GET /api/batch/{job_id}` - Includes `gemini_batch_job_id` if batch API was used

### Database Tables

- `gemini_batch_jobs` - Tracks Gemini Batch API jobs (status, requests, results)
- `batch_jobs` - Internal batch job tracking (linked via source_job_id)
- `validation_results` - Validation outcomes per scraped file
- `extractions` / `memo_extractions` - Extraction results with scraped_file_id link

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `"C:\Python314\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000` | Start server |
| `"C:\Python314\python.exe" scripts/<script>.py` | Run scripts |
| `pytest tests/ -v --cov=app` | Run tests |
| `python -m app.cli poll-batch-jobs --once` | Poll Gemini batch jobs |

**Note:** No local venv - use system Python (`C:\Python314\python.exe`) for all operations.

---

## Environment Variables

Key `.env` variables for batch operations:

```env
GEMINI_API_KEY=...
SUPABASE_URL=...
SUPABASE_KEY=...                          # anon key for API
SUPABASE_SERVICE_ROLE_KEY=...             # service role for scripts (bypasses RLS)
FIREBASE_CREDENTIALS_PATH=...             # Path to Firebase service account JSON
```

---

## SQL Migrations

No CLI tools available. Use Supabase Dashboard SQL Editor:
`https://supabase.com/dashboard/project/aqxgnvjqabitfvcnboah`

---

## Ralph Agents

If you are an autonomous agent, read `scripts/ralph/CLAUDE.md` first.

---

## Detailed Guidelines

- [Architecture](instructions/architecture.md) - Tech stack, file structure, hybrid pipeline
- [Python Patterns](instructions/python-patterns.md) - Code style, Gemini SDK, extraction patterns
- [Environment Setup](instructions/environment.md) - Python interpreter, env vars, migrations
- [Security](instructions/security.md) - API keys, PDF safety, data privacy
- [Testing](instructions/testing.md) - Test commands and coverage
- [Ralph Workflow](instructions/ralph-workflow.md) - Autonomous agent instructions

---

## References

- **Current Status:** `docs/CURRENT_STATUS.md` - Active batch jobs and recent changes
- **PRD:** `.claude/tasks/prd-pdf-extraction-service.md`
- **Tasks:** `.claude/tasks/todo.md`
- **Batch API Plan:** `.cursor/plans/gemini_batch_api_implementation_*.plan.md`
- **Global Rules:** `~/.claude/CLAUDE.md`
