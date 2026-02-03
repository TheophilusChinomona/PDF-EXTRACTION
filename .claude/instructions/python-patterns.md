# Python Code Patterns

## Overview
Python conventions and code patterns specific to this FastAPI + Gemini project.

---

## Code Style

### PEP 8 Compliance
- Follow PEP 8 for all Python code
- Type hints required for all function signatures
- Async/await for I/O operations (API calls, database)
- Pydantic models for data validation

### Import Order
1. Standard library imports
2. Third-party imports
3. Local application imports

### Example
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

## Gemini SDK Pattern

**IMPORTANT:** Use `google.genai` not `google.generativeai`

```python
from google import genai
from google.genai import types

# Initialize client (reads GEMINI_API_KEY from env)
client = genai.Client()

# Structured output with Pydantic schema
response = client.models.generate_content(
    model="gemini-3-flash-preview",
    contents=["Extract data from this content"],
    config=types.GenerateContentConfig(
        response_mime_type='application/json',
        response_schema=YourPydanticModel
    )
)

result = response.parsed  # Returns Pydantic object directly
```

---

## Hybrid Extraction Pipeline

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
    result.tables = tables
    return result
```

---

## Quality Scoring

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

## Pydantic Schema Example

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
    bounding_boxes: dict[str, BoundingBox]
    confidence_score: float = Field(ge=0.0, le=1.0)
    quality_score: float
    processing_method: str  # "hybrid" or "vision_fallback"
```
