# Migrate Firestore Data to Supabase & Build Batch Tooling

**Date:** 2026-02-02
**Status:** IMPLEMENTATION COMPLETE - Pending execution

---

## Plan

- [x] 1. Extend scraped_files table schema (migration 007)
- [x] 2. Create comprehensive migration script
- [x] 3. Create batch operations CLI tool
- [x] 4. Add migration requirements
- [x] 5. Update .env with Firebase config

---

## Changes Made

### Step 1: SQL Migration (`migrations/007_extend_scraped_files_for_firebase.sql`)
Added 12 new columns to `scraped_files`: storage_path, storage_bucket, document_type, year, session, syllabus, language, user_id, user_email, job_id, downloaded_at, firestore_doc_id. Added indexes on document_type, year, storage_path, composite (subject, grade, year), firestore_doc_id (unique partial), and session.

### Step 2: Migration Script (`scripts/migrate_firestore_to_supabase.py`)
Comprehensive Firestore-to-Supabase migration with full field mapping. Features: extracts denormalized fields from metadata sub-object, parses Firebase Storage URLs to extract storage paths, converts Firestore Timestamps to ISO 8601, upserts on file_id for safe re-runs, deduplicates by file_id, supports --dry-run, --run, and --verify modes with detailed statistics.

### Step 3: Batch Operations CLI (`scripts/batch_operations.py`)
CLI tool with 5 subcommands: `stats` (summary statistics), `list` (filtered query with table output), `export-csv` (CSV export with filters), `update-metadata` (bulk update with confirmation), `rename` (file rename with optional Firebase Storage rename). All commands support common filters: --subject, --grade, --year, --document-type, --session, --status, --syllabus.

### Step 4: Requirements (`scripts/requirements-migration.txt`)
firebase-admin, supabase, python-dotenv, tqdm, google-cloud-storage.

### Step 5: .env Update
Added FIREBASE_CREDENTIALS_PATH pointing to Academy Scrapper serviceAccountKey.json. Added commented placeholder for SUPABASE_SERVICE_ROLE_KEY.

---

## Files Created/Modified
1. **CREATED** `migrations/007_extend_scraped_files_for_firebase.sql`
2. **CREATED** `scripts/migrate_firestore_to_supabase.py`
3. **CREATED** `scripts/batch_operations.py`
4. **CREATED** `scripts/requirements-migration.txt`
5. **MODIFIED** `.env` - Added Firebase credentials path and service role key placeholder

---

## Next Steps (Manual)
1. Apply migration 007 to Supabase (SQL editor or `psql`)
2. Set `SUPABASE_SERVICE_ROLE_KEY` in `.env` (get from Supabase Dashboard > Settings > API)
3. Install deps: `pip install -r scripts/requirements-migration.txt`
4. Run `python scripts/migrate_firestore_to_supabase.py --dry-run`
5. Run `python scripts/migrate_firestore_to_supabase.py --run`
6. Run `python scripts/migrate_firestore_to_supabase.py --verify`
7. Run `python scripts/batch_operations.py stats`
