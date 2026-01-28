# Pydantic Schema Generation Prompt

**Purpose:** Generate and validate Pydantic models for PDF extraction data

---

## Prompt for Schema Generation

```
Create a Pydantic model for storing extracted academic PDF data.

REQUIREMENTS:
1. Model should validate JSON response from Gemini Vision API
2. Include type hints for all fields
3. Use Optional for fields that may be null
4. Add Field validators for:
   - confidence_score (must be 0.0-1.0)
   - authors (must be non-empty list)
   - title (must be non-empty string)
5. Include example values in docstrings
6. Add JSON schema configuration for API documentation

FIELDS TO INCLUDE:
- title: str
- authors: List[str]
- abstract: Optional[str]
- sections: List[dict] (with heading and content keys)
- keywords: List[str]
- reference_count: int
- figures_tables: List[str]
- confidence_score: float (0.0-1.0)

OUTPUT: Complete Pydantic model class definition
```

---

## Expected Schema Output

```python
from typing import List, Optional, Dict
from pydantic import BaseModel, Field, field_validator, ConfigDict

class DocumentSection(BaseModel):
    """Represents a section in the academic document."""
    heading: str = Field(..., description="Section heading (e.g., 'Introduction')")
    content: str = Field(..., description="Section content text")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "heading": "Introduction",
                "content": "This paper discusses the application of..."
            }
        }
    )


class ExtractedPDFData(BaseModel):
    """Structured data extracted from an academic PDF document."""

    title: str = Field(
        ...,
        min_length=1,
        description="Main title of the academic paper"
    )

    authors: List[str] = Field(
        ...,
        min_length=1,
        description="List of author names"
    )

    abstract: Optional[str] = Field(
        None,
        description="Paper abstract or summary"
    )

    sections: List[DocumentSection] = Field(
        default_factory=list,
        description="Document sections with headings and content"
    )

    keywords: List[str] = Field(
        default_factory=list,
        description="Key terms or keywords from the paper"
    )

    reference_count: int = Field(
        default=0,
        ge=0,
        description="Number of references cited"
    )

    figures_tables: List[str] = Field(
        default_factory=list,
        description="Captions of figures and tables"
    )

    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Extraction confidence score (0.0-1.0)"
    )

    @field_validator('authors')
    @classmethod
    def validate_authors(cls, v: List[str]) -> List[str]:
        """Ensure at least one author is provided."""
        if not v or len(v) == 0:
            raise ValueError("At least one author must be provided")
        return v

    @field_validator('title')
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Ensure title is not empty or whitespace only."""
        if not v or not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip()

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Deep Learning for NLP: A Survey",
                "authors": ["Jane Smith", "John Doe"],
                "abstract": "This paper provides a comprehensive survey...",
                "sections": [
                    {
                        "heading": "Introduction",
                        "content": "Natural language processing has..."
                    }
                ],
                "keywords": ["deep learning", "NLP", "neural networks"],
                "reference_count": 87,
                "figures_tables": ["Figure 1: Model architecture"],
                "confidence_score": 0.92
            }
        }
    )
```

---

## Validation Usage

```python
from app.models.extraction import ExtractedPDFData, DocumentSection

# Parse Gemini API response
def parse_extraction_response(gemini_response: dict) -> ExtractedPDFData:
    """Validate and parse Gemini Vision API response."""
    try:
        # Pydantic automatically validates against schema
        extracted_data = ExtractedPDFData(**gemini_response)
        return extracted_data
    except ValidationError as e:
        # Handle validation errors
        print(f"Validation error: {e}")
        raise

# Example usage
response = {
    "title": "Sample Paper",
    "authors": ["Author 1"],
    "abstract": None,
    "sections": [
        {"heading": "Intro", "content": "Text here"}
    ],
    "keywords": [],
    "reference_count": 10,
    "figures_tables": [],
    "confidence_score": 0.85
}

validated_data = ExtractedPDFData(**response)
print(validated_data.model_dump_json(indent=2))
```

---

## Schema Extensions

**For Database Storage:**
```python
class ExtractionRecord(ExtractedPDFData):
    """Extended model with database metadata."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    source_file: str
    processing_time_ms: int
```

**For API Response:**
```python
class ExtractionResponse(BaseModel):
    """API response wrapper."""
    success: bool
    data: Optional[ExtractedPDFData]
    error: Optional[str]
    processing_time_ms: int
```
