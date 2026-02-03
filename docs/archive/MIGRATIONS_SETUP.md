# Database Migrations Setup Guide

This guide explains the database migrations for the PDF Extraction Service and how to apply them to your Supabase PostgreSQL database.

---

## What Was Created

### 1. Migration Files (5 total)

| File | Purpose | Status |
|------|---------|--------|
| `001_create_extractions_table.sql` | Base extractions table | ⚠️ Needs update via 005 |
| `002_create_review_queue_table.sql` | Failed extraction review queue | ✅ Ready |
| `003_create_batch_jobs_table.sql` | Batch processing jobs | ✅ Ready |
| `004_create_memo_extractions_table.sql` | Marking guideline extractions | ✅ Ready |
| `005_update_extractions_for_exam_papers.sql` | **Update extractions for exam papers** | ✅ **Important!** |

### 2. Helper Scripts

- **`README.md`**: Comprehensive migration documentation with Supabase best practices
- **`apply_migrations.sh`**: Bash script to apply all migrations (Linux/macOS)
- **`apply_migrations.bat`**: Batch script to apply all migrations (Windows)
- **`verify_schema.py`**: Python script to verify database schema

---

## Why Migration 005?

Migration 001 was created for **academic papers** (research papers, journal articles) with fields like `abstract`, `references`, `sections`.

However, the **actual Python code** extracts **exam papers** (question papers) with different fields:
- `subject`, `syllabus`, `year`, `session`, `grade`, `language`
- `groups` (JSONB array of question groups)
- `total_marks`

**Migration 005** updates the `extractions` table to match the current Python models (`FullExamPaper`).

---

## Quick Setup (3 Options)

### Option 1: Supabase Dashboard (Easiest)

**Best for:** First-time setup, no CLI tools needed

1. Go to https://app.supabase.com
2. Select your project
3. Click **SQL Editor** in left sidebar
4. Copy/paste each migration file **in order**:
   - `001_create_extractions_table.sql` → Click "Run"
   - `002_create_review_queue_table.sql` → Click "Run"
   - `003_create_batch_jobs_table.sql` → Click "Run"
   - `004_create_memo_extractions_table.sql` → Click "Run"
   - `005_update_extractions_for_exam_papers.sql` → Click "Run" ⚠️ **Important!**

5. Verify with:
   ```sql
   SELECT table_name
   FROM information_schema.tables
   WHERE table_schema = 'public'
   ORDER BY table_name;
   ```

**Expected output:** `batch_jobs`, `extractions`, `memo_extractions`, `review_queue`

### Option 2: Automated Script (Recommended for developers)

**Best for:** Local development, automated setup

#### Windows:
```bash
# Set Supabase connection string
set DATABASE_URL=postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres

# Run migration script
cd migrations
apply_migrations.bat
```

#### Linux/macOS:
```bash
# Set Supabase connection string
export DATABASE_URL="postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres"

# Run migration script
cd migrations
chmod +x apply_migrations.sh
./apply_migrations.sh
```

### Option 3: Manual psql (Advanced)

**Best for:** CI/CD pipelines, production deployments

```bash
# Set connection string
export DATABASE_URL="postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres"

# Apply migrations in order
psql $DATABASE_URL -f migrations/001_create_extractions_table.sql
psql $DATABASE_URL -f migrations/002_create_review_queue_table.sql
psql $DATABASE_URL -f migrations/003_create_batch_jobs_table.sql
psql $DATABASE_URL -f migrations/004_create_memo_extractions_table.sql
psql $DATABASE_URL -f migrations/005_update_extractions_for_exam_papers.sql
```

---

## Verification

After applying migrations, verify the schema:

### Method 1: Python Verification Script

```bash
# Install dependencies
pip install -r requirements.txt

# Run verification
python migrations/verify_schema.py
```

**Expected output:**
```
[OK] Connected to Supabase
[OK] Table exists
[OK] All 22 required columns present (extractions)
[OK] All 18 required columns present (memo_extractions)
[OK] All 13 required columns present (batch_jobs)
[OK] All 11 required columns present (review_queue)
[SUCCESS] All schema checks passed!
```

### Method 2: Manual SQL Check

Run this in Supabase SQL Editor:

```sql
-- Check tables exist
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- Check extractions columns
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'extractions'
  AND table_schema = 'public'
ORDER BY ordinal_position;

-- Verify indexes
SELECT tablename, indexname
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
```

---

## Database Schema Overview

### Table: `extractions` (Exam Papers)

**Purpose:** Stores question paper extraction results

**Key Columns:**
```sql
id                      UUID PRIMARY KEY
file_hash               TEXT UNIQUE              -- SHA-256 for deduplication
status                  extraction_status        -- pending, completed, failed, partial
processing_method       processing_method_type   -- hybrid, vision_fallback

-- Exam Paper Metadata
subject                 TEXT                     -- "Business Studies P1"
syllabus                TEXT                     -- "SC" or "NSC"
year                    INTEGER                  -- 2025
session                 TEXT                     -- "MAY/JUNE" or "NOV"
grade                   TEXT                     -- "12"
language                TEXT                     -- "English", "Afrikaans"
total_marks             INTEGER                  -- 150

-- Data
groups                  JSONB                    -- QuestionGroup[] array
processing_metadata     JSONB                    -- Quality scores, cost, cache stats
```

### Table: `memo_extractions` (Marking Guidelines)

**Purpose:** Stores marking guideline (memo) extraction results

**Key Columns:**
```sql
id                      UUID PRIMARY KEY
file_hash               TEXT UNIQUE

-- Memo Metadata (similar to extractions)
subject, year, session, grade, total_marks

-- Data
sections                JSONB                    -- MemoSection[] array with answers
```

### Table: `batch_jobs`

**Purpose:** Tracks batch processing jobs for multiple PDFs

**Key Columns:**
```sql
id                      UUID PRIMARY KEY
status                  batch_status             -- pending, processing, completed
total_files             INTEGER                  -- Total files (max 100)
completed_files         INTEGER
failed_files            INTEGER
routing_stats           JSONB                    -- {"hybrid": N, "vision_fallback": M}
extraction_ids          UUID[]                   -- Array of extraction UUIDs
cost_estimate_usd       DECIMAL
cost_savings_usd        DECIMAL
```

### Table: `review_queue`

**Purpose:** Manual review queue for failed extractions

**Key Columns:**
```sql
id                      UUID PRIMARY KEY
extraction_id           UUID REFERENCES extractions(id) ON DELETE CASCADE
error_type              TEXT
error_message           TEXT
resolution              review_resolution        -- fixed, false_positive, unable_to_process
reviewer_notes          TEXT
queued_at               TIMESTAMPTZ
reviewed_at             TIMESTAMPTZ
```

---

## Supabase Best Practices Applied

✅ **ENUMs for status fields** (type safety)
✅ **UNIQUE indexes** on `file_hash` (deduplication)
✅ **Composite indexes** for common queries (performance)
✅ **JSONB columns** for flexible nested structures
✅ **Foreign keys with CASCADE** (referential integrity)
✅ **Triggers for `updated_at`** (automatic timestamps)
✅ **CHECK constraints** for validation (data integrity)
✅ **Comments on tables/columns** (documentation)
✅ **Lowercase identifiers** (PostgreSQL convention)

---

## Common Issues

### Issue 1: "relation already exists"
**Cause:** Table already created from previous run
**Solution:** Safe to ignore, or drop table and rerun migration

### Issue 2: Missing columns after migration 001
**Cause:** Migration 005 not run (updates extractions table)
**Solution:** Run migration 005: `005_update_extractions_for_exam_papers.sql`

### Issue 3: Foreign key violation
**Cause:** Migrations run out of order
**Solution:** Drop all tables and rerun in order (001 → 002 → 003 → 004 → 005)

### Issue 4: Permission denied
**Cause:** Using anon key instead of service role key
**Solution:** Use service role key from Supabase → Settings → API

---

## Next Steps After Migration

1. **Update `.env` file:**
   ```env
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-service-role-key-here
   ```

2. **Verify connection:**
   ```bash
   python migrations/verify_schema.py
   ```

3. **Run tests:**
   ```bash
   pytest tests/ -v
   ```

4. **Test with sample PDF:**
   ```bash
   python -m app.cli batch-process --directory "Sample PDFS" --workers 1
   ```

5. **Start API server:**
   ```bash
   uvicorn app.main:app --reload
   ```

---

## Rollback (If Needed)

To completely reset the database:

```sql
-- Drop in reverse order (respects foreign keys)
DROP TABLE IF EXISTS review_queue CASCADE;
DROP TABLE IF EXISTS batch_jobs CASCADE;
DROP TABLE IF EXISTS memo_extractions CASCADE;
DROP TABLE IF EXISTS extractions CASCADE;

-- Drop types
DROP TYPE IF EXISTS review_resolution CASCADE;
DROP TYPE IF EXISTS batch_status CASCADE;
DROP TYPE IF EXISTS processing_method_type CASCADE;
DROP TYPE IF EXISTS extraction_status CASCADE;

-- Drop function
DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;
```

Then rerun migrations from scratch.

---

## Additional Resources

- **Full migration docs:** `migrations/README.md`
- **Supabase docs:** https://supabase.com/docs/guides/database
- **PostgreSQL docs:** https://www.postgresql.org/docs/
- **Project README:** `README.md`

---

## Questions?

- Check `migrations/README.md` for detailed documentation
- Run `python migrations/verify_schema.py` to verify setup
- Open GitHub issue for problems
- Email: your.email@example.com

---

**Last Updated:** 2026-01-29
**Database Version:** 005 (Exam papers with memo support)
