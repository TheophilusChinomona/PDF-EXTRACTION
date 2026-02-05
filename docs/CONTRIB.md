# Contributing Guide

Development workflow, environment setup, and scripts reference for PDF-Extraction.

---

## Environment Setup

### Prerequisites

- **Python 3.11+** (project uses system Python at `C:\Python314\python.exe`)
- **Supabase project** with migrations applied
- **Google Gemini API key**
- **Firebase service account** (for storage operations)

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure Environment

Copy `.env.example` to `.env` and fill in values:

```bash
cp .env.example .env
```

#### Required Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key |
| `SUPABASE_URL` | Supabase project URL (`https://xxx.supabase.co`) |
| `SUPABASE_KEY` | Supabase anon key |

#### Script Variables (needed for scripts that bypass RLS)

| Variable | Description |
|----------|-------------|
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (Dashboard > Project Settings > API) |
| `FIREBASE_CREDENTIALS_PATH` | Path to Firebase service account JSON file |

#### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_NAME` | `gemini-3-flash-preview` | Gemini model for extraction |
| `ENABLE_HYBRID_MODE` | `true` | Use OpenDataLoader + Gemini hybrid |
| `ALLOWED_ORIGINS` | `*` | CORS origins (restrict in production) |
| `TRUSTED_PROXIES` | _(empty)_ | Trusted proxy IPs for rate limiting |
| `BATCH_WORKERS` | `1` | Parallel PDF processing (CLI) |
| `BATCH_API_LIMIT` | `3` | Max concurrent Gemini API calls |
| `BATCH_API_THRESHOLD` | `100` | Min files to trigger Batch API mode |
| `BATCH_API_POLL_INTERVAL` | `60` | Seconds between batch job polls |
| `BATCH_API_MODEL` | `models/gemini-2.5-flash` | Model for Batch API jobs |

### Apply Database Migrations

Run SQL files from `migrations/` in order via [Supabase Dashboard SQL Editor](https://supabase.com/dashboard/project/aqxgnvjqabitfvcnboah):

```
migrations/001_*.sql through migrations/019_*.sql
```

No CLI migration tool is available; use the dashboard.

---

## Development Workflow

### Start the Server

```bash
"C:\Python314\python.exe" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/health

### Run Tests

```bash
# All tests with coverage
pytest tests/ -v --cov=app

# Specific test file
pytest tests/test_extraction_router.py -v
```

### Commit Convention

```
<type>: <description>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`

---

## CLI Commands

### batch-process

Process local PDFs without the API.

```bash
python -m app.cli batch-process [OPTIONS]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--directory` | `-d` | `Sample PDFS/` | Directory containing PDFs |
| `--pattern` | `-p` | `document_*.pdf` | Glob pattern for files |
| `--workers` | `-w` | `1` | Parallel PDF processing (1-50) |
| `--api-limit` | `-a` | `3` | Max concurrent API calls (1-10) |

### poll-batch-jobs

Poll pending Gemini Batch API jobs and process results.

```bash
python -m app.cli poll-batch-jobs [OPTIONS]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--once` | | | Poll once and exit |
| `--interval` | `-i` | `60` | Poll interval in seconds |
| `--job-type` | | _(all)_ | Filter: `validation` or `extraction` |

---

## Scripts Reference

All scripts are in `scripts/` and should be run from project root.

### Extraction & Batch

| Script | Description |
|--------|-------------|
| `run_extraction_batch_from_validated.py` | Submit Gemini Batch API extraction for validated-not-extracted files. Flags: `--dry-run`, `--min-files N`, `--force` |
| `batch_operations.py` | Database queries: `stats`, `list`, `export-csv`, `update-metadata`, `rename` |
| `export_extractions_md.py` | Export extraction results to Markdown files |
| `run_batch_matcher.py` | Run paper matching/reconstruction |

### Diagnostics & Fixes

| Script | Description |
|--------|-------------|
| `diagnose_storage_paths.py` | Compare DB `storage_path` vs Firebase Storage blobs. Flags: `--validated-only`, `--limit N` |
| `fix_storage_paths.py` | Fix mismatched `storage_path` values. Flags: `--dry-run`, `--run`, `--validated-only` |
| `check_batch_errors.py` | Debug Gemini batch job errors |
| `debug_batch_results.py` | Inspect batch result payloads |
| `debug_file_upload.py` | Debug file upload issues |
| `check_revalidate_progress.py` | Check validation progress |

### Data Management

| Script | Description |
|--------|-------------|
| `migrate_firestore_to_supabase.py` | Migrate Firestore data to Supabase. Flags: `--dry-run`, `--run`, `--verify` |
| `register_and_link_extractions.py` | Link existing extractions to scraped_files |
| `backfill_scraped_file_ids.py` | Backfill scraped_file_id on extractions |
| `upload_local_extractions.py` | Upload local extraction JSON to Supabase |
| `full_db_summary.py` | Print comprehensive database statistics |
| `query_extraction_stats.py` | Query extraction coverage stats |

### Testing

| Script | Description |
|--------|-------------|
| `test_batch_10.py` | Test batch processing with 10 files |

---

## Project Structure

```
PDF-Extraction/
  app/
    main.py              # FastAPI entry point
    cli.py               # CLI commands
    config.py            # Pydantic settings from .env
    routers/             # API endpoints
    services/            # Business logic (extraction, validation, batch)
    models/              # Pydantic schemas
    db/                  # Database CRUD layer
    middleware/          # Rate limiting, CORS
    utils/               # Shared utilities
  tests/                 # pytest test suite
  migrations/            # SQL migration files (001-019)
  scripts/               # Utility and operational scripts
  docs/                  # Documentation
  Sample PDFS/           # Test PDF files
```

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `scraped_files` | Source PDFs from Academy Scrapper (36K+ rows) |
| `validation_results` | Gemini validation outcomes per file |
| `extractions` | Extracted question paper data (JSON) |
| `memo_extractions` | Extracted marking guide data (JSON) |
| `batch_jobs` | Internal batch job tracking |
| `gemini_batch_jobs` | Gemini Batch API job tracking |
| `file_registry` | All validated files registry |

---

Last updated: 2026-02-05
