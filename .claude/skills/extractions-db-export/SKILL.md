---
name: extractions-db-export
description: Query the Supabase database for the full extractions list in the same format as docs/extractions-export.md. Use when the user or agent needs the exact extraction rows (question papers) as a table or markdown file.
version: 1.0.0
source: project-docs
---

# Extractions DB Export Skill

When you need **the same information** as in `docs/extractions-export.md` (all extraction rows with key columns), use this skill to query the database directly or regenerate the file.

## When to Use

- User asks for "all extractions", "export extractions to .md", or "the same as extractions-export"
- You need the full list of `extractions` (question papers) with: id, file_name, subject, year, grade, session, language, total_marks, scraped_file_id, created_at
- You need to refresh or recreate `docs/extractions-export.md`

## Exact Query

Use this SQL to get the **exact** dataset that backs the export:

```sql
SELECT
  id,
  file_name,
  file_hash,
  status,
  subject,
  year,
  grade,
  session,
  language,
  total_marks,
  scraped_file_id,
  created_at
FROM public.extractions
ORDER BY created_at DESC;
```

- **Table:** `public.extractions` (Supabase)
- **Order:** `created_at DESC` (newest first)
- **Filter:** None (all rows). For only completed: add `WHERE status = 'completed'` if desired; the canonical export uses all rows.

## How to Run the Query

### Option 1: Supabase MCP (recommended for agents)

If Supabase MCP is available, call:

- **Tool:** `mcp_supabase_execute_sql`
- **Query:** The SQL above (as a single string)

Then format the returned rows into a markdown table (header row + one row per record). Optionally write to `docs/extractions-export.md` (see "Producing the .md file" below).

### Option 2: Python script (full export to files)

The project has a script that fetches from both `extractions` and `memo_extractions` and writes **one markdown file per record** into an output directory:

```bash
python scripts/export_extractions_md.py --all
```

- **Extractions (QP):** from `extractions` table, status `completed`
- **Memos:** from `memo_extractions` table, status `completed`
- Output: many `.md` files in the script’s `OUTPUT_DIR`, not a single table

For **one** table with all extraction rows (like `docs/extractions-export.md`), use Option 1 and build the markdown yourself.

### Option 3: Application / Supabase client

From app or scripts:

- Use `get_supabase_client()` from `app.db.supabase_client`
- Then: `client.table("extractions").select("id, file_name, file_hash, status, subject, year, grade, session, language, total_marks, scraped_file_id, created_at").order("created_at", desc=True).execute()`

Credentials: `SUPABASE_URL` and `SUPABASE_KEY` (or `SUPABASE_SERVICE_ROLE_KEY` for scripts). See `.cursor/rules/scripts.mdc` and project env docs.

## Producing the .md File

To recreate or update `docs/extractions-export.md`:

1. Run the exact SQL above (e.g. via `mcp_supabase_execute_sql`).
2. Build a markdown document with:
   - Title: e.g. `# Extractions Table – Full Export`
   - Short summary: total row count, source table, export date
   - A summary table: Total, Status (e.g. all `completed`), With scraped_file_id (count and %)
   - One markdown table with columns: `#`, `id`, `file_name`, `subject`, `year`, `grade`, `session`, `language`, `total_marks`, `scraped_file_id`, `created_at`
   - Number the rows (1, 2, 3, …) in the first column
   - Escape or avoid `|` inside cell values so the table parses correctly
3. Write the result to `docs/extractions-export.md`.

## Column Reference

| Column            | Type / notes                                      |
|-------------------|---------------------------------------------------|
| id                | UUID, primary key                                 |
| file_name         | text                                              |
| file_hash         | text (optional)                                   |
| status            | text (e.g. `completed`)                           |
| subject           | text                                              |
| year              | integer                                           |
| grade             | integer                                           |
| session           | text (e.g. MAY/JUNE, OCTOBER)                     |
| language          | text                                              |
| total_marks       | integer                                           |
| scraped_file_id   | UUID, FK to scraped_files                         |
| created_at        | timestamptz                                       |

Other columns exist on `extractions` (e.g. `file_size_bytes`, `processing_method`, `tables`, `updated_at`) but are not part of this export; omit them unless the user asks for more.

## Related

- **Single-file export:** `docs/extractions-export.md` – full table export (this skill matches that format).
- **Per-record exports:** `scripts/export_extractions_md.py --all` – one .md per extraction/memo.
- **DB overview:** `docs/database-summary.md` – table counts and status; `.cursor/rules/project-context.mdc` – key docs and scripts.
- **Schema/scripts:** `.cursor/rules/supabase-schema-check.mdc`, `.cursor/rules/scripts.mdc`.
