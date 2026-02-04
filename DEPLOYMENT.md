# PDF Extraction API - Deployment Guide

Complete deployment guide for the Academic PDF Extraction Microservice with Hybrid Architecture (OpenDataLoader + Gemini).

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Supabase Setup](#supabase-setup)
4. [Gemini API Setup](#gemini-api-setup)
5. [Docker Deployment](#docker-deployment)
6. [Local Development](#local-development)
7. [Health Checks](#health-checks)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

- **Docker** 20.10+ and **Docker Compose** 2.0+
- **Python** 3.11+ (for local development)
- **Git** (for cloning the repository)

### Required Services

- **Supabase Account** (free tier available at [supabase.com](https://supabase.com))
- **Google Cloud Account** with Gemini API access

---

## Environment Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd PDF-Extraction
```

### 2. Create Environment File

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

### 3. Configure Environment Variables

Edit `.env` with your configuration:

```env
# Gemini API Configuration
GEMINI_API_KEY=your_gemini_api_key_here
MODEL_NAME=gemini-3-flash-preview

# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key_here

# Hybrid Mode Configuration (Optional)
ENABLE_HYBRID_MODE=true
QUALITY_THRESHOLD=0.7

# File Validation Configuration (Optional)
MAX_FILE_SIZE_MB=200

# Context Caching (Optional - for 95% cost savings)
ENABLE_CONTEXT_CACHING=true

# Gemini Batch API (Optional - 50% cost for large batches, ~24h turnaround)
BATCH_API_THRESHOLD=100
BATCH_API_POLL_INTERVAL=60
BATCH_API_MODEL=models/gemini-2.5-flash
```

---

## Supabase Setup

### 1. Create a Supabase Project

1. Go to [supabase.com](https://supabase.com) and sign up
2. Click "New Project"
3. Fill in project details:
   - **Project Name**: pdf-extraction
   - **Database Password**: (strong password)
   - **Region**: Choose closest to your users
4. Wait for project to provision (~2 minutes)

### 2. Get Connection Details

From your Supabase project dashboard:

1. Go to **Settings → API**
2. Copy the following values to your `.env`:
   - **Project URL** → `SUPABASE_URL`
   - **anon public key** → `SUPABASE_KEY`

### 3. Run Database Migrations

Run the SQL migrations to create required tables:

```bash
# Connect to Supabase SQL Editor (Project → SQL Editor → New Query)
```

Execute the following migrations in order:

#### Migration 001: Extractions Table

```sql
-- Run: migrations/001_create_extractions_table.sql
CREATE TABLE IF NOT EXISTS extractions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_name TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'partial', 'failed')),
    metadata JSONB,
    abstract TEXT,
    sections JSONB,
    tables JSONB,
    references JSONB,
    confidence_score REAL,
    bounding_boxes JSONB,
    processing_metadata JSONB,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    webhook_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_extractions_file_hash ON extractions(file_hash);
CREATE INDEX idx_extractions_status ON extractions(status);
CREATE INDEX idx_extractions_created_at ON extractions(created_at DESC);
```

#### Migration 002: Review Queue Table

```sql
-- Run: migrations/002_create_review_queue_table.sql
CREATE TABLE IF NOT EXISTS review_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID REFERENCES extractions(id),
    status TEXT NOT NULL CHECK (status IN ('pending', 'in_review', 'approved', 'rejected')),
    priority INTEGER DEFAULT 0,
    assigned_to TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_review_queue_status ON review_queue(status);
CREATE INDEX idx_review_queue_priority ON review_queue(priority DESC);
```

#### Migration 003: Batch Jobs Table

```sql
-- Run: migrations/003_create_batch_jobs_table.sql
CREATE TYPE batch_status AS ENUM ('pending', 'processing', 'completed', 'failed', 'partial');

CREATE TABLE IF NOT EXISTS batch_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status batch_status NOT NULL DEFAULT 'pending',
    total_files INTEGER NOT NULL,
    completed_files INTEGER DEFAULT 0,
    failed_files INTEGER DEFAULT 0,
    routing_stats JSONB DEFAULT '{"hybrid": 0, "vision_fallback": 0, "pending": 0}',
    extraction_ids UUID[] DEFAULT '{}',
    cost_estimate_usd REAL DEFAULT 0.0,
    cost_savings_usd REAL DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_batch_jobs_status ON batch_jobs(status);
CREATE INDEX idx_batch_jobs_created_at ON batch_jobs(created_at DESC);
```

#### Migration 018: Gemini Batch Jobs Table

For Gemini Batch API (validation and extraction at 50% cost for large batches), run:

```sql
-- Run: migrations/018_gemini_batch_jobs.sql
CREATE TABLE IF NOT EXISTS gemini_batch_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gemini_job_name TEXT NOT NULL UNIQUE,
    job_type TEXT NOT NULL CHECK (job_type IN ('validation', 'extraction')),
    status TEXT NOT NULL DEFAULT 'pending',
    total_requests INT NOT NULL,
    completed_requests INT DEFAULT 0,
    failed_requests INT DEFAULT 0,
    source_job_id UUID,
    request_metadata JSONB,
    result_file_name TEXT,
    error_message TEXT,
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_gemini_batch_jobs_status ON gemini_batch_jobs(status);
CREATE INDEX IF NOT EXISTS idx_gemini_batch_jobs_source_job_id ON gemini_batch_jobs(source_job_id);
```

### 4. Verify Database Setup

```bash
# Test connection with Python
python -c "from app.db.supabase_client import get_supabase_client; client = get_supabase_client(); print('✅ Connected to Supabase')"
```

---

## Gemini API Setup

### 1. Get a Gemini API Key

1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Click "Create API Key"
3. Select or create a Google Cloud project
4. Copy the API key
5. Add to `.env`: `GEMINI_API_KEY=your_key_here`

### 2. Verify API Access

```bash
# Test Gemini API connection
python -c "from app.services.gemini_client import get_gemini_client; client = get_gemini_client(); print('✅ Connected to Gemini API')"
```

### 3. Enable Gemini 3 Flash (if needed)

Ensure your Google Cloud project has access to `gemini-3-flash-preview` model:

- Go to [Google Cloud Console](https://console.cloud.google.com)
- Enable **Generative Language API**
- Check quota limits

---

## Docker Deployment

### 1. Build Docker Image

```bash
# Build the image
docker build -t pdf-extraction-api .

# Verify the image
docker images | grep pdf-extraction
```

### 2. Run with Docker Compose

```bash
# Start the service
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop the service
docker-compose down
```

### 3. Verify Deployment

```bash
# Check health endpoint
curl http://localhost:8000/health

# Expected response:
# {
#   "status": "healthy",
#   "timestamp": "2024-01-28T...",
#   "services": {
#     "opendataloader": "healthy",
#     "gemini_api": "healthy",
#     "supabase": "healthy"
#   }
# }
```

### 4. Test API

```bash
# Upload a test PDF
curl -X POST http://localhost:8000/api/extract \
  -F "file=@sample.pdf" \
  -H "Accept: application/json"

# Get extraction by ID
curl http://localhost:8000/api/extractions/{extraction_id}
```

---

## Local Development

### 1. Create Virtual Environment

```bash
# Create venv
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Linux/Mac)
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run Development Server

```bash
# Run with hot reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run with specific environment file
uvicorn app.main:app --env-file .env.development --reload
```

### 4. Run Gemini Batch API Poller (Optional)

When using the Gemini Batch API for validation or extraction (100+ files), run the poller so completed batch jobs are processed and results written to the database:

```bash
# Poll once and exit (e.g. from cron)
python -m app.cli poll-batch-jobs --once

# Poll every 60 seconds (long-running process)
python -m app.cli poll-batch-jobs --interval 60

# Only process validation or extraction jobs
python -m app.cli poll-batch-jobs --job-type validation --once
```

### 5. Run Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=term-missing

# Run integration tests only
pytest tests/integration/ -v

# Run specific test file
pytest tests/test_pdf_extractor.py -v
```

### 6. Code Quality Checks

```bash
# Type checking with mypy
mypy app/ --strict

# Linting (if using)
flake8 app/ tests/
black app/ tests/ --check
```

---

## Health Checks

### Health Check Endpoint

```bash
GET /health
```

**Response (200 OK):**

```json
{
  "status": "healthy",
  "timestamp": "2024-01-28T12:00:00Z",
  "services": {
    "opendataloader": "healthy",
    "gemini_api": "healthy",
    "supabase": "healthy"
  }
}
```

**Response (503 Service Unavailable):**

```json
{
  "status": "unhealthy",
  "timestamp": "2024-01-28T12:00:00Z",
  "services": {
    "opendataloader": "healthy",
    "gemini_api": "unhealthy: API key invalid",
    "supabase": "healthy"
  }
}
```

### Version Endpoint

```bash
GET /version
```

**Response:**

```json
{
  "version": "1.0.0",
  "commit_hash": "abc123def"
}
```

### Docker Health Check

Docker automatically runs health checks:

```bash
# Check container health
docker ps

# View health check logs
docker inspect --format='{{.State.Health.Status}}' <container_id>
```

---

## Troubleshooting

### Common Issues

#### 1. **503 Service Unavailable**

**Symptoms:** `/health` endpoint returns 503

**Causes:**
- Invalid API keys
- Database connection failure
- Missing environment variables

**Solutions:**

```bash
# Check logs
docker-compose logs app

# Verify environment variables
docker-compose exec app env | grep GEMINI
docker-compose exec app env | grep SUPABASE

# Test database connection
docker-compose exec app python -c "from app.db.supabase_client import get_supabase_client; get_supabase_client()"
```

#### 2. **File Upload Fails**

**Symptoms:** 400 or 413 errors on `/api/extract`

**Causes:**
- File too large (> 200MB)
- Invalid file type (not PDF)
- Corrupted PDF

**Solutions:**

```bash
# Check file size
ls -lh sample.pdf

# Verify PDF validity
file sample.pdf  # Should output "PDF document"

# Increase max file size in .env
MAX_FILE_SIZE_MB=500
```

#### 3. **Slow Extraction Performance**

**Symptoms:** Extraction takes > 30 seconds

**Causes:**
- Large multi-page PDFs
- Vision fallback (low quality PDFs)
- High API latency

**Solutions:**

```bash
# Enable context caching for 95% cost savings
ENABLE_CONTEXT_CACHING=true

# Check routing statistics
curl http://localhost:8000/api/stats/routing

# Use batch processing for multiple files
curl -X POST http://localhost:8000/api/batch -F "files=@doc1.pdf" -F "files=@doc2.pdf"
```

#### 4. **Database Migration Errors**

**Symptoms:** SQL errors on startup

**Solutions:**

```bash
# Check if tables exist
psql $SUPABASE_URL -c "\\dt"

# Re-run migrations manually via Supabase SQL Editor
# Copy content from migrations/*.sql
```

#### 5. **Docker Build Fails**

**Symptoms:** `docker build` errors

**Solutions:**

```bash
# Clear Docker cache
docker system prune -a

# Rebuild without cache
docker build --no-cache -t pdf-extraction-api .

# Check Docker daemon
docker info
```

---

## Production Deployment Recommendations

### 1. Security

- Use **secrets management** (AWS Secrets Manager, HashiCorp Vault)
- Enable **HTTPS** (use reverse proxy like Nginx)
- Implement **API authentication** (API keys, JWT)
- Set **CORS** to specific domains (not `*`)
- Use **rate limiting** (already configured via slowapi)

### 2. Scaling

- Deploy on **Kubernetes** for horizontal scaling
- Use **load balancer** for multiple instances
- Enable **auto-scaling** based on CPU/memory
- Consider **async workers** for batch processing

### 3. Monitoring

- Set up **application monitoring** (Datadog, New Relic)
- Enable **structured logging** (JSON format)
- Track **cost metrics** via `/api/stats/routing`
- Configure **alerts** for health check failures

### 4. Backup

- **Supabase** automatic backups (enabled by default)
- Export **database schema** regularly
- Version control **migrations**

---

## API Documentation

Once deployed, access interactive API documentation:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

---

## Support

For issues and questions:

- **GitHub Issues**: <repository-url>/issues
- **Documentation**: See `README.md` and `Prd.md`
- **Architecture**: Hybrid OpenDataLoader + Gemini (80% cost savings)

---

## License

[Your License Here]
