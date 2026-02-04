# Revalidation: Populate grade and metadata via Gemini

Instructions for running the revalidation script that updates `validation_results` (and optionally `scraped_files`) with grade, subject, year, and other metadata from Gemini for rows that currently have `grade IS NULL`.

## Where to run

**Directory:** ValidationAgent in the Academy Scrapper project  
**Path:** `C:\Users\theoc\Desktop\Work\Academy Scrapper\Scapper.Console\ValidationAgent`

All commands below are run from that directory.

## Requirements

In the ValidationAgent directory, ensure your environment has:

- **GEMINI_API_KEY** – Google Gemini API key
- **SUPABASE_URL** – Supabase project URL
- **SUPABASE_SERVICE_ROLE_KEY** – Supabase service role key (for DB updates)
- **GOOGLE_APPLICATION_CREDENTIALS** – Path to your Firebase/GCS service account JSON (so the script can download PDFs from `gs://`)

Use a `.env` file in that directory or set these variables in your shell.

## Commands

### Full run (recommended)

Updates all validation_results with null grade and, by default, patches linked `scraped_files` as well.

```bash
cd "C:\Users\theoc\Desktop\Work\Academy Scrapper\Scapper.Console\ValidationAgent"
python revalidate_missing_metadata.py
```

### Full run, only update validation_results

Do not patch `scraped_files`; only update `validation_results`.

```bash
cd "C:\Users\theoc\Desktop\Work\Academy Scrapper\Scapper.Console\ValidationAgent"
python revalidate_missing_metadata.py --no-scraped-files
```

### Test run (small batch first)

Run on a limited number of rows (e.g. 10) to confirm everything works before a full run.

```bash
cd "C:\Users\theoc\Desktop\Work\Academy Scrapper\Scapper.Console\ValidationAgent"
python revalidate_missing_metadata.py --limit 10
```

### Dry-run (no DB updates)

Process all rows and log what would be patched, but do not perform any UPDATEs. Use this to see how many rows would get grade populated (see script output for the dry-run summary).

```bash
cd "C:\Users\theoc\Desktop\Work\Academy Scrapper\Scapper.Console\ValidationAgent"
python revalidate_missing_metadata.py --dry-run
```

### Save output to a log file

Capture all output (and still see it in the terminal) with `tee`:

```bash
cd "C:\Users\theoc\Desktop\Work\Academy Scrapper\Scapper.Console\ValidationAgent"
python revalidate_missing_metadata.py 2>&1 | tee revalidate_run.log
```

For a dry-run log:

```bash
python revalidate_missing_metadata.py --dry-run 2>&1 | tee revalidate_dry_run.log
```

## What the script does

- Selects rows from `validation_results` where:
  - `status = 'correct'`
  - `scraped_file_id` is set
  - `grade IS NULL`
- For each row: builds the `gs://` URL from linked `scraped_files`, downloads the PDF, sends it to Gemini via the File API, and patches `validation_results` (and optionally `scraped_files`) with grade, subject, year, paper_number, etc.
- Failed rows are written to **revalidate_failed_ids.txt** in the ValidationAgent directory.

## Runtime

A full run over 5000+ rows can take several hours (download + Gemini per row, with concurrency). Use a long-lived terminal, or run under `tmux` / `screen`, or redirect output to a file as above.

## Check progress (query the database)

To see how many rows still need revalidation vs how many now have grade set, run this in **Supabase Dashboard → SQL Editor** (same project as ValidationAgent):

```sql
SELECT
  COUNT(*) FILTER (WHERE grade IS NULL)   AS still_to_do,
  COUNT(*) FILTER (WHERE grade IS NOT NULL) AS have_grade,
  COUNT(*)                                AS total_eligible
FROM validation_results
WHERE status = 'correct'
  AND scraped_file_id IS NOT NULL;
```

Or from the PDF-Extraction repo (only if its `.env` uses the same Supabase project as ValidationAgent):

```bash
cd "C:\Users\theoc\Desktop\Work\PDF-Extraction"
python scripts/check_revalidate_progress.py
```
