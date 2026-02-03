# PDF Extraction Operations Guide

Practical commands and workflows for extracting PDFs, managing batches, exporting data, and querying the database.

---

## Table of Contents

1. [Quick Reference](#quick-reference)
2. [Extract Single PDF](#extract-single-pdf)
3. [Batch Processing](#batch-processing)
4. [Export to Markdown](#export-to-markdown)
5. [Query the Database](#query-the-database)
6. [Database Management](#database-management)
7. [Common Workflows](#common-workflows)

---

## Quick Reference

```bash
# Start the server
"C:\Python314\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Extract single PDF via API
curl -X POST http://localhost:8000/api/extract -F "file=@path/to/file.pdf"

# Batch process directory
"C:\Python314\python.exe" -m app.cli batch-process -d "Sample PDFS" -w 5

# Export extractions to Markdown
"C:\Python314\python.exe" scripts/export_extractions_md.py

# View database stats
"C:\Python314\python.exe" scripts/batch_operations.py stats

# List papers by subject
"C:\Python314\python.exe" scripts/batch_operations.py list --subject "Mathematics" --grade 12
```

---

## Extract Single PDF

### Via API (Server must be running)

```bash
# Basic extraction
curl -X POST http://localhost:8000/api/extract \
  -F "file=@path/to/exam_paper.pdf"

# With webhook notification
curl -X POST http://localhost:8000/api/extract \
  -F "file=@path/to/exam_paper.pdf" \
  -F "webhook_url=https://your-server.com/webhook"

# Response includes extraction ID
# {
#   "id": "550e8400-e29b-41d4-a716-446655440000",
#   "subject": "Business Studies",
#   "grade": 12,
#   ...
# }
```

### Via Python Script

```python
import httpx

async def extract_pdf(file_path: str) -> dict:
    async with httpx.AsyncClient() as client:
        with open(file_path, "rb") as f:
            files = {"file": (file_path, f, "application/pdf")}
            response = await client.post(
                "http://localhost:8000/api/extract",
                files=files,
                timeout=300.0
            )
        return response.json()

# Usage
result = await extract_pdf("Sample PDFS/document_62.pdf")
print(f"Extraction ID: {result['id']}")
print(f"Subject: {result['subject']}")
```

### Retrieve Extraction Result

```bash
# Get by ID
curl http://localhost:8000/api/extractions/550e8400-e29b-41d4-a716-446655440000

# Get bounding boxes (for PDF highlighting)
curl http://localhost:8000/api/extractions/550e8400-e29b-41d4-a716-446655440000/bounding-boxes

# List all extractions
curl "http://localhost:8000/api/extractions?limit=20&status_filter=completed"
```

---

## Batch Processing

### CLI Batch Processing (Recommended)

Process multiple PDFs in a directory without using the API.

```bash
# Basic - process all PDFs in Sample PDFS/
"C:\Python314\python.exe" -m app.cli batch-process

# Specify directory
"C:\Python314\python.exe" -m app.cli batch-process -d "C:\path\to\pdfs"

# Custom file pattern
"C:\Python314\python.exe" -m app.cli batch-process -p "*.pdf"
"C:\Python314\python.exe" -m app.cli batch-process -p "exam_*.pdf"

# Parallel processing (5 PDFs at once, max 3 API calls)
"C:\Python314\python.exe" -m app.cli batch-process -w 5 -a 3

# Full example
"C:\Python314\python.exe" -m app.cli batch-process \
  -d "Sample PDFS" \
  -p "document_*.pdf" \
  -w 5 \
  -a 3
```

**CLI Options:**

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--directory` | `-d` | Directory containing PDFs | `Sample PDFS/` |
| `--pattern` | `-p` | Glob pattern for files | `document_*.pdf` |
| `--workers` | `-w` | Parallel PDF processing | 1 |
| `--api-limit` | `-a` | Max concurrent API calls | 3 |

**Output:**
- Renames PDFs to canonical format: `{subject}-p{paper}-gr{grade}-{session}-{year}-{qp|mg}.pdf`
- Saves JSON results alongside each PDF
- Generates `_batch_summary.json` in the directory

### API Batch Processing

```bash
# Upload multiple files
curl -X POST http://localhost:8000/api/batch \
  -F "files=@paper1.pdf" \
  -F "files=@paper2.pdf" \
  -F "files=@paper3.pdf" \
  -F "webhook_url=https://your-server.com/webhook"

# Response
# {
#   "batch_job_id": "770e8400-e29b-41d4-a716-446655440000",
#   "status": "processing",
#   "total_files": 3
# }

# Check batch status
curl http://localhost:8000/api/batch/770e8400-e29b-41d4-a716-446655440000
```

---

## Export to Markdown

Convert extraction results from the database to human-readable Markdown files.

### Using the Export Script

```bash
# Export extractions to output_markdown/
"C:\Python314\python.exe" scripts/export_extractions_md.py
```

**What it does:**
1. Fetches extraction records from Supabase (both `extractions` and `memo_extractions` tables)
2. Converts to formatted Markdown with:
   - Metadata header (subject, grade, year, session)
   - Question groups/sections
   - Options, match tables, scenarios
   - Marking guidelines (for memos)
3. Saves to `output_markdown/` with canonical filenames

**Output filename format:**
```
{short_id}-{subject}-gr{grade}-{session}-{year}-{qp|mg}.md

Examples:
072b402f5929-business-studies-gr12-may-june-2023-qp.md
b6f4fbb1e35d-mathematics-gr11-nov-2024-mg.md
```

### Customize Export IDs

Edit `scripts/export_extractions_md.py` and modify the `EXTRACTION_IDS` list:

```python
EXTRACTION_IDS = [
    "your-extraction-id-1",
    "your-extraction-id-2",
    # Add more IDs...
]
```

### Manual Markdown Conversion (Python)

```python
from supabase import create_client
import os

# Connect to Supabase
supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"]
)

# Fetch extraction
result = supabase.table("extractions").select("*").eq("id", "your-id").execute()
data = result.data[0]

# Convert to Markdown
def to_markdown(data):
    lines = [f"# {data['subject']}", ""]
    lines.append(f"**Grade:** {data['grade']} | **Year:** {data['year']} | **Session:** {data['session']}")
    lines.append("")

    for group in data.get("groups", []):
        lines.append(f"## {group['group_id']}: {group.get('title', '')}")
        for q in group.get("questions", []):
            marks = f" [{q.get('marks')} marks]" if q.get('marks') else ""
            lines.append(f"### Question {q['id']}{marks}")
            lines.append(q.get("text", ""))
            lines.append("")

    return "\n".join(lines)

print(to_markdown(data))
```

---

## Query the Database

### Using the Batch Operations Script

```bash
# View statistics
"C:\Python314\python.exe" scripts/batch_operations.py stats

# List papers with filters
"C:\Python314\python.exe" scripts/batch_operations.py list --subject "Mathematics"
"C:\Python314\python.exe" scripts/batch_operations.py list --grade 12 --year 2023
"C:\Python314\python.exe" scripts/batch_operations.py list --document-type QP --limit 100

# Export to CSV
"C:\Python314\python.exe" scripts/batch_operations.py export-csv --output papers.csv
"C:\Python314\python.exe" scripts/batch_operations.py export-csv --subject "Business" -o business_papers.csv
```

**Filter options:**

| Filter | Example | Description |
|--------|---------|-------------|
| `--subject` | `"Mathematics"` | Partial match on subject |
| `--grade` | `12` | Exact grade match |
| `--year` | `2023` | Exact year match |
| `--document-type` | `QP` or `MG` | Question Paper or Memo |
| `--session` | `"MAY/JUNE"` | Partial match on session |
| `--status` | `completed` | Extraction status |
| `--syllabus` | `NSC` | Partial match on syllabus |

### Direct Supabase Queries (Python)

```python
from supabase import create_client
import os

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"]
)

# Query extractions table
result = supabase.table("extractions")\
    .select("id, subject, grade, year, status")\
    .eq("status", "completed")\
    .eq("grade", 12)\
    .order("created_at", desc=True)\
    .limit(50)\
    .execute()

for row in result.data:
    print(f"{row['subject']} Gr{row['grade']} {row['year']}")

# Query memo_extractions table
memos = supabase.table("memo_extractions")\
    .select("*")\
    .eq("subject", "Business Studies")\
    .execute()

# Query scraped_files table (source files)
files = supabase.table("scraped_files")\
    .select("filename, subject, grade, year, storage_path")\
    .ilike("subject", "%Mathematics%")\
    .eq("grade", 12)\
    .execute()

# Count records
count = supabase.table("extractions")\
    .select("id", count="exact")\
    .eq("status", "completed")\
    .execute()
print(f"Total completed: {count.count}")
```

### Common Queries

```python
# Get all failed extractions
failed = supabase.table("extractions")\
    .select("id, file_name, error_message")\
    .eq("status", "failed")\
    .execute()

# Find duplicates by file hash
dupes = supabase.table("extractions")\
    .select("file_hash, count")\
    .execute()

# Get extraction with questions
extraction = supabase.table("extractions")\
    .select("id, subject, groups")\
    .eq("id", "your-extraction-id")\
    .single()\
    .execute()

# Count questions in an extraction
total_questions = sum(
    len(g.get("questions", []))
    for g in extraction.data.get("groups", [])
)

# Search by subject across both tables
qp = supabase.table("extractions").select("id, subject").ilike("subject", "%Business%").execute()
mg = supabase.table("memo_extractions").select("id, subject").ilike("subject", "%Business%").execute()
```

---

## Database Management

### Update Metadata in Bulk

```bash
# Update subject name
"C:\Python314\python.exe" scripts/batch_operations.py update-metadata \
  --subject "Maths" \
  --set-subject "Mathematics" \
  -y

# Update grade for specific year
"C:\Python314\python.exe" scripts/batch_operations.py update-metadata \
  --year 2023 \
  --subject "Business" \
  --set-status "reviewed"

# Fix syllabus
"C:\Python314\python.exe" scripts/batch_operations.py update-metadata \
  --syllabus "nsc" \
  --set-syllabus "NSC" \
  -y
```

### Rename Files

```bash
# Rename in database only
"C:\Python314\python.exe" scripts/batch_operations.py rename \
  --file-id "abc123" \
  --new-filename "mathematics-p1-gr12-may-june-2023-qp.pdf"

# Rename in database AND Firebase Storage
"C:\Python314\python.exe" scripts/batch_operations.py rename \
  --file-id "abc123" \
  --new-filename "mathematics-p1-gr12-may-june-2023-qp.pdf" \
  --rename-storage
```

### Direct Database Updates (Python)

```python
# Update extraction status
supabase.table("extractions")\
    .update({"status": "reviewed"})\
    .eq("id", "extraction-id")\
    .execute()

# Bulk update by filter
supabase.table("scraped_files")\
    .update({"syllabus": "NSC"})\
    .ilike("syllabus", "%nsc%")\
    .execute()

# Delete failed extractions
supabase.table("extractions")\
    .delete()\
    .eq("status", "failed")\
    .lt("created_at", "2024-01-01")\
    .execute()
```

---

## Common Workflows

### Workflow 1: Process New Exam Papers

```bash
# 1. Start the server
"C:\Python314\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. Copy PDFs to Sample PDFS/

# 3. Run batch processing
"C:\Python314\python.exe" -m app.cli batch-process -d "Sample PDFS" -w 5

# 4. Check results
"C:\Python314\python.exe" scripts/batch_operations.py stats
```

### Workflow 2: Export Papers for Review

```bash
# 1. List completed extractions
"C:\Python314\python.exe" scripts/batch_operations.py list \
  --status completed \
  --subject "Business Studies" \
  --grade 12

# 2. Export to Markdown
"C:\Python314\python.exe" scripts/export_extractions_md.py

# 3. Review files in output_markdown/
```

### Workflow 3: Fix Failed Extractions

```bash
# 1. List failed extractions
curl "http://localhost:8000/api/review-queue?limit=50"

# 2. Retry specific extraction
curl -X POST http://localhost:8000/api/extractions/{id}/retry

# 3. Or re-upload the PDF
curl -X POST http://localhost:8000/api/extract -F "file=@fixed_paper.pdf"
```

### Workflow 4: Bulk Export to CSV

```bash
# Export all Grade 12 papers
"C:\Python314\python.exe" scripts/batch_operations.py export-csv \
  --grade 12 \
  -o grade12_papers.csv

# Export by year range (run multiple times)
"C:\Python314\python.exe" scripts/batch_operations.py export-csv --year 2023 -o 2023.csv
"C:\Python314\python.exe" scripts/batch_operations.py export-csv --year 2024 -o 2024.csv
```

---

## Database Tables Reference

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `extractions` | Question paper results | id, subject, grade, year, groups (JSON), status |
| `memo_extractions` | Marking guideline results | id, subject, grade, year, sections (JSON) |
| `scraped_files` | Source PDF metadata | file_id, filename, storage_path, subject, grade |
| `batch_jobs` | Batch processing jobs | id, status, total_files, completed_files |
| `review_queue` | Failed extractions | id, extraction_id, error_type, error_message |

---

## Troubleshooting

### Server won't start
```bash
# Check if port is in use
netstat -ano | findstr :8000

# Kill existing process
taskkill /PID <PID> /F
```

### API returns 429 (rate limited)
```bash
# Wait and retry, or check rate limit headers
curl -I http://localhost:8000/api/extractions
# Look for: X-RateLimit-Remaining
```

### Extraction fails
```bash
# Check review queue
curl http://localhost:8000/api/review-queue

# Check extraction status
curl http://localhost:8000/api/extractions/{id}
```

### Database connection fails
```bash
# Verify environment variables
echo %SUPABASE_URL%
echo %SUPABASE_KEY%

# Test connection
"C:\Python314\python.exe" -c "from supabase import create_client; import os; c = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY']); print('OK')"
```

---

**Last Updated:** 2026-02-03
