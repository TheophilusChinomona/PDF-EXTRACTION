---
name: db-tables-markdown-export
description: Query all Supabase tables (or a subset), get row counts and optional data, and format results as markdown. Use when the user wants a DB overview, table list, or export of multiple tables to markdown.
version: 1.0.0
source: project-docs
---

# DB Tables – Query All and Format as Markdown

When you need to **list all tables** and/or **export table data in markdown format**, use this skill with Supabase MCP and the formatting rules below.

## When to Use

- User asks for "all tables", "list tables", "database overview", or "export tables to markdown"
- You need a markdown report of table names, row counts, and optionally sample/full data
- You need to refresh or create a document like `docs/database-summary.md`

## Step 1: List All Tables

Use Supabase MCP to get the table list:

- **Tool:** `mcp_supabase_list_tables`
- **Parameters:** `schemas: ["public"]` (or include other schemas if needed)

Result: list of table names in the schema(s). Use this to build the markdown structure (one section per table, or a summary table of all tables).

## Step 2: Get Row Counts (and Optional Data)

For each table you want to include:

### Option A: Row count only

```sql
SELECT count(*) AS row_count FROM public.{table_name};
```

Use **Tool:** `mcp_supabase_execute_sql` with the query. Then in markdown: e.g. `| table_name | row_count |` in a summary table, or a line like `**table_name:** N rows`.

### Option B: Row count + sample rows

```sql
SELECT * FROM public.{table_name} ORDER BY 1 LIMIT {limit};
```

- Replace `{table_name}` with the actual table name.
- `ORDER BY 1` uses the first column (often id); use a known column like `created_at DESC` if preferred.
- `{limit}`: e.g. 10–100 for a sample; omit `LIMIT` only for small tables.

Use **Tool:** `mcp_supabase_execute_sql`. Format the returned rows as a markdown table (see Step 3).

### Option C: Full table export (small tables only)

Same as Option B but with a higher limit or no limit. Only do this for tables with a small number of rows (e.g. &lt; 500) to avoid huge output.

## Step 3: Format Results as Markdown

### Summary section (all tables)

Start the document with a title and a single table listing every table and its row count:

```markdown
# Database Summary – {Project Name}

**Queried:** {date} (Supabase public schema)

---

## 1. Public Schema – Table Counts

| Table | Count | Notes |
|-------|--------|--------|
| scraped_files | 36,017 | Source PDFs; validation_status |
| validation_results | 10,554 | Validation outcomes |
| extractions | 72 | Question papers; all completed |
| ... | ... | ... |
```

### Per-table sections (optional)

For each table where you export data (not just count), add a section:

```markdown
---

## 2. {table_name} ({row_count} rows)

{Optional bullet summary, e.g. status breakdown.}

| col_a | col_b | col_c |
|-------|-------|-------|
| ...   | ...   | ...   |
```

### Markdown table formatting rules

1. **Header row:** First row = pipe-separated column names (match DB column names or shortened).
2. **Separator row:** Second row = `|-------|-------|-------|` (one `---` per column).
3. **Data rows:** One row per record; pipe-separated values.
4. **Escaping:** If a cell value contains `|`, replace with something else (e.g. " / ") or wrap in backticks so the table still parses.
5. **Nulls:** Use `(null)` or `—` or leave empty for nulls.
6. **UUIDs/dates:** Keep as-is; they are readable enough.

Example row:

```markdown
| id | file_name | status | created_at |
|----|-----------|--------|------------|
| b9f8cdeb-... | OCR-A-Level-Further-Maths.pdf | completed | 2026-02-05 19:57:12 |
```

## Step 4: Write the File (optional)

- **Path:** `docs/database-summary.md` (or another path the user specifies).
- **Content:** Assemble the summary + per-table sections, then write with the Write tool.

## Quick Reference – Supabase MCP Tools

| Goal | Tool | Example |
|------|------|--------|
| List tables | `mcp_supabase_list_tables` | `schemas: ["public"]` |
| Run any SQL | `mcp_supabase_execute_sql` | `query: "SELECT count(*) FROM public.extractions"` |
| Row count for one table | `mcp_supabase_execute_sql` | `SELECT count(*) AS n FROM public.{table}` |
| Sample rows | `mcp_supabase_execute_sql` | `SELECT * FROM public.{table} ORDER BY 1 LIMIT 20` |

## Suggested Workflow for "All Tables in Markdown"

1. Call `mcp_supabase_list_tables` with `schemas: ["public"]`.
2. For each table in the list, call `mcp_supabase_execute_sql` with `SELECT count(*) AS row_count FROM public.{table}` (you can batch or loop).
3. Build the summary markdown: title, date, then one table with columns e.g. **Table | Count | Notes**.
4. Optionally, for important or small tables, run `SELECT * FROM public.{table} ORDER BY 1 LIMIT n` and add a "## table_name" section with a markdown table of the result.
5. Write the full document to `docs/database-summary.md` (or requested path).

## Related

- **Single-table export (extractions):** `.cursor/skills/extractions-db-export/SKILL.md` – same idea for `extractions` only, with exact columns and `docs/extractions-export.md`.
- **Existing summary:** `docs/database-summary.md` – example of the target format.
- **Schema / scripts:** `.cursor/rules/supabase-schema-check.mdc`, `.cursor/rules/scripts.mdc`.
