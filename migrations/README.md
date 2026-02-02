# Database Migrations

This directory contains SQL migration files for setting up the PDF Extraction Service database schema in Supabase (PostgreSQL).

---

## Migration Files

| File | Description | Status |
|------|-------------|--------|
| `001_create_extractions_table.sql` | Create base extractions table | ⚠️ Deprecated (for academic papers) |
| `002_create_review_queue_table.sql` | Create review queue for failed extractions | ✅ Active |
| `003_create_batch_jobs_table.sql` | Create batch processing jobs table | ✅ Active |
| `004_create_memo_extractions_table.sql` | Create marking guideline (memo) table | ✅ Active |
| `005_update_extractions_for_exam_papers.sql` | Update extractions for exam papers | ✅ **Run this!** |
| `006_add_constraints_and_indexes.sql` | Partial unique indexes, CHECK constraint (Gap Bridge) | ✅ Run after 005 |

---

## Quick Start

### Option 1: Supabase Dashboard (Recommended)

1. Go to your Supabase project: https://app.supabase.com
2. Navigate to **SQL Editor** in the left sidebar
3. Execute migrations **in order**:

```sql
-- Run each migration file in sequence:
-- 1. Copy contents of 001_create_extractions_table.sql → Execute
-- 2. Copy contents of 002_create_review_queue_table.sql → Execute
-- 3. Copy contents of 003_create_batch_jobs_table.sql → Execute
-- 4. Copy contents of 004_create_memo_extractions_table.sql → Execute
-- 5. Copy contents of 005_update_extractions_for_exam_papers.sql → Execute
-- 6. Copy contents of 006_add_constraints_and_indexes.sql → Execute
```

**Important:** Run migration 005 even if you've already run 001. This updates the schema to match the current Python models. Run 006 after 005 for duplicate-prevention indexes and CHECK constraints.

### Option 2: Supabase CLI

If you have the Supabase CLI installed:

```bash
# Initialize Supabase (if not already done)
supabase init

# Link to your project
supabase link --project-ref your-project-ref

# Apply migrations
supabase db push

# Or apply individual migrations
psql $DATABASE_URL < migrations/001_create_extractions_table.sql
psql $DATABASE_URL < migrations/002_create_review_queue_table.sql
psql $DATABASE_URL < migrations/003_create_batch_jobs_table.sql
psql $DATABASE_URL < migrations/004_create_memo_extractions_table.sql
psql $DATABASE_URL < migrations/005_update_extractions_for_exam_papers.sql
```

### Option 3: Direct PostgreSQL Connection

```bash
# Set your Supabase connection string
export DATABASE_URL="postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres"

# Apply migrations in order
psql $DATABASE_URL -f migrations/001_create_extractions_table.sql
psql $DATABASE_URL -f migrations/002_create_review_queue_table.sql
psql $DATABASE_URL -f migrations/003_create_batch_jobs_table.sql
psql $DATABASE_URL -f migrations/004_create_memo_extractions_table.sql
psql $DATABASE_URL -f migrations/005_update_extractions_for_exam_papers.sql
```

---

## Schema Overview

### Tables

#### 1. `extractions` (Exam Paper Extractions)
Stores question paper extraction results with structured question data.

**Key Fields:**
- `id` (UUID, PK): Unique extraction ID
- `file_hash` (TEXT, UNIQUE): SHA-256 hash for deduplication
- `status` (ENUM): `pending`, `completed`, `failed`, `partial`
- `processing_method` (ENUM): `hybrid`, `vision_fallback`, `opendataloader_only`
- **Exam Paper Metadata:**
  - `subject` (TEXT): e.g., "Business Studies P1"
  - `syllabus` (TEXT): "SC" or "NSC"
  - `year` (INTEGER): Exam year
  - `session` (TEXT): "MAY/JUNE" or "NOV"
  - `grade` (TEXT): "12", "11", "10"
  - `language` (TEXT): "English", "Afrikaans", etc.
  - `total_marks` (INTEGER): Total marks for the paper
- `groups` (JSONB): Array of QuestionGroup objects with questions
- `processing_metadata` (JSONB): Method, quality scores, cost estimates

**Indexes:**
- `idx_extractions_file_hash` (UNIQUE): Deduplication
- `idx_extractions_status`: Filter by status
- `idx_extractions_subject_grade_year`: Common query pattern

#### 2. `memo_extractions` (Marking Guidelines)
Stores marking guideline (memo) extraction results with correct answers.

**Key Fields:**
- Similar structure to `extractions`
- `sections` (JSONB): Array of MemoSection objects with answers
- Metadata: `subject`, `year`, `session`, `grade`, `total_marks`

**Indexes:**
- `idx_memo_extractions_file_hash` (UNIQUE): Deduplication
- `idx_memo_extractions_status`: Filter by status

#### 3. `batch_jobs`
Tracks batch processing jobs for multiple PDF files.

**Key Fields:**
- `id` (UUID, PK): Batch job ID
- `status` (ENUM): `pending`, `processing`, `completed`, `failed`, `partial`
- `total_files` (INTEGER): Total files in batch (max 100)
- `completed_files`, `failed_files` (INTEGER): Progress counters
- `routing_stats` (JSONB): `{"hybrid": N, "vision_fallback": M, "pending": K}`
- `extraction_ids` (UUID[]): Array of extraction UUIDs
- `cost_estimate_usd`, `cost_savings_usd` (DECIMAL): Cost tracking

**Indexes:**
- `idx_batch_jobs_status_created_at`: Dashboard queries

#### 4. `review_queue`
Manual review queue for failed extractions that exceeded retry limits.

**Key Fields:**
- `id` (UUID, PK): Review record ID
- `extraction_id` (UUID, FK): References `extractions(id)`
- `error_type` (TEXT): Error classification
- `resolution` (ENUM): `fixed`, `false_positive`, `unable_to_process`
- `reviewer_notes` (TEXT): Human reviewer notes
- `queued_at`, `reviewed_at` (TIMESTAMPTZ): Timestamps

**Indexes:**
- `idx_review_queue_pending`: Unresolved items (WHERE `resolution IS NULL`)
- `idx_review_queue_extraction_id`: FK lookup

---

## Supabase Best Practices

### 1. **Use Enums for Status Fields**
✅ Migrations use PostgreSQL ENUMs (`extraction_status`, `processing_method_type`, etc.)
- Type safety at database level
- Clear documentation of valid values
- Better query performance

### 2. **Index Strategy**
✅ All migrations include comprehensive indexes:
- **UNIQUE indexes** on `file_hash` columns for deduplication
- **Single-column indexes** on frequently queried fields (`status`, `created_at`)
- **Composite indexes** for common query patterns (`status + created_at`)
- **Partial indexes** on review_queue for pending items (`WHERE resolution IS NULL`)
- **Foreign key indexes** on all FK columns

### 3. **JSONB for Flexible Schemas**
✅ Used for nested structures:
- `extractions.groups` → Array of QuestionGroup objects
- `memo_extractions.sections` → Array of MemoSection objects
- `batch_jobs.routing_stats` → Dynamic routing statistics
- `processing_metadata` → Flexible metadata storage

**Benefits:**
- No schema migrations for nested structure changes
- Efficient storage and indexing
- Native JSON operators in PostgreSQL

### 4. **Timestamps with Automatic Updates**
✅ All tables have:
- `created_at` (TIMESTAMPTZ) → Default `NOW()`
- `updated_at` (TIMESTAMPTZ) → Auto-updated via trigger

**Pattern:**
```sql
CREATE TRIGGER update_[table]_updated_at
    BEFORE UPDATE ON [table]
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

### 5. **Constraints and Validation**
✅ Migrations include CHECK constraints:
- `file_size_bytes >= 0`
- `quality_score BETWEEN 0.0 AND 1.0`
- `retry_count >= 0`
- `completed_files + failed_files <= total_files` (batch_jobs)
- `total_files BETWEEN 1 AND 100` (batch_jobs)

### 6. **Foreign Keys with CASCADE**
✅ Review queue uses `ON DELETE CASCADE`:
```sql
extraction_id UUID REFERENCES extractions(id) ON DELETE CASCADE
```
- If extraction deleted → review record also deleted
- Maintains referential integrity

### 7. **Lowercase Identifiers**
✅ All table and column names use `snake_case`:
- `extractions`, `memo_extractions`, `batch_jobs`, `review_queue`
- `file_name`, `processing_method`, `created_at`

**Why:** PostgreSQL folds identifiers to lowercase unless quoted. Avoids quoting issues.

### 8. **Comments for Documentation**
✅ All tables and columns have `COMMENT ON`:
```sql
COMMENT ON TABLE extractions IS 'Stores exam paper extraction results...';
COMMENT ON COLUMN extractions.subject IS 'Subject name, e.g., "Business Studies P1"';
```
- Serves as inline documentation
- Visible in Supabase dashboard
- Helps future developers understand schema

### 9. **Default Values**
✅ Migrations provide sensible defaults:
- `status` → `'pending'`
- `retry_count` → `0`
- `language` → `'English'`
- `total_marks` → `150`
- `groups`, `sections` → `'[]'::jsonb`
- `processing_metadata` → `'{}'::jsonb`

### 10. **Row Level Security (RLS)**
⚠️ **Not yet implemented** - migrations focus on schema only.

**Recommended RLS policies for production:**
```sql
-- Enable RLS on all tables
ALTER TABLE extractions ENABLE ROW LEVEL SECURITY;
ALTER TABLE memo_extractions ENABLE ROW LEVEL SECURITY;
ALTER TABLE batch_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_queue ENABLE ROW LEVEL SECURITY;

-- Example policy: Service role has full access
CREATE POLICY "Service role full access" ON extractions
    FOR ALL
    USING (auth.role() = 'service_role');

-- Example policy: Authenticated users can read their own extractions
CREATE POLICY "Users read own extractions" ON extractions
    FOR SELECT
    USING (auth.uid() = user_id); -- Requires adding user_id column
```

**When to enable RLS:**
- If exposing Supabase directly to frontend (bypass your backend)
- If implementing multi-tenancy
- For production security hardening

**Current setup:**
- Service uses **service role key** (bypasses RLS)
- Backend controls access via API authentication
- RLS optional for this architecture

---

## Verification

After running migrations, verify the schema:

### 1. Check Tables Exist
```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;
```

**Expected output:**
- `extractions`
- `memo_extractions`
- `batch_jobs`
- `review_queue`

### 2. Check Indexes
```sql
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
```

**Look for:**
- `idx_extractions_file_hash` (UNIQUE)
- `idx_extractions_status`
- `idx_extractions_subject_grade_year`
- `idx_memo_extractions_file_hash` (UNIQUE)
- `idx_batch_jobs_status_created_at`
- `idx_review_queue_pending` (partial index)

### 3. Check Foreign Keys
```sql
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'public';
```

**Expected:**
- `review_queue.extraction_id` → `extractions.id`

### 4. Test Insert
```sql
-- Test inserting an extraction record
INSERT INTO extractions (
    file_name, file_size_bytes, file_hash, status,
    subject, year, grade, session, groups
) VALUES (
    'test-paper.pdf', 1024, 'test-hash-12345', 'pending',
    'Business Studies P1', 2025, '12', 'MAY/JUNE', '[]'::jsonb
) RETURNING id;

-- Clean up test data
DELETE FROM extractions WHERE file_hash = 'test-hash-12345';
```

---

## Rollback

If you need to rollback migrations:

```sql
-- Drop tables in reverse order (respects foreign keys)
DROP TABLE IF EXISTS review_queue CASCADE;
DROP TABLE IF EXISTS batch_jobs CASCADE;
DROP TABLE IF EXISTS memo_extractions CASCADE;
DROP TABLE IF EXISTS extractions CASCADE;

-- Drop enum types
DROP TYPE IF EXISTS review_resolution CASCADE;
DROP TYPE IF EXISTS batch_status CASCADE;
DROP TYPE IF EXISTS processing_method_type CASCADE;
DROP TYPE IF EXISTS extraction_status CASCADE;

-- Drop trigger function
DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;
```

---

## Troubleshooting

### Issue: "relation already exists"
**Solution:** Table already created. Safe to ignore, or drop and recreate.

### Issue: "type already exists"
**Solution:** ENUM type already created. Safe to ignore, or use `IF NOT EXISTS`.

### Issue: "permission denied"
**Solution:** Use service role key or database owner credentials.

### Issue: Foreign key violation
**Solution:** Ensure migrations run in order (001 → 002 → 003 → 004 → 005).

---

## Next Steps

After running migrations:

1. **Update `.env` file** with Supabase credentials:
   ```env
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-service-role-key-here
   ```

2. **Test database connection:**
   ```bash
   python -c "from app.db.supabase_client import get_supabase_client; print(get_supabase_client())"
   ```

3. **Run application tests:**
   ```bash
   pytest tests/test_extractions.py -v
   ```

4. **Verify with sample PDF:**
   ```bash
   python -m app.cli batch-process --workers 1
   ```

---

## Migration History

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-01-28 | 001-004 | Initial schema (academic papers) | Initial setup |
| 2026-01-29 | 005 | Update for exam papers (FullExamPaper model) | Schema alignment |

---

## Contributing

When adding new migrations:

1. **Naming:** `NNN_descriptive_name.sql` (sequential numbering)
2. **Header:** Include migration number, description, date, purpose
3. **Idempotency:** Use `IF NOT EXISTS` / `IF EXISTS` where possible
4. **Comments:** Add `COMMENT ON` for documentation
5. **Indexes:** Always index foreign keys and frequently queried columns
6. **Testing:** Verify migration on local Supabase instance first
7. **Update README:** Add to migration table and schema overview

---

**Questions or Issues?**
- Check Supabase docs: https://supabase.com/docs/guides/database
- Open issue: GitHub Issues
- Email: your.email@example.com
