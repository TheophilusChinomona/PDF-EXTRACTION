# Plan: Execute Firestore -> Supabase Migration

## Status
- [x] Migration SQL file created (`migrations/007_extend_scraped_files_for_firebase.sql`)
- [x] Migration script created (`scripts/migrate_firestore_to_supabase.py`)
- [x] Batch operations CLI created (`scripts/batch_operations.py`)
- [x] Dependencies installed
- [x] `.env` configured with service role key + Firebase credentials path

## Remaining Steps

### Step 1: Apply SQL Migration (YOU - via Cursor Supabase MCP)
Run the contents of `migrations/007_extend_scraped_files_for_firebase.sql` against Supabase.

This adds 12 columns to `scraped_files`:
- `storage_path`, `storage_bucket`, `document_type`, `year`, `session`, `syllabus`, `language`
- `user_id`, `user_email`, `job_id`, `downloaded_at`, `firestore_doc_id`

Plus 6 indexes.

**Tell me when done** -- I will verify the columns exist.

### Step 2: Verify Schema (ME)
I'll query Supabase via Python to confirm all new columns are present on `scraped_files`.

### Step 3: Dry-Run Migration (ME)
```
python scripts/migrate_firestore_to_supabase.py --dry-run
```
Preview Firestore data, show field mapping stats, sample transformations.

### Step 4: Execute Migration (ME)
```
python scripts/migrate_firestore_to_supabase.py --run
```
Upsert all Firestore `scraped_files` into Supabase with full field mapping.

### Step 5: Verify Migration (ME)
```
python scripts/migrate_firestore_to_supabase.py --verify
```
Compare counts, spot-check records, confirm new fields populated.

### Step 6: Run Stats (ME)
```
python scripts/batch_operations.py stats
```
Show summary of all papers by subject, grade, year, type, status.
