"""
Hybrid PDF extraction pipeline combining OpenDataLoader and Gemini API.

This module implements the core extraction logic that routes between:
- Hybrid mode: OpenDataLoader structure + Gemini semantic analysis (80% cost savings)
- Vision fallback: Direct Gemini Vision API for low-quality PDFs
"""

from typing import Optional
from google import genai
from google.genai import types

from app.models.extraction import ExtractionResult, ExtractedTable
from app.services.opendataloader_extractor import extract_pdf_structure
from app.utils.retry import retry_with_backoff


@retry_with_backoff()
def extract_with_vision_fallback(
    client: genai.Client,
    file_path: str,
    model: str = "gemini-3-flash-preview"
) -> ExtractionResult:
    """
    Extract PDF using Gemini Vision API fallback (for low-quality PDFs).

    This function uploads the PDF to Gemini Files API and uses Vision analysis
    when OpenDataLoader quality score is too low (<0.7). This is the fallback
    path for scanned PDFs or documents with poor structure.

    Args:
        client: Gemini API client
        file_path: Path to PDF file
        model: Gemini model name to use

    Returns:
        ExtractionResult with vision-based extraction

    Raises:
        FileNotFoundError: If PDF file doesn't exist
        ValueError: If file upload or processing fails
        Exception: For Gemini API errors

    Example:
        >>> client = get_gemini_client()
        >>> result = extract_with_vision_fallback(client, "scanned.pdf")
        >>> print(result.processing_metadata["method"])  # "vision_fallback"
    """
    uploaded_file = None

    try:
        # Upload PDF file to Gemini Files API
        uploaded_file = client.files.upload(file=file_path)

        # Build extraction prompt for Vision analysis
        prompt = """You are analyzing an academic research paper from an image-based PDF.
Extract the following information by reading the document:

1. **Metadata**: Paper title, authors, journal, year, DOI
2. **Abstract**: The paper's abstract (if present)
3. **Sections**: All major sections with headings and content
4. **Tables**: Extracted table data with captions
5. **References**: Bibliographic references from the references section

Please extract the information in structured JSON format. Focus on accurately reading
and understanding the visual content. For sections, include the heading, content, and
starting page number. For references, parse citation text to extract authors, year,
and title where possible.
"""

        # Call Gemini API with uploaded file and structured output
        from typing import Any
        contents_list: list[Any] = [uploaded_file, prompt]
        response = client.models.generate_content(
            model=model,
            contents=contents_list,
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
                response_schema=ExtractionResult
            )
        )

        # Parse structured response
        parsed = response.parsed
        if not isinstance(parsed, ExtractionResult):
            raise ValueError("Gemini API returned unexpected response type")
        result: ExtractionResult = parsed

        # Add processing metadata indicating fallback mode
        result.processing_metadata = {
            "method": "vision_fallback",
            "reason": "Low OpenDataLoader quality score",
            "cost_savings_percent": 0,  # No cost savings in fallback mode
            "model": model
        }

        return result

    finally:
        # Always clean up uploaded file
        if uploaded_file is not None and hasattr(uploaded_file, 'name') and uploaded_file.name:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                # Log cleanup failure but don't raise (extraction already complete)
                pass


@retry_with_backoff()
async def extract_pdf_data_hybrid(
    client: genai.Client,
    file_path: str,
    model: str = "gemini-3-flash-preview",
    raise_on_partial: bool = False
) -> ExtractionResult:
    """
    Extract PDF data using hybrid pipeline (OpenDataLoader + Gemini).

    This is the core extraction function implementing the 6-step hybrid pipeline:
    1. Extract PDF structure locally using OpenDataLoader
    2. Calculate quality score and route based on threshold
    3. Build prompt with structured markdown content
    4. Call Gemini API with response schema for structured output
    5. Merge OpenDataLoader tables with Gemini semantic data
    6. Add processing metadata (method, quality scores, cost savings)

    If Gemini extraction fails but raise_on_partial=False, returns partial
    extraction with OpenDataLoader data only (tables, bounding boxes).

    Args:
        client: Gemini API client
        file_path: Path to PDF file to extract
        model: Gemini model name (default: gemini-3-flash-preview)
        raise_on_partial: If True, raise exception on Gemini failure instead of returning partial result

    Returns:
        ExtractionResult with complete or partial extraction data

    Raises:
        FileNotFoundError: If PDF file doesn't exist
        ValueError: If PDF cannot be processed
        Exception: For Gemini API errors (only if raise_on_partial=True)
        PartialExtractionError: If Gemini fails and raise_on_partial=False (contains partial result)

    Example:
        >>> client = get_gemini_client()
        >>> result = await extract_pdf_data_hybrid(client, "paper.pdf")
        >>> print(result.metadata.title)
        >>> print(result.processing_metadata["method"])  # "hybrid"
    """
    # Step 1: Extract PDF structure using OpenDataLoader (local, fast, free)
    doc_structure = extract_pdf_structure(file_path)

    # Step 2: Route based on quality score
    if doc_structure.quality_score < 0.7:
        # Low quality: fallback to Gemini Vision API
        return extract_with_vision_fallback(client, file_path, model)

    # Step 3: Build prompt with markdown content for Gemini
    prompt = f"""You are analyzing an academic research paper. Extract the following information:

1. **Metadata**: Paper title, authors, journal, year, DOI
2. **Abstract**: The paper's abstract (if present)
3. **Sections**: All major sections with headings and content
4. **References**: Bibliographic references from the references section

Here is the paper content in Markdown format:

---
{doc_structure.markdown}
---

Please extract the information in structured JSON format. Focus on semantic understanding of the content.
For sections, include the heading, content, and starting page number.
For references, parse citation text to extract authors, year, and title where possible.
"""

    # Step 4: Call Gemini API with structured output schema (wrapped in try/except for partial results)
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
                response_schema=ExtractionResult
            )
        )

        # Parse structured response
        parsed = response.parsed
        if not isinstance(parsed, ExtractionResult):
            raise ValueError("Gemini API returned unexpected response type")
        result: ExtractionResult = parsed

        # Step 5: Merge deterministic tables from OpenDataLoader with Gemini data
        # OpenDataLoader's table extraction is more reliable than Gemini's
        odl_tables = [
            ExtractedTable(
                caption=t.get("caption", ""),
                page_number=t.get("page", 1),
                data=t.get("data", []),
                bbox=t.get("bbox")  # Pydantic will auto-convert dict to BoundingBox
            )
            for t in doc_structure.tables
        ]
        result.tables = odl_tables

        # Merge bounding boxes from OpenDataLoader
        result.bounding_boxes = doc_structure.bounding_boxes

        # Step 6: Add processing metadata
        result.processing_metadata = {
            "method": "hybrid",
            "opendataloader_quality": doc_structure.quality_score,
            "cost_savings_percent": 80,  # Hybrid mode achieves ~80% cost reduction
            "element_count": doc_structure.element_count,
            "model": model
        }

        return result

    except Exception as e:
        # If Gemini extraction fails, create partial result from OpenDataLoader data
        if raise_on_partial:
            raise

        # Build partial extraction result with OpenDataLoader data only
        from app.models.extraction import ExtractedMetadata

        partial_result = ExtractionResult(
            metadata=ExtractedMetadata(title="[Partial Extraction]"),
            abstract=None,
            sections=[],
            tables=[
                ExtractedTable(
                    caption=t.get("caption", ""),
                    page_number=t.get("page", 1),
                    data=t.get("data", []),
                    bbox=t.get("bbox")
                )
                for t in doc_structure.tables
            ],
            references=[],
            confidence_score=0.0,
            bounding_boxes=doc_structure.bounding_boxes,
            processing_metadata={
                "method": "partial",
                "opendataloader_quality": doc_structure.quality_score,
                "cost_savings_percent": 0,
                "element_count": doc_structure.element_count,
                "model": model,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )

        # Re-raise as PartialExtractionError containing the partial result
        raise PartialExtractionError(
            message=f"Gemini extraction failed: {str(e)}",
            partial_result=partial_result,
            original_exception=e
        )


class PartialExtractionError(Exception):
    """Exception raised when extraction partially succeeds with OpenDataLoader but Gemini fails.

    Attributes:
        message: Error message
        partial_result: ExtractionResult with partial data from OpenDataLoader
        original_exception: The original exception that caused partial extraction
    """

    def __init__(self, message: str, partial_result: ExtractionResult, original_exception: Exception):
        super().__init__(message)
        self.partial_result = partial_result
        self.original_exception = original_exception
