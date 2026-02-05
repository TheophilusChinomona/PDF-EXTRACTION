# Running PDF Extraction Locally

This guide shows how to run the extraction service locally with sample PDFs using the Gemini API.

---

## Quick Start

### 1. Set up environment variables

Create `.env` file (copy from `.env.example`):

```env
# Required
GEMINI_API_KEY=your_gemini_api_key_here

# Optional (only if saving to DB)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
```

### 2. Start the local server

```bash
cd "C:\Users\theoc\Desktop\Work\PDF-Extraction"
"C:\Python314\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3. Extract a single PDF via curl/PowerShell

**PowerShell:**
```powershell
# Single PDF extraction
$file = Get-Item "C:\path\to\your\sample.pdf"
Invoke-RestMethod -Uri "http://localhost:8000/api/extract" -Method Post -Form @{
    file = $file
    doc_type = "question_paper"  # or "memo" for marking guidelines
}
```

**curl (Git Bash):**
```bash
curl -X POST "http://localhost:8000/api/extract" \
  -F "file=@/c/path/to/your/sample.pdf" \
  -F "doc_type=question_paper"
```

### 4. Batch extraction (multiple PDFs)

```bash
curl -X POST "http://localhost:8000/api/batch" \
  -F "files=@sample1.pdf" \
  -F "files=@sample2.pdf" \
  -F "files=@sample3.pdf"
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/extract` | POST | Extract single PDF |
| `/api/batch` | POST | Extract multiple PDFs |
| `/api/extractions/{id}` | GET | Get extraction result |
| `/docs` | GET | Swagger UI (interactive API docs) |

---

## Document Types

- `doc_type=question_paper` - Exam papers with questions
- `doc_type=memo` - Marking guidelines/memoranda
- Omit `doc_type` for auto-detection

---

## Example: Extract all PDFs in a folder

```powershell
cd "C:\Users\theoc\Desktop\Work\PDF-Extraction"
$pdfs = Get-ChildItem "C:\path\to\pdfs\*.pdf"
foreach ($pdf in $pdfs) {
    Write-Host "Extracting: $($pdf.Name)"
    $result = Invoke-RestMethod -Uri "http://localhost:8000/api/extract" -Method Post -Form @{
        file = $pdf
    }
    $result | ConvertTo-Json -Depth 10 | Out-File "output\$($pdf.BaseName).json"
}
```

---

## Troubleshooting

### Server won't start
- Check that `GEMINI_API_KEY` is set in `.env`
- Ensure port 8000 is not in use

### Extraction fails
- Verify PDF is not corrupted
- Check server logs for detailed error messages
- Ensure PDF is under 200MB

### Rate limiting
- Default: 10 requests/minute
- For batch processing, use `/api/batch` endpoint
