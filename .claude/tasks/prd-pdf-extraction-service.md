# PRD: Academic PDF Extraction Microservice (Hybrid Architecture)

**Created:** 2026-01-27
**Updated:** 2026-01-28
**Status:** Ready for Implementation
**Version:** 2.0 - OpenDataLoader Integration

---

## Introduction

A production-ready FastAPI microservice that extracts structured data from academic PDFs using a **hybrid architecture**: OpenDataLoader for deterministic structure extraction + Google Gemini 3 API for semantic understanding. The service processes multi-page documents, extracts text and visual elements (tables, figures) with bounding boxes, handles batch processing for cost efficiency, implements intelligent retry logic, and stores results in Supabase with webhook notifications.

**Problem Statement:** Academic researchers and institutions need to extract structured data from thousands of PDF papers efficiently and cost-effectively, but manual processing is time-consuming and error-prone. Pure AI approaches are expensive and can hallucinate on complex tables and multi-column layouts.

**Solution:** Hybrid extraction pipeline that combines:
1. **OpenDataLoader PDF** (local, deterministic): Extracts document structure, tables, layout with bounding boxes (0.05s/page, $0 cost)
2. **Gemini 3 API** (cloud, semantic): Analyzes structured content to extract metadata, authors, abstract, citations with AI understanding

**Key Benefits:**
- **80% cost reduction** vs pure AI approach (process structured Markdown instead of full PDF)
- **Higher accuracy** for tables (F1: 0.93 vs variable AI performance)
- **Bounding boxes** for every element (enables citation features, quality validation)
- **Faster processing** (local preprocessing + smaller Gemini payloads)
- **No hallucinations** on document structure (deterministic parsing)

---

## Architecture Overview

```
┌─────────────────────────────┐
│  PDF Upload (FastAPI)       │
│  - Validate & hash file     │
│  - Check for duplicates     │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  OpenDataLoader (Local)     │
│  - Parse PDF structure      │
│  - Extract tables (F1:0.93) │
│  - Multi-column layout      │
│  - Bounding boxes           │
│  - Export to Markdown       │
│  Cost: $0 | Speed: 0.05s/pg │
└──────────┬──────────────────┘
           │
           ├─ Quality Check
           │  Low quality? → Fallback to full Gemini Vision
           │
           ▼
┌─────────────────────────────┐
│  Gemini 3 Flash API         │
│  Input: Structured Markdown │
│  - Extract metadata         │
│  - Parse authors/affiliations│
│  - Summarize abstract       │
│  - Classify sections        │
│  - Parse references         │
│  - Confidence scoring       │
│  Cost: 80% reduction        │
└──────────┬──────────────────┘
           │
           ├─ Merge Results
           │  Structure + Semantics + Bounding Boxes
           │
           ▼
┌─────────────────────────────┐
│  Supabase Storage           │
│  - Extraction result        │
│  - Bounding box coordinates │
│  - Processing metadata      │
│  - Enable "View in PDF"     │
└─────────────────────────────┘
```

---

## Goals

- **Accuracy:** Extract structured academic data with 95%+ accuracy for standard papers (improved from 90% via deterministic table extraction)
- **Cost Efficiency:** 80% cost reduction vs pure AI approach (~$0.002 per PDF vs $0.011)
- **Table Accuracy:** F1-score 0.93 for table extraction (deterministic parsing)
- **Scalability:** Support batch processing of 100+ PDFs per job
- **Reliability:** Handle errors gracefully with automatic retry and partial result storage
- **Provenance:** Provide bounding box coordinates for every extracted element
- **Speed:** 5s local preprocessing + 10-20s Gemini = faster than pure AI (20-60s)
- **Developer Experience:** Clean REST API with comprehensive error messages and Swagger documentation
- **Auditability:** Store all extraction results with timestamps, confidence scores, and processing metadata

---

## User Stories

### Phase 1: Core Infrastructure & Hybrid Extraction Pipeline

#### US-001: Python Project Setup with Modern Gemini SDK and OpenDataLoader

**Description:** As a developer, I need a properly configured Python project with the latest Gemini SDK (`google-genai`) and OpenDataLoader PDF library so that I can build on a solid, maintainable foundation using hybrid extraction architecture.

**Acceptance Criteria:**
- [ ] Project structure created following project guidelines (`app/`, `tests/`, `.env.example`)
- [ ] `requirements.txt` includes:
  - `opendataloader-pdf>=1.0.0` (NEW: local PDF parsing)
  - `google-genai>=0.3.0` (NOT deprecated `google-generativeai`)
  - `fastapi>=0.100.0`
  - `supabase-py>=2.0.0`
  - `pydantic>=2.0.0`
  - `pydantic-settings>=2.0.0`
  - `python-multipart>=0.0.6`
  - `python-dotenv>=1.0.0`
  - `httpx>=0.24.0`
  - `python-magic>=0.4.27`
  - `pytest>=7.4.0`
  - `pytest-asyncio>=0.21.0`
  - `pytest-cov>=4.1.0`
- [ ] `.gitignore` includes `.env`, `__pycache__`, `venv/`, `*.pyc`, `.pytest_cache/`
- [ ] `.env.example` template created with: `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`
- [ ] Virtual environment setup documented in README
- [ ] All files follow PEP 8 standards
- [ ] Type hints enabled in all function signatures

**Technical Notes:**
- Use `from google import genai` (not `google.generativeai`)
- Use `from opendataloader_pdf import DocumentLoader`
- Client initialization: `client = genai.Client()` (reads from `GEMINI_API_KEY` env var)
- Avoid deprecated models like `gemini-1.5-flash`; use `gemini-3-flash-preview` or `gemini-3-pro-preview`

---

#### US-002: Gemini Client Configuration with Error Handling

**Description:** As a developer, I need a robust Gemini API client configuration that handles authentication errors, rate limits, and invalid API keys so that the service fails gracefully with clear error messages.

**Acceptance Criteria:**
- [ ] Create `app/config.py` with Pydantic settings model
- [ ] Load environment variables using `pydantic-settings`
- [ ] Validate `GEMINI_API_KEY` is present on startup (fail fast if missing)
- [ ] Create `app/services/gemini_client.py` with client initialization
- [ ] Implement health check that verifies API connectivity
- [ ] Handle authentication errors with specific error messages
- [ ] Log client initialization (without exposing API key)
- [ ] Type hints for all configuration classes
- [ ] Unit tests for config validation

**Edge Cases:**
- Missing API key → Raise `ValueError` with setup instructions
- Invalid API key → Return 401 with "Invalid GEMINI_API_KEY" message
- Network connectivity issues → Return 503 with retry suggestion

**Technical Implementation:**
```python
from google import genai
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    gemini_api_key: str
    model_name: str = "gemini-3-flash-preview"
    enable_hybrid_mode: bool = True  # NEW: Toggle hybrid architecture

    class Config:
        env_file = ".env"

def get_gemini_client() -> genai.Client:
    settings = Settings()
    return genai.Client(api_key=settings.gemini_api_key)
```

---

#### US-019: OpenDataLoader Integration for Local PDF Preprocessing

**Description:** As a developer, I need to integrate OpenDataLoader PDF to extract document structure, tables, and layout locally before sending to Gemini API so that I can reduce costs by 80% and improve table extraction accuracy.

**Acceptance Criteria:**
- [ ] Create `app/services/opendataloader_extractor.py` with extraction functions
- [ ] Implement `extract_pdf_structure(file_path: str) -> DocumentStructure` function
- [ ] Extract structured Markdown with semantic types (headings, paragraphs, tables, lists)
- [ ] Extract bounding boxes for all elements `[x1, y1, x2, y2]`
- [ ] Parse table structure with borders, merged cells, row/column relationships
- [ ] Handle multi-column layouts using XY-Cut++ algorithm
- [ ] Filter headers, footers, watermarks automatically
- [ ] Export tables as structured data (list of dicts)
- [ ] Calculate quality score (completeness, element coverage)
- [ ] Handle errors gracefully (corrupted PDFs, unsupported formats)
- [ ] Type hints for all functions
- [ ] Unit tests with sample academic PDFs

**Technical Implementation:**
```python
from opendataloader_pdf import DocumentLoader
from typing import List, Dict, Tuple

class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float
    page: int

class DocumentStructure:
    markdown: str
    tables: List[Dict]
    bounding_boxes: Dict[str, BoundingBox]
    quality_score: float
    element_count: int

async def extract_pdf_structure(file_path: str) -> DocumentStructure:
    """Extract PDF structure using OpenDataLoader."""

    loader = DocumentLoader()
    doc = loader.load(file_path)

    # Extract structured content
    markdown = doc.export_to_markdown()
    tables = []

    # Parse tables with structure
    for table_elem in doc.get_tables():
        tables.append({
            "caption": table_elem.caption,
            "page": table_elem.page,
            "data": table_elem.to_dict(),
            "bbox": [table_elem.bbox.x1, table_elem.bbox.y1,
                     table_elem.bbox.x2, table_elem.bbox.y2]
        })

    # Extract bounding boxes for all elements
    bounding_boxes = {}
    for elem in doc.elements:
        bounding_boxes[elem.id] = BoundingBox(
            x1=elem.bbox.x1,
            y1=elem.bbox.y1,
            x2=elem.bbox.x2,
            y2=elem.bbox.y2,
            page=elem.page
        )

    # Calculate quality score
    quality_score = calculate_quality_score(doc)

    return DocumentStructure(
        markdown=markdown,
        tables=tables,
        bounding_boxes=bounding_boxes,
        quality_score=quality_score,
        element_count=len(doc.elements)
    )

def calculate_quality_score(doc) -> float:
    """Calculate extraction quality (0.0 to 1.0)."""
    # Check for completeness indicators
    has_text = len(doc.get_text()) > 100
    has_structure = len(doc.elements) > 10
    has_headings = any(e.type == "heading" for e in doc.elements)

    score = 0.0
    if has_text: score += 0.4
    if has_structure: score += 0.3
    if has_headings: score += 0.3

    return score
```

**Edge Cases:**
- PDF with no text (scanned images) → Return low quality_score, trigger Vision fallback
- Malformed PDF → Catch parsing errors, return error with details
- Multi-column layout → XY-Cut++ handles automatically, verify reading order
- Tables as images → OpenDataLoader may miss these, flag for Gemini Vision processing
- Very large PDFs (500+ pages) → Process in chunks if memory issues

---

#### US-003: Hybrid PDF Extraction Service with Structured Output

**Description:** As a developer, I need a hybrid PDF extraction function that uses OpenDataLoader for structure + Gemini for semantic analysis to extract complete academic data with optimal cost and accuracy.

**Acceptance Criteria:**
- [ ] Create `app/services/pdf_extractor.py` with async hybrid extraction function
- [ ] Define Pydantic models in `app/models/extraction.py`:
  - `ExtractedMetadata` (title, authors, journal, year, doi)
  - `ExtractedSection` (heading, content, page_number, bbox)
  - `ExtractedFigure` (caption, page_number, description, bbox)
  - `ExtractedTable` (caption, page_number, data, bbox) - from OpenDataLoader
  - `ExtractedReference` (citation_text, authors, year, title)
  - `ExtractionResult` (metadata, abstract, sections, figures, tables, references, confidence_score, bounding_boxes)
- [ ] Implement hybrid pipeline:
  1. Extract structure with OpenDataLoader
  2. Check quality score
  3. If quality >= 0.7: send Markdown to Gemini
  4. If quality < 0.7: fallback to full Gemini Vision
  5. Merge structured tables from OpenDataLoader with semantic data from Gemini
- [ ] Use Gemini's structured output (`response_schema` with Pydantic model)
- [ ] Return confidence score for extraction quality
- [ ] Store bounding box coordinates for all elements
- [ ] Type hints for all functions
- [ ] Unit tests with sample academic PDFs

**Technical Implementation:**
```python
from google import genai
from google.genai import types
from app.models.extraction import ExtractionResult
from app.services.opendataloader_extractor import extract_pdf_structure

async def extract_pdf_data_hybrid(
    client: genai.Client,
    file_path: str,
    model: str = "gemini-3-flash-preview"
) -> ExtractionResult:
    """Extract structured data using hybrid approach."""

    # Step 1: Local extraction with OpenDataLoader
    structure = await extract_pdf_structure(file_path)

    # Step 2: Quality-based routing
    if structure.quality_score < 0.7:
        # Fallback: Use full Gemini Vision for low-quality PDFs
        return await extract_with_vision_fallback(client, file_path, model)

    # Step 3: Send structured Markdown to Gemini (80% cost savings)
    prompt = f"""Analyze this pre-extracted academic paper structure and extract:

**Markdown Content:**
{structure.markdown}

**Tables Found:** {len(structure.tables)} tables with structured data already extracted

Extract the following with high precision:
1. Metadata: Title, authors (with affiliations), journal, year, DOI
2. Abstract: Full text summary
3. Section classification: Label each section (Introduction, Methods, Results, Discussion, Conclusion)
4. Key findings: Summarize main results from each section
5. References: Parse citations with author names, year, title

Return structured JSON conforming to ExtractionResult schema.
"""

    response = client.models.generate_content(
        model=model,
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            response_schema=ExtractionResult
        )
    )

    # Step 4: Merge structured tables from OpenDataLoader with Gemini semantics
    result = response.parsed
    result.tables = structure.tables  # Use deterministic table extraction
    result.bounding_boxes = structure.bounding_boxes  # Add coordinates
    result.processing_metadata = {
        "method": "hybrid",
        "opendataloader_quality": structure.quality_score,
        "element_count": structure.element_count,
        "cost_savings_percent": 80
    }

    return result

async def extract_with_vision_fallback(
    client: genai.Client,
    file_path: str,
    model: str
) -> ExtractionResult:
    """Fallback to full Gemini Vision for low-quality structure extraction."""

    uploaded_file = client.files.upload(file=file_path)

    try:
        response = client.models.generate_content(
            model=model,
            contents=[
                uploaded_file,
                "Extract structured academic data from this PDF including metadata, abstract, sections, tables, figures, and citations."
            ],
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
                response_schema=ExtractionResult
            )
        )

        result = response.parsed
        result.processing_metadata = {
            "method": "vision_fallback",
            "reason": "Low OpenDataLoader quality score"
        }
        return result

    finally:
        client.files.delete(name=uploaded_file.name)
```

**Edge Cases:**
- OpenDataLoader fails to parse → Immediate fallback to Gemini Vision
- Mixed quality (good structure, poor table extraction) → Use hybrid with Vision for tables only
- Scanned PDF (no extractable text) → Gemini Vision handles OCR
- Multi-column scientific paper → OpenDataLoader XY-Cut++ handles reading order
- Tables as images → Gemini Vision processes these separately

---

#### US-020: Bounding Box Storage and Citation Features

**Description:** As a researcher, I need bounding box coordinates stored for every extracted element so that I can click "View in PDF" and see the exact source location highlighted in the original document.

**Acceptance Criteria:**
- [ ] Extend `app/models/extraction.py` to include bounding boxes:
  - `BoundingBox(x1, y1, x2, y2, page, element_type)`
- [ ] Store bounding boxes in database (new JSONB column)
- [ ] Create endpoint `GET /extractions/{id}/element/{element_id}/bbox`
- [ ] Return bounding box coordinates for specific element
- [ ] Create endpoint `GET /extractions/{id}/highlight` (returns PDF with annotations)
- [ ] Implement PDF annotation service using bounding boxes
- [ ] Add "source_location" field to all extracted elements
- [ ] Type hints for all bounding box functions
- [ ] Unit tests for bounding box storage/retrieval

**API Response Example:**
```json
{
  "extraction_id": "uuid-v4",
  "element_id": "section_1_paragraph_3",
  "element_type": "paragraph",
  "content": "Our results demonstrate...",
  "bounding_box": {
    "x1": 72.0,
    "y1": 234.5,
    "x2": 523.2,
    "y2": 278.9,
    "page": 3
  }
}
```

**Future Feature Enablement:**
- Interactive PDF viewer with click-to-highlight
- Quality validation: visual diff between extracted and rendered
- Citation verification: link claims back to source paragraphs
- RAG integration: chunk-level provenance

**Edge Cases:**
- Element spans multiple pages → Store array of bounding boxes
- Bounding box outside page bounds → Validate and clip to page dimensions
- Missing bounding box (Vision fallback mode) → Return null, flag as unavailable

---

#### US-021: Intelligent Pipeline Routing and Quality Scoring

**Description:** As a system administrator, I need intelligent routing between OpenDataLoader and Gemini Vision based on quality metrics so that the system optimizes for cost and accuracy automatically.

**Acceptance Criteria:**
- [ ] Implement quality scoring in `app/services/quality_scorer.py`
- [ ] Score based on:
  - Text extraction completeness (has substantial text)
  - Structure detection (headings, sections found)
  - Table parsing success (tables have >3 rows)
  - Multi-column detection (columns properly ordered)
- [ ] Quality thresholds:
  - >= 0.9: OpenDataLoader only (cost: $0)
  - 0.7-0.89: Hybrid (OpenDataLoader + Gemini Markdown) (cost: 80% reduction)
  - < 0.7: Gemini Vision fallback (cost: standard)
- [ ] Log routing decisions with quality score and reason
- [ ] Add quality score to extraction result
- [ ] Create endpoint `GET /stats/routing` showing distribution
- [ ] Unit tests for quality scoring logic

**Quality Scoring Algorithm:**
```python
def calculate_quality_score(structure: DocumentStructure) -> float:
    """Calculate extraction quality (0.0 to 1.0)."""
    score = 0.0

    # Text completeness (40%)
    text_length = len(structure.markdown)
    if text_length > 1000:
        score += 0.4
    elif text_length > 500:
        score += 0.3
    elif text_length > 100:
        score += 0.2

    # Structure detection (30%)
    if structure.element_count > 50:
        score += 0.3
    elif structure.element_count > 20:
        score += 0.2
    elif structure.element_count > 5:
        score += 0.1

    # Heading hierarchy (15%)
    heading_count = sum(1 for e in structure.elements if e.type == "heading")
    if heading_count >= 5:
        score += 0.15
    elif heading_count >= 3:
        score += 0.1
    elif heading_count >= 1:
        score += 0.05

    # Table extraction (15%)
    if len(structure.tables) > 0:
        valid_tables = [t for t in structure.tables if len(t.get('data', [])) > 3]
        if len(valid_tables) == len(structure.tables):
            score += 0.15
        elif len(valid_tables) > 0:
            score += 0.10

    return min(score, 1.0)
```

**Edge Cases:**
- Borderline quality (0.69-0.71) → Add hysteresis, prefer hybrid if previous similar PDFs succeeded
- All PDFs routing to Vision → Alert if >50% fallback rate, investigate OpenDataLoader issues
- Quality score inflation → Manual spot-checks to validate scoring accuracy

---

#### US-004: File Upload Validation and Size Handling

**Description:** As a system administrator, I need the service to validate uploaded PDFs (file type, size, integrity) and automatically route large files (>20MB) to the File API so that the system handles all file sizes reliably and prevents malicious uploads.

**Acceptance Criteria:**
- [ ] Validate file MIME type is `application/pdf`
- [ ] Reject files with dangerous extensions or invalid magic bytes
- [ ] Set maximum file size limit (200MB) to prevent DoS attacks
- [ ] Automatically use File API for files >20MB when using Gemini Vision fallback
- [ ] Validate PDF integrity (can be opened by OpenDataLoader)
- [ ] Sanitize uploaded filenames (prevent path traversal)
- [ ] Log upload attempts with file size and validation result
- [ ] Return clear error messages for invalid uploads
- [ ] Rate limit upload endpoint (10 requests/minute per IP)
- [ ] Unit tests for all validation scenarios

**Edge Cases:**
- File renamed from `.exe` to `.pdf` → Validate magic bytes, reject if not valid PDF
- Empty PDF (0 bytes) → Return 400 error with "Empty file uploaded"
- Corrupted PDF → OpenDataLoader will fail, catch and return 422 with "Corrupted or invalid PDF"
- Very large file (500MB) → Return 413 with "File exceeds 200MB limit"
- Simultaneous uploads from same IP → Rate limit, return 429 with retry-after header
- Path traversal attempt (`../../../etc/passwd.pdf`) → Sanitize, reject with 400

---

### Phase 2: FastAPI Service & REST API

#### US-005: FastAPI Application with Health Check

**Description:** As a DevOps engineer, I need a FastAPI application with a health check endpoint that verifies Gemini API connectivity, OpenDataLoader availability, and database connection so that I can monitor service health in production.

**Acceptance Criteria:**
- [ ] Create `app/main.py` with FastAPI app initialization
- [ ] Add `/health` endpoint (GET) that returns:
  - Service status
  - OpenDataLoader status (can load test PDF)
  - Gemini API connectivity status
  - Supabase connection status
  - Timestamp
- [ ] Configure CORS middleware for frontend integration
- [ ] Add request logging middleware
- [ ] Enable Swagger UI at `/docs`
- [ ] Add version endpoint (`/version`) with commit hash
- [ ] Return 200 if all dependencies healthy, 503 if any fail
- [ ] Type hints for all route handlers
- [ ] Integration tests for health endpoint

**Health Check Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-28T10:30:00Z",
  "services": {
    "opendataloader": {
      "status": "healthy",
      "version": "1.0.0",
      "test_extraction_time_ms": 45
    },
    "gemini_api": {
      "status": "healthy",
      "connectivity": "ok"
    },
    "supabase": {
      "status": "healthy",
      "latency_ms": 23
    }
  }
}
```

**Edge Cases:**
- OpenDataLoader import fails → Return 503 with "OpenDataLoader unavailable - check installation"
- Gemini API unreachable → Return 503 with "Gemini API unavailable"
- Supabase unreachable → Return 503 with "Database unavailable"
- Partial failure → Return 503 with list of failed services

---

#### US-006: PDF Upload and Extraction Endpoint

**Description:** As an API consumer, I need a POST endpoint to upload a PDF and receive extracted structured data (with bounding boxes) so that I can integrate PDF extraction into my application workflow.

**Acceptance Criteria:**
- [ ] Create `POST /extract` endpoint accepting multipart/form-data
- [ ] Accept `file` parameter (PDF upload)
- [ ] Optional `webhook_url` parameter for async notification
- [ ] Optional `force_vision` parameter to skip OpenDataLoader (default: false)
- [ ] Validate file using US-004 validation logic
- [ ] Call hybrid extraction service (US-003)
- [ ] Return extraction result as JSON with 201 status
- [ ] Store result in Supabase (auto-generated ID)
- [ ] Return extraction ID in response headers (`X-Extraction-ID`)
- [ ] Add request timeout (60 seconds for large files)
- [ ] Comprehensive error handling with specific error codes
- [ ] OpenAPI schema documentation
- [ ] Integration tests with sample PDFs

**Response Schema:**
```json
{
  "extraction_id": "uuid-v4",
  "status": "completed",
  "processing_metadata": {
    "method": "hybrid",
    "opendataloader_quality": 0.92,
    "cost_savings_percent": 80,
    "processing_time_seconds": 8.3
  },
  "metadata": {
    "title": "Deep Learning for Computer Vision",
    "authors": [
      {"name": "Jane Doe", "affiliation": "MIT CSAIL"},
      {"name": "John Smith", "affiliation": "Stanford AI Lab"}
    ],
    "journal": "Nature Machine Intelligence",
    "year": 2024,
    "doi": "10.1038/s42256-024-00123-4"
  },
  "abstract": "This paper presents...",
  "sections": [
    {
      "heading": "Introduction",
      "content": "...",
      "page_number": 1,
      "bbox": {"x1": 72, "y1": 180, "x2": 523, "y2": 420, "page": 1}
    }
  ],
  "tables": [
    {
      "caption": "Model Performance Comparison",
      "page_number": 5,
      "data": [[{"cell": "Model", "row": 0, "col": 0}, ...]],
      "bbox": {"x1": 72, "y1": 200, "x2": 523, "y2": 450, "page": 5}
    }
  ],
  "figures": [...],
  "references": [...],
  "confidence_score": 0.96,
  "bounding_boxes_count": 247,
  "created_at": "2026-01-28T10:30:00Z"
}
```

**Edge Cases:**
- Extraction timeout (>60s) → Return 202 with extraction ID, continue processing async
- OpenDataLoader fails → Automatic fallback to Gemini Vision, log routing decision
- Webhook URL provided → Process async, send result to webhook when complete
- Duplicate upload (same PDF hash) → Return cached result if available (within 7 days)
- `force_vision=true` → Skip OpenDataLoader, use Gemini Vision directly

---

#### US-007: Extraction Retrieval Endpoint with Bounding Box Access

**Description:** As an API consumer, I need a GET endpoint to retrieve extraction results by ID with bounding box data so that I can fetch results asynchronously and enable citation features.

**Acceptance Criteria:**
- [ ] Create `GET /extractions/{extraction_id}` endpoint
- [ ] Validate UUID format of extraction_id
- [ ] Query Supabase for extraction record
- [ ] Return extraction result with same schema as POST response
- [ ] Include bounding boxes in response
- [ ] Return 404 if extraction_id not found
- [ ] Include processing status (`pending`, `completed`, `failed`, `partial`)
- [ ] Cache responses for 5 minutes (in-memory or Redis)
- [ ] Add pagination for list endpoint (`GET /extractions`)
- [ ] Filter by date range, status, processing method (hybrid vs vision)
- [ ] Type hints for query parameters
- [ ] Integration tests for all scenarios

**Additional Endpoints:**
- [ ] `GET /extractions/{id}/bounding-boxes` - Return all bounding boxes
- [ ] `GET /extractions/{id}/elements/{element_id}` - Return specific element with bbox

**Edge Cases:**
- Invalid UUID format → Return 400 with "Invalid extraction ID format"
- Extraction still processing → Return 202 with status "pending"
- Extraction failed → Return 200 with status "failed" and error details
- Deleted extraction → Return 404 with "Extraction not found or deleted"
- No bounding boxes (Vision fallback) → Return warning in response

---

### Phase 3: Supabase Integration & Data Persistence

#### US-008: Supabase Client Configuration

**Description:** As a developer, I need a configured Supabase client that handles connection pooling, authentication, and error handling so that database operations are reliable and secure.

**Acceptance Criteria:**
- [ ] Create `app/db/supabase_client.py` with client initialization
- [ ] Load Supabase credentials from environment variables
- [ ] Implement connection health check
- [ ] Handle authentication errors gracefully
- [ ] Configure connection timeout (10 seconds)
- [ ] Add retry logic for transient failures (3 retries, exponential backoff)
- [ ] Log database operations (without exposing sensitive data)
- [ ] Type hints for all database functions
- [ ] Unit tests with mocked Supabase client

**Edge Cases:**
- Invalid Supabase URL → Raise `ValueError` with setup instructions
- Invalid API key → Return 401 from health check
- Network timeout → Retry 3 times, then raise `TimeoutError`
- Connection pool exhausted → Log warning, queue request

---

#### US-009: Database Schema for Extractions with Bounding Boxes

**Description:** As a database administrator, I need a well-designed schema for storing extraction results with bounding box coordinates and proper indexing so that queries are fast and citation features are enabled.

**Acceptance Criteria:**
- [ ] Create `extractions` table with schema:
  - `id` (UUID, primary key)
  - `file_name` (text, not null)
  - `file_size_bytes` (bigint)
  - `file_hash` (text, unique index for deduplication)
  - `status` (enum: pending, completed, failed, partial)
  - `processing_method` (enum: hybrid, vision_fallback, opendataloader_only) **NEW**
  - `quality_score` (decimal) **NEW: OpenDataLoader quality**
  - `metadata` (jsonb)
  - `abstract` (text)
  - `sections` (jsonb)
  - `figures` (jsonb)
  - `tables` (jsonb)
  - `references` (jsonb)
  - `bounding_boxes` (jsonb) **NEW: Coordinates for all elements**
  - `confidence_score` (decimal)
  - `error_message` (text, nullable)
  - `processing_time_seconds` (decimal)
  - `cost_estimate_usd` (decimal) **NEW: Track cost savings**
  - `created_at` (timestamp with timezone, default now())
  - `updated_at` (timestamp with timezone)
  - `webhook_url` (text, nullable)
  - `retry_count` (integer, default 0)
- [ ] Create index on `created_at` for date range queries
- [ ] Create index on `status` for filtering
- [ ] Create index on `file_hash` for deduplication
- [ ] Create index on `processing_method` for analytics **NEW**
- [ ] Add RLS (Row Level Security) policies if multi-tenant
- [ ] Document schema in migration file
- [ ] Create migration script using Supabase CLI

**Bounding Boxes JSONB Structure:**
```json
{
  "section_1_heading": {
    "x1": 72.0, "y1": 180.0, "x2": 523.2, "y2": 210.5,
    "page": 1, "element_type": "heading"
  },
  "section_1_paragraph_1": {
    "x1": 72.0, "y1": 220.0, "x2": 523.2, "y2": 280.0,
    "page": 1, "element_type": "paragraph"
  },
  "table_1": {
    "x1": 72.0, "y1": 300.0, "x2": 523.2, "y2": 500.0,
    "page": 3, "element_type": "table"
  }
}
```

**Technical Notes:**
- Use JSONB for flexible nested data (sections, figures, etc.)
- Store file_hash (SHA-256) for detecting duplicate uploads
- Bounding boxes indexed by element ID for fast lookups
- Timestamp columns for audit trail

---

#### US-010: Data Storage and Retrieval Functions

**Description:** As a developer, I need typed database functions to insert and query extraction results with bounding boxes so that I can reliably persist and retrieve data with proper error handling.

**Acceptance Criteria:**
- [ ] Create `app/db/extractions.py` with async functions:
  - `create_extraction(data: ExtractionResult) -> str` (returns UUID)
  - `get_extraction(extraction_id: str) -> Optional[ExtractionResult]`
  - `update_extraction_status(extraction_id: str, status: str, error: Optional[str]) -> None`
  - `list_extractions(limit: int, offset: int, status: Optional[str]) -> List[ExtractionResult]`
  - `check_duplicate(file_hash: str) -> Optional[str]` (returns existing extraction_id)
  - `get_bounding_boxes(extraction_id: str) -> Dict[str, BoundingBox]` **NEW**
  - `get_element_bbox(extraction_id: str, element_id: str) -> Optional[BoundingBox]` **NEW**
- [ ] All functions have full type hints
- [ ] Handle unique constraint violations (duplicate hash)
- [ ] Return None for not found (don't raise exception)
- [ ] Log all database operations
- [ ] Unit tests with mocked Supabase responses
- [ ] Integration tests with test Supabase instance

**Edge Cases:**
- Duplicate file_hash → Return existing extraction_id from `check_duplicate`
- Malformed UUID → Raise `ValueError` with clear message
- Database connection lost mid-operation → Retry with exponential backoff
- JSONB serialization error → Log error, raise `ValueError` with field name
- Concurrent updates to same record → Use optimistic locking with `updated_at`
- Missing bounding boxes (Vision fallback) → Store empty dict, log warning

---

### Phase 4: Advanced Features (Batch Processing, Retry, Webhooks)

#### US-011: Batch Processing with Hybrid Pipeline

**Description:** As a researcher, I need to upload multiple PDFs for batch processing using the hybrid pipeline so that I can extract data from 100+ papers overnight with 80% cost savings vs pure AI batch processing.

**Acceptance Criteria:**
- [ ] Create `POST /batch` endpoint accepting multiple files or file URLs
- [ ] Accept up to 100 PDFs per batch job
- [ ] Generate batch job ID (UUID)
- [ ] Process each PDF through hybrid pipeline (OpenDataLoader + Gemini)
- [ ] Store batch job metadata in new `batch_jobs` table
- [ ] Return batch job ID and status URL immediately (202 Accepted)
- [ ] Implement polling endpoint `GET /batch/{job_id}` for status
- [ ] Store individual extraction results in `extractions` table
- [ ] Track per-file routing decisions (hybrid vs fallback)
- [ ] Send webhook notification when batch completes (if provided)
- [ ] Handle partial batch failures gracefully
- [ ] Calculate total cost savings vs pure Vision approach
- [ ] Unit tests for batch creation
- [ ] Integration tests with small batch (3-5 files)

**Batch Response Schema:**
```json
{
  "batch_job_id": "uuid-v4",
  "status": "processing",
  "total_files": 50,
  "completed_files": 23,
  "failed_files": 1,
  "routing_stats": {
    "hybrid": 20,
    "vision_fallback": 3,
    "pending": 27
  },
  "created_at": "2026-01-28T10:30:00Z",
  "estimated_completion": "2026-01-28T12:00:00Z",
  "cost_estimate_usd": 0.12,
  "cost_savings_vs_pure_vision_usd": 0.48,
  "cost_savings_percent": 80,
  "extraction_ids": ["uuid1", "uuid2", ...]
}
```

**Edge Cases:**
- >100 files uploaded → Return 400 with "Maximum 100 files per batch"
- Mixed valid/invalid PDFs → Process valid files, report invalid files in response
- All files route to Vision fallback → Log warning, investigate quality issues
- Batch processing timeout → Mark as partial completion, store completed results
- Individual file fails → Store error for that file, continue processing others

---

#### US-012: Automatic Retry with Exponential Backoff

**Description:** As a system administrator, I need the service to automatically retry failed API requests with exponential backoff so that transient errors (rate limits, timeouts) don't require manual intervention.

**Acceptance Criteria:**
- [ ] Implement retry decorator in `app/utils/retry.py`
- [ ] Retry on specific errors:
  - `429 Too Many Requests` (rate limit)
  - `503 Service Unavailable`
  - `500 Internal Server Error`
  - Network timeouts
- [ ] Do NOT retry on:
  - `400 Bad Request` (client error)
  - `401 Unauthorized` (auth error)
  - `404 Not Found`
- [ ] Exponential backoff: 1s, 2s, 4s, 8s, 16s (max 5 retries)
- [ ] Add jitter (random 0-1s) to prevent thundering herd
- [ ] Log each retry attempt with attempt number and delay
- [ ] Update `retry_count` field in database
- [ ] Return original error after max retries exhausted
- [ ] Unit tests for all retry scenarios
- [ ] Integration tests with mocked API failures

**Edge Cases:**
- OpenDataLoader fails → Immediate fallback to Vision (no retry)
- Gemini API rate limit → Respect `retry-after` header if present
- Intermittent network errors → Retry succeeds on 2nd attempt, log recovery
- Persistent 500 error → Exhaust retries, mark extraction as failed, queue for review
- Retry during batch processing → Individual file retries don't block other files

---

#### US-013: Partial Result Storage

**Description:** As a researcher, I need the system to save partial extraction results when processing fails partway through so that I don't lose data from successfully processed sections (especially OpenDataLoader structure extraction).

**Acceptance Criteria:**
- [ ] Detect partial responses from Gemini API
- [ ] Store partial data with status="partial"
- [ ] Set `error_message` field with failure reason
- [ ] Always save OpenDataLoader structure even if Gemini fails
- [ ] Flag which fields are missing in response
- [ ] Allow re-processing of partial extractions via `POST /extractions/{id}/retry`
- [ ] Merge new data with existing partial data on retry
- [ ] Log partial save events for monitoring
- [ ] Include partial status in API responses
- [ ] Unit tests for partial data scenarios

**Edge Cases:**
- OpenDataLoader succeeds, Gemini fails → Store structure + tables, mark as partial
- Only metadata extracted, no sections → Store metadata, mark sections as null
- Extraction stops mid-section → Store completed sections, flag incomplete one
- Retry completes missing data → Merge with partial, update status to "completed"
- Multiple retries all partial → Keep latest partial data, increment retry_count

---

#### US-014: Manual Review Queue

**Description:** As a data quality manager, I need extractions that fail after retries to be queued for manual review with clear error context so that I can investigate and fix edge cases.

**Acceptance Criteria:**
- [ ] Create `review_queue` table:
  - `id` (UUID, primary key)
  - `extraction_id` (UUID, foreign key)
  - `error_type` (text)
  - `error_message` (text)
  - `processing_method` (enum: hybrid, vision_fallback) **NEW**
  - `quality_score` (decimal, nullable) **NEW**
  - `retry_count` (integer)
  - `queued_at` (timestamp)
  - `reviewed_at` (timestamp, nullable)
  - `reviewer_notes` (text, nullable)
  - `resolution` (enum: fixed, false_positive, unable_to_process)
- [ ] Automatically queue extractions when retry_count > 5
- [ ] Create `GET /review-queue` endpoint for admins
- [ ] Create `POST /review-queue/{id}/resolve` endpoint
- [ ] Allow manual re-processing from review queue
- [ ] Log queue additions for alerting
- [ ] Dashboard query to count queued items by processing method
- [ ] Unit tests for queue logic

**Edge Cases:**
- Extraction eventually succeeds on manual retry → Remove from queue, update status
- Recurring error pattern (e.g., all scanned PDFs) → Flag for developer investigation
- Queue grows >100 items → Send alert to operations team
- High Vision fallback rate → Investigate OpenDataLoader configuration

---

#### US-015: Webhook Notifications

**Description:** As an API consumer, I need the service to POST extraction results to my webhook URL when processing completes so that I can integrate asynchronously without polling.

**Acceptance Criteria:**
- [ ] Accept `webhook_url` parameter in `POST /extract` and `POST /batch`
- [ ] Validate webhook_url is HTTPS (security requirement)
- [ ] Send POST request to webhook_url when extraction completes
- [ ] Include full extraction result in webhook payload
- [ ] Include processing metadata (method, quality_score, cost_savings)
- [ ] Add signature header (`X-Webhook-Signature`) using HMAC-SHA256
- [ ] Retry webhook delivery on failure (3 retries, exponential backoff)
- [ ] Log webhook delivery attempts and responses
- [ ] Mark webhook as failed after 3 failed attempts
- [ ] Create `GET /webhooks/failed` endpoint to list failed deliveries
- [ ] Allow webhook retry via `POST /webhooks/{id}/retry`
- [ ] Unit tests for webhook delivery
- [ ] Integration tests with mock webhook server

**Webhook Payload:**
```json
{
  "event": "extraction.completed",
  "extraction_id": "uuid-v4",
  "status": "completed",
  "processing_metadata": {
    "method": "hybrid",
    "quality_score": 0.92,
    "cost_savings_percent": 80,
    "processing_time_seconds": 8.3
  },
  "data": { /* full ExtractionResult with bounding boxes */ },
  "timestamp": "2026-01-28T10:30:00Z"
}
```

**Edge Cases:**
- Webhook URL unreachable → Retry 3 times, then mark as failed, log error
- Webhook returns 4xx (client error) → Don't retry, log as permanent failure
- Webhook returns 5xx (server error) → Retry with backoff
- HTTP webhook (not HTTPS) → Reject with 400 error in upload request
- Webhook takes >30s to respond → Timeout, retry later
- Circular webhook (webhook triggers new extraction) → Detect and break loop

---

### Phase 5: Performance & Monitoring

#### US-016: Context Caching for Repeated Prompts

**Description:** As a cost-conscious operator, I need the service to use Gemini's context caching for repeated extraction prompts (used in hybrid mode) so that I can reduce API costs by up to 90% on similar documents.

**Acceptance Criteria:**
- [ ] Implement context caching for hybrid extraction prompts
- [ ] Cache system instructions for academic PDF analysis
- [ ] Set cache TTL to 1 hour
- [ ] Reuse cached context for all hybrid extractions
- [ ] Log cache hits/misses for monitoring
- [ ] Track cost savings in database (new column)
- [ ] Add cache statistics to `GET /stats` endpoint
- [ ] Calculate combined savings: 80% (hybrid) + 90% (caching) = ~98% total
- [ ] Unit tests for cache logic

**Technical Notes:**
- Cache the system instruction: "Analyze this pre-extracted academic paper structure..."
- Each request uses cached context + unique Markdown content
- Gemini charges reduced rate for cached tokens
- Combined with hybrid approach: massive cost reduction

**Cost Comparison:**
- Pure Vision: $0.011 per 100-page PDF
- Hybrid (no caching): $0.002 per PDF (80% reduction)
- Hybrid + Caching: $0.0002 per PDF (98% reduction!)

---

#### US-017: Rate Limiting and Quota Management

**Description:** As a system administrator, I need rate limiting on all API endpoints to prevent abuse and quota exhaustion so that the service remains available for legitimate users.

**Acceptance Criteria:**
- [ ] Implement rate limiting middleware using token bucket algorithm
- [ ] Limits per endpoint:
  - `POST /extract`: 10 requests/minute per IP
  - `POST /batch`: 2 requests/minute per IP
  - `GET /extractions`: 100 requests/minute per IP
- [ ] Return 429 status with `retry-after` header when limit exceeded
- [ ] Track quota usage in Redis (if available) or in-memory
- [ ] Add `X-RateLimit-Remaining` header to responses
- [ ] Log rate limit violations for security monitoring
- [ ] Allow bypass for authenticated admin users
- [ ] Unit tests for rate limiting

**Edge Cases:**
- Distributed deployment (multiple servers) → Use Redis for shared rate limit state
- Legitimate user hits limit during burst → Provide clear error message with retry time
- Malicious actor → Log IP, consider auto-blocking after repeated violations

---

#### US-018: Logging and Metrics

**Description:** As a DevOps engineer, I need structured logging and metrics collection for all operations (including routing decisions) so that I can monitor performance, debug issues, and track cost savings.

**Acceptance Criteria:**
- [ ] Configure structured logging (JSON format) with:
  - Timestamp
  - Log level
  - Request ID (correlation)
  - Endpoint
  - Status code
  - Processing time
  - Processing method (hybrid/vision_fallback)
  - Quality score
  - Cost estimate
  - User IP
  - Error details (if applicable)
- [ ] Log all API requests and responses
- [ ] Log routing decisions with quality score and reasoning
- [ ] Log Gemini API calls (duration, tokens used, cost estimate)
- [ ] Log OpenDataLoader processing time
- [ ] Log database operations (query time)
- [ ] Never log sensitive data (API keys, file contents)
- [ ] Add request ID to all log entries for tracing
- [ ] Create `/metrics` endpoint for Prometheus scraping
- [ ] Track metrics:
  - Request count by endpoint
  - Error rate by error type
  - Processing time (p50, p95, p99)
  - Routing distribution (hybrid vs vision)
  - Quality score distribution
  - Cost savings (actual vs pure Vision baseline)
  - Queue depth (pending extractions)
- [ ] Create `/stats/routing` endpoint with dashboard data
- [ ] Unit tests for logging middleware

**Stats Endpoint Response:**
```json
{
  "total_extractions": 1543,
  "routing_distribution": {
    "hybrid": 1234,
    "vision_fallback": 309
  },
  "average_quality_score": 0.87,
  "cost_metrics": {
    "total_cost_usd": 3.45,
    "estimated_pure_vision_cost_usd": 17.85,
    "total_savings_usd": 14.40,
    "savings_percent": 80.7
  },
  "performance": {
    "avg_processing_time_seconds": 9.2,
    "p95_processing_time_seconds": 15.3
  }
}
```

---

## Functional Requirements

**Core Processing:**
- FR-1: The system MUST use OpenDataLoader for local PDF structure extraction before Gemini API
- FR-2: The system MUST extract title, authors, journal, year, and DOI from academic PDFs
- FR-3: The system MUST extract abstract and organize content into sections
- FR-4: The system MUST extract tables with F1-score >= 0.90 using OpenDataLoader
- FR-5: The system MUST identify and describe figures and their captions
- FR-6: The system MUST extract citations and references with author, year, and title
- FR-7: The system MUST handle multi-page PDFs (up to 200MB, 1000+ pages)
- FR-8: The system MUST provide bounding box coordinates for all extracted elements
- FR-9: The system MUST handle multi-column academic layouts correctly (XY-Cut++ algorithm)

**Hybrid Architecture:**
- FR-10: The system MUST calculate quality score for OpenDataLoader extraction
- FR-11: The system MUST route high-quality extractions (>= 0.7) through hybrid pipeline
- FR-12: The system MUST fallback to Gemini Vision for low-quality extractions (< 0.7)
- FR-13: The system MUST merge OpenDataLoader tables with Gemini semantic analysis
- FR-14: The system MUST achieve 80% cost reduction vs pure AI approach for hybrid extractions

**API & Integration:**
- FR-15: The system MUST provide a REST API with `/extract` (POST) and `/extractions/{id}` (GET) endpoints
- FR-16: The system MUST support batch processing via `/batch` endpoint
- FR-17: The system MUST validate uploaded files (type, size, integrity)
- FR-18: The system MUST return structured JSON conforming to defined Pydantic schemas
- FR-19: The system MUST support webhook notifications for async processing

**Reliability & Error Handling:**
- FR-20: The system MUST retry failed API requests up to 5 times with exponential backoff
- FR-21: The system MUST store partial extraction results when processing fails
- FR-22: The system MUST queue failed extractions for manual review after 5 retry attempts
- FR-23: The system MUST handle rate limits from Gemini API gracefully
- FR-24: The system MUST fallback to Gemini Vision if OpenDataLoader fails

**Data Storage:**
- FR-25: The system MUST store all extraction results in Supabase with timestamps
- FR-26: The system MUST store bounding box coordinates for all elements
- FR-27: The system MUST detect duplicate PDFs using file hashing and return cached results
- FR-28: The system MUST store processing metadata (method, quality_score, cost_estimate)

**Security:**
- FR-29: The system MUST validate all file uploads to prevent malicious content
- FR-30: The system MUST sanitize filenames to prevent path traversal attacks
- FR-31: The system MUST rate limit endpoints to prevent abuse (10/min for /extract)
- FR-32: The system MUST use HTTPS for all webhook deliveries
- FR-33: The system MUST never log API keys or file contents

**Performance:**
- FR-34: The system MUST process PDFs in under 15 seconds for 90% of hybrid extractions
- FR-35: The system MUST use context caching to reduce Gemini API costs by up to 90%
- FR-36: The system MUST achieve combined 95%+ cost reduction (hybrid + caching)

---

## Non-Goals (Out of Scope for v1.0)

- **Authentication/Authorization:** No user accounts or API keys in v1.0 (assumes internal use or gateway auth)
- **PDF Generation:** Service extracts data but doesn't create or modify PDFs
- **Custom Training:** Uses pre-trained models; no fine-tuning
- **Real-time Streaming:** Batch results are polled, not streamed via WebSockets
- **Multi-Language PDFs:** Focus on English academic papers; i18n is future enhancement
- **Advanced OCR:** Relies on OpenDataLoader + Gemini Vision for scanned PDFs
- **On-Premise Deployment:** Cloud-only for v1.0 (Gemini API requires internet)
- **Advanced Search:** No full-text search across stored extractions (use Supabase queries)
- **User Dashboard:** Admin endpoints only; no web UI
- **PDF Annotation UI:** Bounding boxes stored but no visual editor in v1.0
- **Gemini Batch API:** Hybrid approach already provides cost savings; batch API deferred to v2.0

---

## Technical Considerations

### Architecture Decisions

**Why Hybrid (OpenDataLoader + Gemini) vs Pure AI?**
- **Cost:** 80% reduction by processing structured Markdown instead of full PDF
- **Accuracy:** Deterministic table extraction (F1: 0.93) vs variable AI performance
- **Speed:** Local preprocessing (0.05s/page) + smaller Gemini payloads
- **Bounding boxes:** OpenDataLoader provides coordinates; Gemini Vision doesn't
- **No hallucinations:** Document structure is deterministic

**Quality-Based Routing Logic:**
- Quality >= 0.9: OpenDataLoader only (future optimization)
- Quality 0.7-0.89: Hybrid (OpenDataLoader + Gemini Markdown analysis)
- Quality < 0.7: Gemini Vision fallback (scanned PDFs, complex layouts)

**Why OpenDataLoader vs Other PDF Parsers?**
- Designed for RAG/LLM pipelines (optimized Markdown output)
- XY-Cut++ algorithm handles multi-column academic papers
- Bounding boxes for all elements (critical for citations)
- Tagged PDF support (accessibility compliance)
- 100% local processing (no cloud dependencies)
- High table extraction accuracy (F1: 0.93 in hybrid mode)

**Why Gemini 3 Flash for Hybrid Mode?**
- Structured output with Pydantic schemas
- Fast inference for Markdown analysis
- Cost-effective for semantic understanding
- Context caching support (90% additional savings)

**Why Supabase vs PostgreSQL directly?**
- Built-in auth for future multi-tenancy
- Real-time subscriptions for future webhook alternative
- Easy RLS (Row Level Security) for data isolation
- Free tier sufficient for MVP
- JSONB support for bounding boxes

### Dependencies

**Critical:**
- OpenDataLoader PDF (local PDF parsing) - NEW
- Google Gemini API (semantic analysis)
- Supabase (managed PostgreSQL)

**Optional:**
- Redis (for distributed rate limiting and caching)
- Prometheus + Grafana (for metrics visualization)

### Performance Targets

**Updated with Hybrid Architecture:**
- Single PDF extraction (hybrid): <15s for 90% of requests (vs 60s pure AI)
- OpenDataLoader preprocessing: <5s for 100-page PDF
- Gemini analysis (Markdown): 5-10s
- API latency (excluding processing): <200ms p95
- Database queries: <50ms p95
- Webhook delivery: <5s timeout

### Cost Analysis

**Per 100-Page Academic PDF:**
- Pure Gemini Vision: ~$0.011 (150,000 tokens @ $0.075/1M)
- Hybrid (no caching): ~$0.002 (30,000 tokens @ $0.075/1M) - **80% savings**
- Hybrid + Caching: ~$0.0002 (cached prompt + unique content) - **98% savings**

**At Scale (1000 PDFs/day):**
- Pure Vision: $11/day = $330/month
- Hybrid: $2/day = $60/month (saves $270/month)
- Hybrid + Caching: $0.20/day = $6/month (saves $324/month)

### Scalability Considerations

- FastAPI is async-first (supports high concurrency)
- OpenDataLoader is CPU-based (scales horizontally)
- Gemini API handles scaling (pay-per-use)
- Supabase scales to 100K+ rows easily
- For >1M extractions, consider partitioning `extractions` table by date
- For >100 req/s, add Redis for rate limiting and caching

---

## Security Considerations

### Threat Model

**Threats:**
1. Malicious PDF uploads (embedded exploits, path traversal)
2. DoS attacks (large files, rapid uploads)
3. API key exposure (logged, committed to git)
4. Data exfiltration (unauthorized access to extraction results)
5. Webhook abuse (SSRF, unauthorized data delivery)

**Mitigations:**
1. Validate file magic bytes, sanitize filenames, size limits
2. Rate limiting, file size caps, request timeouts
3. Environment variables only, never log keys, .gitignore .env
4. Future: Add API key auth, RLS in Supabase
5. HTTPS-only webhooks, signature verification, timeout limits

### Data Privacy

- **User Data:** Extraction results may contain academic research data (potentially sensitive)
- **Local Processing:** OpenDataLoader processes PDFs locally (no cloud transmission)
- **Retention:** Store results indefinitely unless user requests deletion
- **Compliance:** No PII expected, but consider GDPR if processing European papers
- **Encryption:** Supabase encrypts data at rest; use HTTPS for transit

### API Security

- Rate limiting on all endpoints
- Input validation for all parameters
- Webhook signature verification (HMAC-SHA256)
- CORS configuration to prevent unauthorized origins
- No sensitive data in logs or error messages

---

## Success Metrics

### Performance Metrics
- **Extraction Accuracy:** 95%+ for standard academic papers (improved via deterministic table extraction)
- **Table Extraction Accuracy:** F1-score >= 0.90 (OpenDataLoader)
- **Uptime:** 99.5% availability (excluding Gemini API outages)
- **Processing Time:** 90% of hybrid extractions under 15s
- **Error Rate:** <3% of extractions fail (after retries)

### Cost Metrics (Updated for Hybrid Architecture)
- **Hybrid Adoption Rate:** 80% of PDFs route through hybrid pipeline (quality >= 0.7)
- **Cost Reduction:** 80% average savings vs pure Vision approach
- **Cache Hit Rate:** 70% of hybrid requests use cached context
- **Combined Savings:** 95%+ total cost reduction (hybrid + caching)
- **Cost per Extraction:** <$0.001 per PDF (target: $0.0002 with caching)

### Usage Metrics
- **Throughput:** Support 1000 extractions/day by end of month 1
- **Batch Jobs:** 10+ batch jobs/week
- **Webhook Success Rate:** 95% of webhooks deliver on first attempt
- **Bounding Box Coverage:** 90%+ of extractions include bounding boxes

### Quality Metrics
- **Manual Review Queue:** <10 items in queue at any time
- **Retry Success Rate:** 80% of retries succeed on 2nd or 3rd attempt
- **Partial Results:** <5% of extractions return partial data
- **Vision Fallback Rate:** <20% of extractions fallback to pure Vision (indicates good OpenDataLoader coverage)

---

## Open Questions

1. **OpenDataLoader Hybrid Mode:** Should we enable OpenDataLoader's hybrid mode (uses docling-serve backend) for formula extraction?
   - **Recommendation:** Phase 2 - evaluate if formula extraction is critical for target academic papers

2. **Model Selection:** Should we auto-select Gemini Pro for complex papers, or always use Flash in hybrid mode?
   - **Recommendation:** Always use Flash for hybrid (structured Markdown is simple); Pro only for Vision fallback

3. **Bounding Box Precision:** What level of precision do we need for bounding boxes (integer pixels vs float)?
   - **Recommendation:** Float (matches OpenDataLoader output) for sub-pixel accuracy

4. **Deduplication:** How long should we cache duplicate detection (24h, 7d, forever)?
   - **Recommendation:** 7 days for v1.0, configurable via environment variable

5. **Failed Webhook Retention:** How long to keep failed webhook records?
   - **Recommendation:** 30 days, then auto-delete

6. **Authentication:** When to add API key authentication?
   - **Recommendation:** Phase 2 (after v1.0 MVP) when exposing to external users

7. **Monitoring:** Should we integrate with external monitoring (Sentry, Datadog)?
   - **Recommendation:** Add Sentry for error tracking in production

8. **LangChain Integration:** Should we provide LangChain document loader using our API?
   - **Recommendation:** Phase 2 - OpenDataLoader already has LangChain loader; can build custom loader for our enhanced results

---

## Implementation Phases

### Phase 1: Hybrid Pipeline MVP (Weeks 1-2)
- **US-001:** Project setup with OpenDataLoader + Gemini SDK
- **US-002:** Gemini client configuration
- **US-019:** OpenDataLoader integration
- **US-003:** Hybrid extraction pipeline
- **US-021:** Quality scoring and routing
- **US-004:** File validation
- **US-005:** FastAPI app with health check
- **US-006:** Upload and extraction endpoint
- **US-007:** Retrieval endpoint

**Deliverable:** Working API with hybrid extraction (OpenDataLoader + Gemini)

### Phase 2: Data Persistence & Bounding Boxes (Week 2-3)
- **US-008:** Supabase client configuration
- **US-009:** Database schema with bounding boxes
- **US-010:** Data storage and retrieval functions
- **US-020:** Bounding box API endpoints

**Deliverable:** Complete data persistence with citation features

### Phase 3: Reliability & Error Handling (Week 3)
- **US-012:** Retry logic
- **US-013:** Partial result storage
- **US-014:** Manual review queue
- **US-017:** Rate limiting
- **US-018:** Logging and metrics with routing analytics

**Deliverable:** Production-ready service with error handling and observability

### Phase 4: Advanced Features (Week 4)
- **US-011:** Batch processing with hybrid pipeline
- **US-015:** Webhook notifications
- **US-016:** Context caching for 90% additional savings

**Deliverable:** Full-featured service with batch processing and cost optimization

### Phase 5: Testing, Documentation & Deployment (Week 5)
- Complete testing (unit + integration)
- Performance benchmarking (hybrid vs pure Vision)
- Cost analysis validation
- Documentation (API docs, deployment guide, architecture diagrams)
- Production deployment with monitoring

**Deliverable:** Live service with comprehensive documentation

---

## Testing Strategy

### Unit Tests
- OpenDataLoader integration (structure extraction, quality scoring)
- Hybrid routing logic (quality thresholds, fallback triggers)
- Gemini API calls (Markdown analysis, structured output)
- Bounding box storage and retrieval
- Database functions (create, read, update with bounding boxes)
- Pydantic model validation
- Utility functions (hashing, retry decorator)

### Integration Tests
- Full hybrid flow: upload → OpenDataLoader → Gemini → store → retrieve
- Vision fallback flow: upload → quality check → Vision API → store
- Batch processing with mixed quality PDFs
- Bounding box API endpoints
- Webhook delivery with processing metadata
- Error scenarios (OpenDataLoader failures, API failures, invalid files)

### Test Data
- Sample academic PDFs (10-15 papers from open access sources)
  - High-quality text PDFs (should route hybrid)
  - Scanned PDFs (should route Vision fallback)
  - Multi-column papers (test XY-Cut++ algorithm)
  - Papers with complex tables (validate F1 >= 0.90)
  - Edge cases: malformed PDFs, huge files
- Mock Gemini API responses for deterministic testing
- Mock OpenDataLoader responses for failure scenarios

### Performance Testing
- Benchmark OpenDataLoader processing time (target: 0.05s/page)
- Benchmark hybrid vs pure Vision processing time
- Validate cost savings (80% reduction)
- Simulate 100 concurrent uploads
- Batch job with 50 PDFs
- Verify rate limiting under load

### Quality Validation
- Manual spot-check of 20 extractions for accuracy
- Validate table extraction F1-score >= 0.90
- Verify bounding box coordinates match PDF elements
- Test quality scoring accuracy (manual classification vs automated)

---

## Documentation Requirements

1. **README.md:**
   - Setup instructions (OpenDataLoader + Gemini)
   - Quickstart guide
   - Hybrid architecture overview diagram
   - Cost savings explanation

2. **API Documentation:**
   - OpenAPI/Swagger at `/docs`
   - Bounding box API reference
   - Routing decision documentation

3. **Deployment Guide:**
   - Environment setup (Python, OpenDataLoader, Gemini API)
   - Docker configuration
   - Monitoring setup (Prometheus metrics)

4. **Developer Guide:**
   - Code structure
   - Adding new routing rules
   - Testing hybrid pipeline
   - Quality scoring customization

5. **Operations Runbook:**
   - Common errors (OpenDataLoader failures, quality issues)
   - Debugging routing decisions
   - Scaling guidance
   - Cost monitoring

6. **Architecture Document:**
   - Hybrid pipeline flow diagram
   - Quality-based routing decision tree
   - Cost comparison analysis
   - Performance benchmarks

---

## Dependencies

```txt
# Core PDF Processing
opendataloader-pdf>=1.0.0

# AI/ML
google-genai>=0.3.0

# Web Framework
fastapi>=0.100.0
uvicorn>=0.23.0

# Database
supabase-py>=2.0.0

# Data Validation
pydantic>=2.0.0
pydantic-settings>=2.0.0

# File Handling
python-multipart>=0.0.6
python-dotenv>=1.0.0
python-magic>=0.4.27

# HTTP Client
httpx>=0.24.0

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0

# Optional: Hybrid Mode (for formula extraction)
# opendataloader-pdf[hybrid]>=1.0.0
```

---

**Approver:** _______________ **Date:** _______________

**Next Steps After Approval:**
1. Set up development environment (Python 3.11+, venv, .env)
2. Install OpenDataLoader PDF and test with sample academic paper
3. Create initial project structure (app/, tests/)
4. Begin Phase 1 implementation starting with US-001
5. Benchmark hybrid vs pure Vision approach with 5 test PDFs
6. Create task file in `tasks/` and track progress using 7 Claude Rules

**Key Success Indicators for Phase 1:**
- OpenDataLoader successfully extracts structure from 80%+ of test PDFs
- Quality scoring correctly routes PDFs (hybrid vs fallback)
- Cost reduction of 70%+ vs pure Vision approach
- Table extraction F1-score >= 0.85 (target: 0.90+)
- Bounding boxes stored for all extracted elements
