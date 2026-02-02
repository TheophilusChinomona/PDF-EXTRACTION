# PDF Extraction Service

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-teal)
![License](https://img.shields.io/badge/license-MIT-green)

**A production-ready microservice for extracting structured data from academic exam papers and marking guidelines (memos).**

Designed to integrate with your main backend and frontend applications, this service uses a hybrid AI pipeline combining local PDF parsing (OpenDataLoader) with semantic AI analysis (Google Gemini 3) to achieve 95%+ accuracy at 80% cost savings.

---

## 📖 Overview

### Problem Solved
Traditional OCR fails on complex academic documents with multi-column layouts, mathematical formulas, tables, and diagrams. This microservice provides intelligent extraction with:

- **Automatic document classification** (exam paper vs memo/marking guideline)
- **Structured JSON output** with bounding boxes for frontend highlighting
- **Hybrid processing** (local → AI fallback) for optimal cost/quality
- **Batch processing** for bulk uploads via CLI
- **RESTful API** for easy integration with any backend/frontend

### Architecture

```
Frontend App → Your Backend → PDF Extraction Service → Supabase
                                     ↓
                          [OpenDataLoader + Gemini 3]
```

**Processing Flow:**
1. **Classification**: Auto-detect document type (question paper or memo)
2. **Structure Extraction**: OpenDataLoader parses PDF locally (0.05s/page)
3. **Quality Analysis**: Calculate extraction confidence score
4. **Smart Routing**: Use AI only when needed (quality < 0.7)
5. **Data Storage**: Results saved to Supabase with full metadata

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+** (tested with Python 3.14)
- **Google Cloud API Key** (Gemini 3 Flash)
- **Supabase Project** (URL + Service Key)
- **Operating System**: Windows, Linux, or macOS

### Installation

#### 1. Clone Repository
```bash
git clone https://github.com/yourusername/PDF-Extraction.git
cd PDF-Extraction
```

#### 2. Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

#### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 4. Configure Environment
Create a `.env` file in the project root:

```env
# Required: AI and Database
GEMINI_API_KEY=your_gemini_api_key_here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_service_role_key_here

# Optional: Model Configuration
MODEL_NAME=gemini-3-flash-preview
ENABLE_HYBRID_MODE=true

# Optional: Security (for production)
ALLOWED_ORIGINS=*                    # Dev: *, Prod: https://yourdomain.com
TRUSTED_PROXIES=                     # Leave empty unless behind proxy

# Optional: Performance Tuning
BATCH_WORKERS=1                      # CLI: PDFs to process in parallel
BATCH_API_LIMIT=3                    # CLI: Max concurrent API calls
```

> **Security Note**: For production, set `ALLOWED_ORIGINS` to your frontend domain(s) and configure `TRUSTED_PROXIES` if behind a load balancer.

#### 5. Setup Database (Supabase)

**Apply database migrations to create required tables:**

```bash
# Option 1: Supabase Dashboard (Easiest)
# 1. Go to https://app.supabase.com → Your Project → SQL Editor
# 2. Run each migration file in migrations/ folder in order (001-005)
# See MIGRATIONS_SETUP.md for detailed instructions

# Option 2: Automated Script (Windows)
cd migrations
apply_migrations.bat

# Option 3: Automated Script (Linux/macOS)
cd migrations
chmod +x apply_migrations.sh
./apply_migrations.sh

# Option 4: Verify schema with Python
python migrations/verify_schema.py
```

**Tables created:**
- `extractions` - Question paper extraction results
- `memo_extractions` - Marking guideline (memo) results
- `batch_jobs` - Batch processing jobs
- `review_queue` - Manual review queue for failed extractions

📖 **Full migration guide:** [MIGRATIONS_SETUP.md](./MIGRATIONS_SETUP.md)

---

## 🔧 Running the Service

### Option 1: Development Server (Local Testing)

Start the FastAPI server for development:

```bash
# Method 1: Using uvicorn directly
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Method 2: Using Python module
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:
- **Base URL**: http://localhost:8000
- **Swagger Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Option 2: Production Server (Gunicorn + Uvicorn)

For production deployments:

```bash
# Install gunicorn
pip install gunicorn

# Run with multiple workers
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 300
```

### Option 3: Docker (Recommended for Production)

```bash
# Build image
docker build -t pdf-extraction:latest .

# Run container
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  --name pdf-extraction \
  pdf-extraction:latest
```

---

## 💻 CLI Usage (Batch Processing)

Process local PDF files directly without going through the API.

### Basic Commands

```bash
# Process all PDFs matching pattern in default directory
python -m app.cli batch-process

# Process specific directory
python -m app.cli batch-process --directory "C:\Users\theoc\Documents\Exams"

# Process with custom pattern
python -m app.cli batch-process --pattern "*.pdf"

# Parallel processing (5 PDFs at once)
python -m app.cli batch-process --workers 5

# Limit API concurrency (prevent rate limits)
python -m app.cli batch-process --workers 10 --api-limit 3

# Full example
python -m app.cli batch-process \
  --directory "Sample PDFS" \
  --pattern "document_*.pdf" \
  --workers 5 \
  --api-limit 3
```

### CLI Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--directory` | `-d` | Directory containing PDFs | `Sample PDFS/` |
| `--pattern` | `-p` | Glob pattern for files | `document_*.pdf` |
| `--workers` | `-w` | Parallel PDF processing | `1` (from env) |
| `--api-limit` | `-a` | Max concurrent API calls | `3` (from env) |

### Output

The CLI tool:
1. **Processes each PDF** using the hybrid pipeline
2. **Classifies document type** (question paper or memo)
3. **Renames files** to canonical format:
   - Example: `business-studies-p1-gr12-may-june-2023-qp.pdf`
   - Example: `mathematics-p2-gr11-nov-2024-mg.pdf`
4. **Saves JSON results** alongside each PDF
5. **Generates summary** in `_batch_summary.json`

**Performance:**
- Sequential (`--workers 1`): ~60-90s per PDF
- Parallel (`--workers 5`): ~4-5x faster for batches
- API limiting prevents quota exhaustion

---

## 📡 API Integration

### Quick Test

```bash
# Health check
curl http://localhost:8000/health

# Upload single PDF
curl -X POST http://localhost:8000/api/extract \
  -F "file=@path/to/exam_paper.pdf"
```

### Integration with Your Backend

#### Example: Node.js/Express Backend

```javascript
const FormData = require('form-data');
const axios = require('axios');
const fs = require('fs');

async function extractPDF(filePath) {
  const form = new FormData();
  form.append('file', fs.createReadStream(filePath));

  const response = await axios.post(
    'http://localhost:8000/api/extract',
    form,
    { headers: form.getHeaders() }
  );

  return response.data;
}

// Use in your route
app.post('/upload-exam', async (req, res) => {
  try {
    const result = await extractPDF(req.file.path);

    // Save to your database
    await db.exams.create({
      extractionId: result.id,
      subject: result.subject,
      grade: result.grade,
      questions: result.groups
    });

    res.json({ success: true, data: result });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});
```

#### Example: Python/FastAPI Backend

```python
import httpx
from fastapi import UploadFile

async def extract_pdf(file: UploadFile):
    async with httpx.AsyncClient() as client:
        files = {"file": (file.filename, await file.read(), file.content_type)}
        response = await client.post(
            "http://localhost:8000/api/extract",
            files=files,
            timeout=300.0
        )
        response.raise_for_status()
        return response.json()

# Use in your endpoint
@app.post("/process-exam")
async def process_exam(file: UploadFile):
    result = await extract_pdf(file)

    # Store in your database
    exam_id = await db.save_exam(
        extraction_id=result["id"],
        subject=result["subject"],
        data=result
    )

    return {"exam_id": exam_id, "extraction": result}
```

### Frontend Integration

#### Example: React Frontend

```typescript
async function uploadExamPaper(file: File) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('YOUR_BACKEND_URL/upload-exam', {
    method: 'POST',
    body: formData
  });

  if (!response.ok) throw new Error('Upload failed');

  const data = await response.json();

  // Display extracted questions
  renderQuestions(data.extraction.groups);
}

// Display with bounding boxes
function renderQuestions(groups: QuestionGroup[]) {
  return groups.map(group => (
    <div key={group.group_id}>
      <h2>{group.title}</h2>
      {group.questions.map(q => (
        <QuestionCard
          key={q.id}
          question={q}
          onHighlight={() => highlightInPDF(q.bbox)}
        />
      ))}
    </div>
  ));
}
```

---

## 📊 API Endpoints

Full API documentation: [api-documentation.md](./api-documentation.md)

### Core Endpoints

| Method | Endpoint | Description | Rate Limit |
|--------|----------|-------------|------------|
| `GET` | `/health` | Service health check | 200/min |
| `GET` | `/version` | API version info | 200/min |
| `POST` | `/api/extract` | Upload single PDF | 10/min |
| `GET` | `/api/extractions/{id}` | Get extraction result | 100/min |
| `GET` | `/api/extractions` | List all extractions | 100/min |
| `GET` | `/api/extractions/{id}/bounding-boxes` | Get PDF coordinates | 100/min |
| `POST` | `/api/batch` | Upload multiple PDFs | 2/min |
| `GET` | `/api/batch/{id}` | Get batch status | 100/min |
| `GET` | `/api/review-queue` | List failed extractions | 100/min |
| `GET` | `/api/stats/caching` | Cache hit statistics | 100/min |

---

## 🗂️ Project Structure

```
PDF-Extraction/
├── app/
│   ├── main.py                 # FastAPI application entry point
│   ├── cli.py                  # CLI commands (batch processing)
│   ├── config.py               # Environment configuration
│   ├── routers/                # API endpoints
│   │   ├── extraction.py       # Main extraction endpoints
│   │   ├── batch.py            # Batch processing API
│   │   ├── review_queue.py     # Manual review workflow
│   │   └── stats.py            # Analytics endpoints
│   ├── services/               # Business logic
│   │   ├── pdf_extractor.py    # Exam paper extraction
│   │   ├── memo_extractor.py   # Memo extraction
│   │   ├── document_classifier.py  # Auto-classification
│   │   ├── batch_processor.py  # CLI batch processing
│   │   └── opendataloader_extractor.py  # Local PDF parsing
│   ├── models/                 # Pydantic schemas
│   │   ├── extraction.py       # Exam paper models
│   │   ├── memo_extraction.py  # Memo models
│   │   └── classification.py   # Document type models
│   ├── db/                     # Database layer
│   │   ├── extractions.py      # Exam paper DB operations
│   │   ├── memo_extractions.py # Memo DB operations
│   │   └── supabase_client.py  # Supabase connection
│   ├── middleware/             # HTTP middleware
│   │   ├── rate_limit.py       # Rate limiting
│   │   └── logging.py          # Request logging
│   └── utils/                  # Utilities
│       └── retry.py            # Retry with backoff
├── tests/                      # Test suite (273 tests)
├── Sample PDFS/                # Test PDF files
├── .env.example                # Environment template
├── requirements.txt            # Python dependencies
├── api-documentation.md        # Full API reference
├── DEPLOYMENT.md               # Deployment guide
└── README.md                   # This file
```

---

## 🧪 Testing

### Run Test Suite

```bash
# All tests
pytest tests/ -v

# With coverage report
pytest tests/ --cov=app --cov-report=html

# Specific test file
pytest tests/test_extraction_router.py -v

# Verify fixes
python verify_fixes.py
```

### Manual Testing

```bash
# Test health endpoint
curl http://localhost:8000/health

# Test extraction (replace with your PDF path)
curl -X POST http://localhost:8000/api/extract \
  -F "file=@Sample PDFS/document_62.pdf"

# Test batch CLI
python -m app.cli batch-process --workers 2
```

---

## 🔒 Security Features

✅ **Implemented:**
- CORS origin validation (environment-based)
- Rate limiting per IP address
- X-Forwarded-For spoofing prevention
- File size limits (200MB)
- PDF validation and sanitization
- Null safety for API responses

⚠️ **Production Recommendations:**
1. Set `ALLOWED_ORIGINS` to specific domains
2. Configure `TRUSTED_PROXIES` if behind load balancer
3. Use HTTPS in production
4. Implement authentication in your backend layer
5. Monitor rate limit headers

---

## 📈 Performance Optimization

### Hybrid Architecture Benefits
- **80% cost reduction** (local processing + smart AI fallback)
- **0.05s/page** for structure extraction (OpenDataLoader)
- **95%+ accuracy** with Gemini semantic analysis
- **Context caching** saves ~90% on repeated system instructions

### Scaling Recommendations

**Vertical Scaling:**
```bash
# Increase workers for CPU-bound tasks
gunicorn app.main:app --workers 8 --worker-class uvicorn.workers.UvicornWorker
```

**Horizontal Scaling:**
```bash
# Deploy multiple instances behind load balancer
docker-compose up --scale pdf-extraction=3
```

**Database Optimization:**
- Enable Supabase connection pooling
- Use read replicas for analytics queries
- Index `file_hash` column for duplicate detection

---

## 🐛 Troubleshooting

### Common Issues

**1. Import Errors**
```bash
# Ensure virtual environment is activated
which python  # Should show venv/bin/python

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

**2. Gemini API Errors**
```bash
# Check API key
echo $GEMINI_API_KEY  # Should not be empty

# Test API connection
curl https://generativelanguage.googleapis.com/v1beta/models \
  -H "x-goog-api-key: $GEMINI_API_KEY"
```

**3. Supabase Connection Fails**
```bash
# Verify URL and key in .env
# Check Supabase project status
# Ensure service role key (not anon key) for full access
```

**4. Port Already in Use**
```bash
# Kill existing process
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/macOS
lsof -ti:8000 | xargs kill -9
```

---

## 📚 Additional Documentation

- **[API Documentation](./api-documentation.md)** - Complete API reference
- **[Deployment Guide](./DEPLOYMENT.md)** - Production deployment
- **[Code Review Report](./CODE_REVIEW.md)** - Security & code quality
- **[Fixes Verification](./FIXES_VERIFICATION_REPORT.md)** - Recent improvements

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'feat: add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Commit Convention
```
feat: Add new feature
fix: Fix bug
docs: Update documentation
test: Add tests
refactor: Code refactoring
```

---

## 📝 License

MIT License - see [LICENSE](./LICENSE) file for details.

---

## 🙋 Support

**Questions or Issues?**
- Open an issue: [GitHub Issues](https://github.com/yourusername/PDF-Extraction/issues)
- Email: your.email@example.com

---

## 🎯 Roadmap

- [ ] Support for more document types (essays, assignments)
- [ ] Diagram/image extraction with descriptions
- [ ] Multi-language support (translations)
- [ ] Real-time WebSocket extraction progress
- [ ] GraphQL API alternative
- [ ] Self-hosted AI model option

---

**Built with ❤️ using FastAPI, OpenDataLoader, and Google Gemini 3**
