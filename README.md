# PDF Extraction Service

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-teal)
![License](https://img.shields.io/badge/license-MIT-green)

**A production-ready microservice for extracting structured data from academic exam papers and marking guidelines (memos).**

Designed to integrate with your main backend and frontend applications, this service uses a hybrid AI pipeline combining local PDF parsing (OpenDataLoader) with semantic AI analysis (Google Gemini 3) to achieve 95%+ accuracy at 80% cost savings.

---

## Overview

### Problem Solved
Traditional OCR fails on complex academic documents with multi-column layouts, mathematical formulas, tables, and diagrams. This microservice provides intelligent extraction with:

- **Automatic document classification** (exam paper vs memo/marking guideline)
- **Structured JSON output** with bounding boxes for frontend highlighting
- **Hybrid processing** (local + AI fallback) for optimal cost/quality
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

## Quick Start

### Prerequisites

- **Python 3.11+** (tested with Python 3.14)
- **Google Cloud API Key** (Gemini 3 Flash)
- **Supabase Project** (URL + Service Key)
- **Operating System**: Windows, Linux, or macOS

### Installation

#### 1. Clone Repository
```bash
git clone https://github.com/TheophilusChinomona/PDF-EXTRACTION.git
cd PDF-Extraction
```

#### 2. Install Dependencies

**Option A: System Python (Recommended for this project)**
```bash
# Install to system Python
pip install -r requirements.txt
```

**Option B: Virtual Environment**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 3. Configure Environment

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

#### 4. Setup Database (Supabase)

Apply database migrations to create required tables:

```bash
# Option 1: Supabase Dashboard (Recommended)
# 1. Go to https://app.supabase.com → Your Project → SQL Editor
# 2. Run each migration file in migrations/ folder in order

# Option 2: Verify schema with Python
python migrations/verify_schema.py
```

**Tables created:**
- `extractions` - Question paper extraction results
- `memo_extractions` - Marking guideline (memo) results
- `batch_jobs` - Batch processing jobs
- `review_queue` - Manual review queue for failed extractions

---

## Running the Service

### Development Server

```bash
# Using system Python
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or if using virtual environment
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:
- **Base URL**: http://localhost:8000
- **Swagger Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Production Server (Docker)

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

## CLI Usage (Batch Processing)

Process local PDF files directly without going through the API.

### Basic Commands

```bash
# Process all PDFs in default directory
python -m app.cli batch-process

# Process specific directory
python -m app.cli batch-process --directory "path/to/pdfs"

# Parallel processing
python -m app.cli batch-process --workers 5 --api-limit 3
```

### CLI Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--directory` | `-d` | Directory containing PDFs | `Sample PDFS/` |
| `--pattern` | `-p` | Glob pattern for files | `*.pdf` |
| `--workers` | `-w` | Parallel PDF processing | `1` |
| `--api-limit` | `-a` | Max concurrent API calls | `3` |

---

## API Endpoints

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

### Quick Test

```bash
# Health check
curl http://localhost:8000/health

# Upload single PDF
curl -X POST http://localhost:8000/api/extract \
  -F "file=@path/to/exam_paper.pdf"
```

---

## Project Structure

```
PDF-Extraction/
├── app/
│   ├── main.py                 # FastAPI application entry point
│   ├── cli.py                  # CLI commands (batch processing)
│   ├── config.py               # Environment configuration
│   ├── routers/                # API endpoints
│   ├── services/               # Business logic
│   ├── models/                 # Pydantic schemas
│   ├── db/                     # Database layer
│   ├── middleware/             # HTTP middleware
│   └── utils/                  # Utilities
├── tests/                      # Test suite
├── migrations/                 # Database migrations
├── scripts/                    # Utility scripts
├── docs/                       # Documentation
│   └── archive/                # Historical reports
├── Sample PDFS/                # Test PDF files
├── .claude/                    # Agent instructions
├── .env.example                # Environment template
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Container build
├── docker-compose.yml          # Container orchestration
├── api-documentation.md        # Full API reference
├── DEPLOYMENT.md               # Deployment guide
└── README.md                   # This file
```

---

## Testing

### Run Test Suite

```bash
# All tests
python -m pytest tests/ -v

# With coverage report
python -m pytest tests/ --cov=app --cov-report=html

# Specific test file
python -m pytest tests/test_extraction_router.py -v
```

---

## Security Features

**Implemented:**
- CORS origin validation (environment-based)
- Rate limiting per IP address
- X-Forwarded-For spoofing prevention
- File size limits (200MB)
- PDF validation and sanitization
- Null safety for API responses

**Production Recommendations:**
1. Set `ALLOWED_ORIGINS` to specific domains
2. Configure `TRUSTED_PROXIES` if behind load balancer
3. Use HTTPS in production
4. Implement authentication in your backend layer
5. Monitor rate limit headers

---

## Performance

### Hybrid Architecture Benefits
- **80% cost reduction** (local processing + smart AI fallback)
- **0.05s/page** for structure extraction (OpenDataLoader)
- **95%+ accuracy** with Gemini semantic analysis
- **Context caching** saves ~90% on repeated system instructions

### Scaling Recommendations

**Docker Scaling:**
```bash
docker-compose up --scale pdf-extraction=3
```

**Database Optimization:**
- Enable Supabase connection pooling
- Use read replicas for analytics queries
- Index `file_hash` column for duplicate detection

---

## Troubleshooting

### Common Issues

**1. Import Errors**
```bash
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
- Verify URL and key in `.env`
- Check Supabase project status
- Ensure service role key (not anon key) for full access

**4. Port Already in Use**
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/macOS
lsof -ti:8000 | xargs kill -9
```

---

## Documentation

- **[API Documentation](./api-documentation.md)** - Complete API reference
- **[Deployment Guide](./DEPLOYMENT.md)** - Production deployment

---

## Contributing

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

## License

MIT License - see [LICENSE](./LICENSE) file for details.

---

## Roadmap

- [ ] Support for more document types (essays, assignments)
- [ ] Diagram/image extraction with descriptions
- [ ] Multi-language support (translations)
- [ ] Real-time WebSocket extraction progress
- [ ] GraphQL API alternative
- [ ] Self-hosted AI model option

---

**Built with FastAPI, OpenDataLoader, and Google Gemini 3**
