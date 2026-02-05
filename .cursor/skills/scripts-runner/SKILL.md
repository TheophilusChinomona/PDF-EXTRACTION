---
name: scripts-runner
description: Run the right script in scripts/ when required. Maps user/agent intent to the correct script and invocation (including --dry-run for writes). Use instead of manually guessing which script to run.
version: 1.0.0
source: project-scripts
---

# Scripts Runner – When to Run Each Script

Run scripts from **repository root** only: `python scripts/<name>.py [args]`. For any script that **writes** to DB/API/storage, run with `--dry-run` first unless the user explicitly asks for a live run.

## Quick Lookup: Intent → Script

| When required / User intent | Script | Invocation |
|-----------------------------|--------|------------|
| Link orphan extractions to **existing** scraped_files (filename/metadata match) | `backfill_scraped_file_ids.py` | `--dry-run` then run without args |
| Create scraped_files for **missing** PDFs and link orphan extractions (Firebase list + create) | `register_and_link_extractions.py` | `--dry-run` then run without args |
| Upload local JSON extractions to Supabase (with scraped_file_id lookup) | `upload_local_extractions.py` | Path(s) to JSON; use `--dry-run` first |
| Export extractions/memos to Markdown (one .md per record) | `export_extractions_md.py` | `--all` or specific IDs; `--limit`, `--since` optional |
| Full DB summary (all tables, counts, samples) | `full_db_summary.py` | No args |
| Validation + extraction stats | `query_extraction_stats.py` | No args |
| Revalidation progress (grade set on validation_results) | `check_revalidate_progress.py` | No args |
| Diagnose storage_path vs Firebase blob mismatches (404s) | `diagnose_storage_paths.py` | Optional `--limit`, `--validated-only` |
| Fix storage_path in scraped_files to match Firebase blobs | `fix_storage_paths.py` | `--dry-run` then `--run`; optional `--validated-only`, `--limit` |
| Query/export/update scraped_files (stats, list, export-csv, update-metadata, rename) | `batch_operations.py` | Subcommand: `stats`, `list`, `export-csv`, `update-metadata`, `rename` + args |
| Run Gemini Batch extraction for validated-but-not-extracted files | `run_extraction_batch_from_validated.py` | `--dry-run` then run; optional `--min-files`, `--force` |
| Run extraction via **local** FastAPI server (not Batch API) | `run_extraction_local_api.py` | `--dry-run` then run; optional `--limit`, `--batch-size`, `--api-url` |
| Trigger batch matcher (link docs to exam_sets) | `run_batch_matcher.py` | Optional positional `[limit]` (default 500) |
| Check Gemini batch job errors/details | `check_batch_errors.py` | No args |
| Debug batch job results (fetch raw from Gemini API) | `debug_batch_results.py` | No args |
| Debug Gemini file upload URI format | `debug_file_upload.py` | No args |
| Test: 10 PDFs → local /api/batch | `test_batch_10.py` | No args (server must be running) |
| Migrate Firestore → Supabase (scraped_files) | `migrate_firestore_to_supabase.py` | `--dry-run`, `--run`, or `--verify`; optional `--collection` |

## Per-Script Details

### Backfill / linking (DB writes – use --dry-run first)

- **backfill_scraped_file_ids.py** – Link extractions/memo_extractions to **existing** scraped_files by normalized filename and metadata.
  - `python scripts/backfill_scraped_file_ids.py --dry-run`
  - `python scripts/backfill_scraped_file_ids.py`

- **register_and_link_extractions.py** – For orphans with **no** matching scraped_file: list Firebase blobs, create scraped_files, set scraped_file_id.
  - `python scripts/register_and_link_extractions.py --dry-run`
  - `python scripts/register_and_link_extractions.py`

- **upload_local_extractions.py** – Upload local JSON extractions; looks up scraped_file_id. Pass paths to JSON files.
  - `python scripts/upload_local_extractions.py --dry-run <path(s)>`
  - `python scripts/upload_local_extractions.py <path(s)>`

### Export / reporting (read-only)

- **export_extractions_md.py** – Export extraction/memo records to Markdown files (one file per record).
  - `python scripts/export_extractions_md.py --all`
  - `python scripts/export_extractions_md.py --all --limit 50`
  - `python scripts/export_extractions_md.py --all --since 2026-02-01`

- **full_db_summary.py** – Full Supabase summary: all tables, counts, sample rows.
  - `python scripts/full_db_summary.py`

- **query_extraction_stats.py** – Validation and extraction statistics.
  - `python scripts/query_extraction_stats.py`

- **check_revalidate_progress.py** – Revalidation progress (grade set on validation_results).
  - `python scripts/check_revalidate_progress.py`

### Storage path diagnosis / fix (fix_storage_paths writes – use --dry-run first)

- **diagnose_storage_paths.py** – Compare scraped_files.storage_path with Firebase blob names; report mismatches.
  - `python scripts/diagnose_storage_paths.py`
  - `python scripts/diagnose_storage_paths.py --limit 50 --validated-only`

- **fix_storage_paths.py** – Update scraped_files.storage_path to match Firebase. Run diagnose first.
  - `python scripts/fix_storage_paths.py --dry-run`
  - `python scripts/fix_storage_paths.py --run`
  - `python scripts/fix_storage_paths.py --dry-run --validated-only --limit 50`

### Batch operations (scraped_files)

- **batch_operations.py** – CLI for scraped_files: stats, list (with filters), export-csv, update-metadata, rename.
  - `python scripts/batch_operations.py stats`
  - `python scripts/batch_operations.py list --subject "Mathematics" --grade 12`
  - `python scripts/batch_operations.py export-csv --output papers.csv`
  - `python scripts/batch_operations.py update-metadata --filter-subject "Maths" --set-subject "Mathematics"`
  - `python scripts/batch_operations.py rename --file-id <id> --new-filename "Paper1.pdf"`

### Extraction jobs (run extraction pipeline)

- **run_extraction_batch_from_validated.py** – Submit Gemini Batch API extraction for validated files not yet extracted (up to 100). After run, poll: `python -m app.cli poll-batch-jobs --once`.
  - `python scripts/run_extraction_batch_from_validated.py --dry-run`
  - `python scripts/run_extraction_batch_from_validated.py`
  - `python scripts/run_extraction_batch_from_validated.py --min-files 10 --force`
  - Requires: SUPABASE_SERVICE_ROLE_KEY.

- **run_extraction_local_api.py** – Same idea but via local FastAPI POST /api/batch (no Batch API). Server must be running.
  - `python scripts/run_extraction_local_api.py --dry-run`
  - `python scripts/run_extraction_local_api.py --dry-run --limit 10`
  - `python scripts/run_extraction_local_api.py --limit 50 --batch-size 25 --api-url http://localhost:8000`
  - Requires: SUPABASE_SERVICE_ROLE_KEY; server on API_URL.

- **run_batch_matcher.py** – Scan unlinked documents and link to exam_sets.
  - `python scripts/run_batch_matcher.py`
  - `python scripts/run_batch_matcher.py 200`  # limit

### Debug / test

- **check_batch_errors.py** – Print Gemini batch job rows (status, errors, counts).
  - `python scripts/check_batch_errors.py`

- **debug_batch_results.py** – Fetch batch job state/results from Gemini API.
  - `python scripts/debug_batch_results.py`

- **debug_file_upload.py** – Upload a tiny test PDF to Gemini and print URI/attributes.
  - `python scripts/debug_file_upload.py`

- **test_batch_10.py** – Download 10 PDFs from Firebase, POST to local /api/batch, report. Server must be running.
  - `python scripts/test_batch_10.py`

### Migration (Firestore → Supabase)

- **migrate_firestore_to_supabase.py** – Migrate scraped_files from Firestore to Supabase. Requires migration 007 applied.
  - `python scripts/migrate_firestore_to_supabase.py --dry-run`
  - `python scripts/migrate_firestore_to_supabase.py --run`
  - `python scripts/migrate_firestore_to_supabase.py --verify`
  - `python scripts/migrate_firestore_to_supabase.py --run --collection scraped_files`

## Rules (from .cursor/rules/scripts.mdc)

1. **Run from repo root** – `python scripts/<name>.py` (do not run from inside `scripts/` without ensuring project root).
2. **Dry-run before writes** – For scripts that write to DB/API/storage, run with `--dry-run` first unless the user explicitly requests a live run.
3. **Env** – Supabase writes often need `SUPABASE_SERVICE_ROLE_KEY`; Firebase scripts need `FIREBASE_CREDENTIALS_PATH` (or equivalent). Fail fast with a clear message if missing.

## Related

- **Scripts rule:** `.cursor/rules/scripts.mdc` – Run from root, dry-run, docstrings, env, async/duplicate handling.
- **Project context:** `.cursor/rules/project-context.mdc` – File structure, key docs.
- **Extractions export (single table):** `.cursor/skills/extractions-db-export/SKILL.md` – Query extractions and write one .md table.
- **DB tables markdown:** `.cursor/skills/db-tables-markdown-export/SKILL.md` – List all tables and format as markdown.
