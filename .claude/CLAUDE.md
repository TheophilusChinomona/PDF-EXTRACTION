# PDF-Extraction Project Guidelines

> **IMPORTANT:** This file contains project-specific instructions. Always follow the global Claude rules in `~/.claude/CLAUDE.md` along with these project-specific guidelines.

> **CRITICAL:** If you are an autonomous agent (Ralph), **ALWAYS** read `scripts/ralph/CLAUDE.md` first for the iterative implementation workflow before proceeding.

---

## Autonomous Implementation Workflow (Ralph Agent)

**For autonomous agents implementing user stories:**

📍 **Start here:** Read `scripts/ralph/CLAUDE.md` for the complete workflow

**Quick Reference:**
1. Read PRD at `scripts/ralph/prd.json`
2. Read progress log at `scripts/ralph/progress.txt` (check Codebase Patterns first!)
3. Implement ONE user story at a time
4. Run quality checks (tests, typecheck, lint)
5. Commit with format: `feat: [Story ID] - [Story Title]`
6. Update PRD to mark story as `passes: true`
7. Append progress to `progress.txt` with learnings

**Important:**
- Always read the **Codebase Patterns** section in `progress.txt` before starting
- Update CLAUDE.md files when you discover reusable patterns
- Never commit broken code - all commits must pass quality checks

---

## Project Overview

**Tech Stack:**
- **Backend:** Python 3.11+, FastAPI
- **AI/ML:** Google Gemini 3 API (multimodal document processing) + OpenDataLoader PDF (local structure extraction)
- **Database:** Supabase (PostgreSQL)
- **Key Libraries:** opendataloader-pdf, google-genai, fastapi, supabase-py, pydantic, python-multipart

**Architecture:** Hybrid extraction pipeline
- **OpenDataLoader** (local): Extracts PDF structure, tables, bounding boxes (0.05s/page, $0 cost, F1: 0.93 for tables)
- **Gemini 3 API** (cloud): Semantic analysis of structured content (80% cost reduction vs pure AI)

**Project Purpose:**
Microservice for extracting structured data from academic PDFs using hybrid approach. Processes multi-page documents, extracts text and visual elements with bounding boxes, and stores results in Supabase. Achieves 80% cost reduction and 95%+ accuracy through local preprocessing + AI semantic understanding.

---

## Code Style and Conventions

### Python Standards
- **PEP 8** compliance for all Python code
- **Type hints** required for all function signatures
- **Async/await** patterns for I/O operations (API calls, database)
- **Pydantic models** for data validation and serialization
- **Descriptive variable names** (no single-letter except loop counters)

### File Organization
```
pdf-extraction/
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── routers/             # API route handlers
│   ├── services/            # Business logic (PDF processing, Gemini API)
│   ├── models/              # Pydantic schemas
│   ├── db/                  # Database clients and queries
│   └── config.py            # Configuration management
├── tests/                   # Unit and integration tests
├── .env                     # Environment variables (NEVER commit)
└── requirements.txt         # Python dependencies
```

### Import Order
1. Standard library imports
2. Third-party imports
3. Local application imports

### Example Code Pattern
```python
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.gemini import extract_pdf_data
from app.db.supabase import store_extraction_result

async def process_pdf(file_path: str) -> dict:
    """Extract data from PDF using Gemini Vision API."""
    try:
        result = await extract_pdf_data(file_path)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## Security Considerations

### API Keys and Secrets
- **NEVER** hardcode API keys in source code
- Use `.env` file for all secrets (Gemini API key, Supabase URL/key)
- Load secrets via `python-dotenv` or FastAPI settings
- Verify `.env` is in `.gitignore`

### PDF Processing Safety
- Validate file uploads (size limits, file type verification)
- Sanitize file paths to prevent directory traversal
- Implement rate limiting on API endpoints
- Handle malformed PDFs gracefully

### Data Privacy
- No logging of extracted content without user consent
- Secure storage of API responses in Supabase
- Clear data retention policies

### Checklist for Every Feature
- [ ] No hardcoded secrets
- [ ] Input validation (file uploads, API parameters)
- [ ] Error handling doesn't leak sensitive info
- [ ] Rate limiting considered
- [ ] File operations validate paths
- [ ] HTTPS enforced in production

---

## Testing Requirements

### Local Development Testing
- Test Gemini API connection with sample PDF
- Verify extraction output matches expected schema
- Test error handling (invalid files, API failures)

### API Testing
- Health check endpoint (`/health`)
- Upload endpoint with valid/invalid PDFs
- Response schema validation

### Database Testing
- Supabase connection verification
- Insert/query operations
- Schema migrations

### Test Command
```bash
pytest tests/ -v --cov=app
```

---

## Environment Setup

### Required Environment Variables
```bash
GEMINI_API_KEY=your_api_key_here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_anon_key_here
```

### Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Python Interpreter (IMPORTANT)
The `.venv` virtual environment does **not** have all runtime dependencies installed (e.g. missing `uvicorn`, `supabase`). The system Python at `C:\Python314\python.exe` has the full set of packages.

- **Start the server:** `"C:\Python314\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
- **Run scripts (supabase, firebase, etc.):** `"C:\Python314\python.exe" scripts/<script>.py`
- **Syntax checks / pure-stdlib tasks:** `.venv` Python works fine

Always use the system Python for anything that imports `supabase`, `firebase_admin`, or `uvicorn`.

### Applying SQL Migrations
There is no `psql` or Supabase CLI on this machine. To run DDL migrations:
1. Open the Supabase dashboard SQL Editor: `https://supabase.com/dashboard/project/aqxgnvjqabitfvcnboah`
2. Paste the SQL from the migration file
3. Click **Run**

---

## Development Workflow

### Phase 1: Hybrid Pipeline MVP (Weeks 1-2)
1. **US-001:** Project setup with OpenDataLoader + Gemini SDK
2. **US-002:** Gemini client configuration
3. **US-019:** OpenDataLoader integration (local PDF parsing)
4. **US-003:** Hybrid extraction pipeline (OpenDataLoader → Gemini)
5. **US-021:** Quality scoring and routing logic
6. **US-004:** File validation
7. **US-005-007:** FastAPI endpoints

**Deliverable:** Working API with hybrid extraction

### Phase 2: Data Persistence & Bounding Boxes (Week 2-3)
1. **US-008:** Supabase client configuration
2. **US-009:** Database schema with bounding boxes
3. **US-010:** Data storage functions
4. **US-020:** Bounding box API endpoints

**Deliverable:** Complete persistence with citation features

### Phase 3: Reliability & Monitoring (Week 3)
1. **US-012:** Retry logic
2. **US-013:** Partial result storage
3. **US-014:** Manual review queue
4. **US-017:** Rate limiting
5. **US-018:** Logging with routing analytics

**Deliverable:** Production-ready service

### Phase 4: Advanced Features (Week 4)
1. **US-011:** Batch processing
2. **US-015:** Webhook notifications
3. **US-016:** Context caching (95%+ total cost savings)

**Deliverable:** Full-featured service

---

## Common Patterns

### Hybrid Extraction Pipeline (IMPORTANT)
```python
from opendataloader_pdf import DocumentLoader
from google import genai
from google.genai import types

async def extract_pdf_hybrid(file_path: str) -> dict:
    """Extract PDF using hybrid approach (OpenDataLoader + Gemini)."""

    # Step 1: Local structure extraction (fast, free, deterministic)
    loader = DocumentLoader()
    doc = loader.load(file_path)
    markdown = doc.export_to_markdown()
    tables = doc.get_tables()

    # Step 2: Quality check
    quality_score = calculate_quality_score(doc)

    # Step 3: Route based on quality
    if quality_score < 0.7:
        # Fallback to Gemini Vision for low-quality PDFs
        return await extract_with_vision(file_path)

    # Step 4: Send structured Markdown to Gemini (80% cost savings)
    client = genai.Client()
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[f"Analyze this academic paper:\n\n{markdown}"],
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            response_schema=ExtractionResult
        )
    )

    # Step 5: Merge deterministic tables with AI semantics
    result = response.parsed
    result.tables = tables  # Use OpenDataLoader's table extraction
    return result
```

### Gemini Client (Modern SDK)
```python
from google import genai  # NOTE: Use 'google' not 'google.generativeai'
from google.genai import types

# Initialize client (reads GEMINI_API_KEY from env)
client = genai.Client()

# Structured output with Pydantic schema
response = client.models.generate_content(
    model="gemini-3-flash-preview",  # Use modern models
    contents=["Extract data from this content"],
    config=types.GenerateContentConfig(
        response_mime_type='application/json',
        response_schema=YourPydanticModel
    )
)

result = response.parsed  # Returns Pydantic object directly
```

### Pydantic Schema Example
```python
from pydantic import BaseModel, Field
from typing import List, Optional

class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    page: int

class ExtractedData(BaseModel):
    title: str
    authors: List[str]
    abstract: Optional[str] = None
    sections: List[dict]
    tables: List[dict]  # From OpenDataLoader
    bounding_boxes: dict[str, BoundingBox]  # NEW: Enable citations
    confidence_score: float = Field(ge=0.0, le=1.0)
    quality_score: float  # OpenDataLoader quality
    processing_method: str  # "hybrid" or "vision_fallback"
```

### Quality Scoring
```python
def calculate_quality_score(doc) -> float:
    """Calculate extraction quality (0.0 to 1.0) for routing."""
    score = 0.0

    # Text completeness (40%)
    if len(doc.get_text()) > 1000:
        score += 0.4

    # Structure detection (30%)
    if len(doc.elements) > 50:
        score += 0.3

    # Heading hierarchy (15%)
    headings = [e for e in doc.elements if e.type == "heading"]
    if len(headings) >= 5:
        score += 0.15

    # Table extraction (15%)
    if len(doc.get_tables()) > 0:
        score += 0.15

    return min(score, 1.0)
```

---

## References

- **PRD:** See `.claude/tasks/prd-pdf-extraction-service.md` for full specifications (v2.0 - Hybrid Architecture)
- **Ralph Agent Workflow:** See `scripts/ralph/CLAUDE.md` for autonomous implementation instructions
- **Global Rules:** See `~/.claude/CLAUDE.md` for 7 Claude Rules workflow
- **Tasks:** Track work in `.claude/tasks/todo.md`
- **Skills:** Custom commands in `.claude/skills/`
- **Architecture Research:** OpenDataLoader integration analysis in conversation history

---

**Last Updated:** 2026-02-02 (Added Python interpreter and migration notes)
