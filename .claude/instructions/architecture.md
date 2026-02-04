# Architecture

## Overview
Hybrid extraction pipeline architecture with dual-path processing: online API for real-time needs, Batch API for large volumes.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11+, FastAPI |
| AI/ML | Google Gemini 3 API (Online + Batch) + OpenDataLoader PDF |
| Database | Supabase (PostgreSQL) |
| Storage | Firebase/GCS for PDF storage |
| Key Libraries | opendataloader-pdf, google-genai, fastapi, supabase-py, pydantic |

---

## Dual Processing Paths

### Online API (Real-time)
| Component | Role | Performance |
|-----------|------|-------------|
| **OpenDataLoader** (local) | PDF structure, tables, bounding boxes | 0.05s/page, $0 cost, F1: 0.93 |
| **Gemini 3 API** (cloud) | Semantic analysis | 80% cost reduction vs pure AI |

### Batch API (Large volumes, 100+ files)
| Component | Role | Performance |
|-----------|------|-------------|
| **Gemini Batch API** | Async processing of 100+ files | 50% cost savings, 24h SLO |
| **File API** | Upload PDFs for batch processing | Auto-cleanup after job creation |

---

## File Organization

```
pdf-extraction/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── cli.py               # CLI commands (poll-batch-jobs, etc.)
│   ├── routers/             # API route handlers
│   │   ├── batch.py         # POST /api/batch (use_batch_api option)
│   │   ├── validation.py    # POST /api/validation/batch (auto batch API)
│   │   └── extraction.py    # POST /api/extract
│   ├── services/
│   │   ├── gemini_batch.py      # Core Batch API operations
│   │   ├── validation_batch.py  # Batch validation processor
│   │   ├── extraction_batch.py  # Batch extraction processor
│   │   ├── batch_job_poller.py  # Background job poller
│   │   ├── pdf_extractor.py     # Online extraction
│   │   └── memo_extractor.py    # Memo extraction
│   ├── models/              # Pydantic schemas
│   ├── db/
│   │   ├── gemini_batch_jobs.py # Batch job CRUD
│   │   ├── batch_jobs.py        # Internal batch jobs
│   │   ├── extractions.py       # Extraction results
│   │   └── validation_results.py
│   └── config.py            # Configuration (batch_api_threshold, etc.)
├── scripts/
│   ├── run_extraction_batch_from_validated.py  # Test script
│   └── check_revalidate_progress.py
├── migrations/
│   └── 018_gemini_batch_jobs.sql  # Batch jobs table
├── tests/                   # Unit and integration tests
├── .env                     # Environment variables (NEVER commit)
└── requirements.txt         # Python dependencies
```

---

## Online Routing Logic

```
PDF Input
    │
    ▼
OpenDataLoader (local extraction)
    │
    ▼
Quality Score Check
    │
    ├── score >= 0.7 → Gemini Text Analysis (80% cheaper)
    │
    └── score < 0.7  → Gemini Vision Fallback
    │
    ▼
Merge Results + Store in Supabase
```

---

## Batch API Flow

```
Batch Request (100+ files)
    │
    ▼
Router checks batch_api_threshold
    │
    ├── < threshold → Online processing (sequential)
    │
    └── >= threshold → Batch API path:
        │
        ▼
    Upload PDFs to Gemini File API
        │
        ▼
    Submit batch job (client.batches.create)
        │
        ▼
    Store in gemini_batch_jobs (status: pending)
        │
        ▼
    Return gemini_batch_job_id to client
        │
        ▼
    [Later: Poller checks status]
        │
        ▼
    Job complete → Download results
        │
        ▼
    Create extractions/memo_extractions
        │
        ▼
    Update batch_jobs counters
```

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `gemini_batch_jobs` | Track Gemini Batch API jobs (name, status, requests, metadata) |
| `batch_jobs` | Internal batch job tracking, linked to gemini_batch_jobs via source_job_id |
| `validation_results` | Validation outcomes per scraped_file_id |
| `validation_jobs` | Batch validation job progress |
| `extractions` | Question paper extraction results |
| `memo_extractions` | Marking guideline extraction results |
| `scraped_files` | Source files with storage_bucket/path |
| `exam_sets` | Matched QP + Memo pairs |
