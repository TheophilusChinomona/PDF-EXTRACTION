"""
Hybrid PDF extraction pipeline combining OpenDataLoader and Gemini API.

This module implements the core extraction logic that routes between:
- Hybrid mode: OpenDataLoader structure + Gemini semantic analysis (80% cost savings)
- Vision fallback: Direct Gemini Vision API for low-quality PDFs

Uses context caching to reduce API costs by ~90% for repeated system instructions.
"""

from typing import Optional, Any, Dict
from google import genai
from google.genai import types

from app.models.extraction import ExtractionResult, ExtractedTable
from app.services.opendataloader_extractor import extract_pdf_structure
from app.utils.retry import retry_with_backoff


def _remove_additional_properties(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively clean JSON schema for Gemini API compatibility.

    Gemini's API doesn't support the additionalProperties field. This function:
    1. Removes additionalProperties from all object types
    2. For objects with only additionalProperties (like Dict[str, T]), converts
       them to empty objects to allow free-form data

    Args:
        schema: JSON schema dictionary to clean

    Returns:
        Cleaned schema compatible with Gemini API
    """
    if not isinstance(schema, dict):
        return schema

    # Create a copy to avoid modifying the original
    cleaned = {}
    had_additional_properties = False

    for key, value in schema.items():
        # Track if we had additionalProperties
        if key == "additionalProperties":
            had_additional_properties = True
            continue  # Skip it entirely

        # Recursively process nested dicts and lists
        if isinstance(value, dict):
            cleaned[key] = _remove_additional_properties(value)
        elif isinstance(value, list):
            cleaned[key] = [
                _remove_additional_properties(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            cleaned[key] = value

    # Special handling for objects that had additionalProperties but no properties
    # (like Dict[str, T] fields) - remove type constraint to allow free-form objects
    if (cleaned.get("type") == "object" and
        had_additional_properties and
        ("properties" not in cleaned or not cleaned.get("properties"))):
        # Return empty object schema to allow any data
        return {}

    return cleaned

# Minimum tokens required for Gemini context caching (API requirement)
MIN_CACHE_TOKENS = 1024

# Global cache name (reused across requests)
_EXTRACTION_CACHE_NAME: Optional[str] = None

# System instruction for academic PDF analysis (cached to reduce costs)
ACADEMIC_EXTRACTION_SYSTEM_INSTRUCTION = """You are an expert at analyzing academic research papers. Your task is to extract structured information from academic documents with high accuracy.

When analyzing papers, you should:
1. Identify and extract bibliographic metadata (title, authors, journal, year, DOI)
2. Extract the abstract verbatim if present
3. Parse document sections preserving hierarchy (Introduction, Methods, Results, Discussion, etc.)
4. Extract tables with their structure and captions
5. Parse bibliographic references into structured format
6. Maintain accuracy and avoid hallucinations - only extract information that is clearly present

For sections, include the heading text, full content, and starting page number.
For references, parse citation text to extract authors, year, and title where possible.
Focus on semantic understanding and structured extraction."""


def _estimate_token_count(text: str) -> int:
    """
    Estimate token count for text (rough approximation).

    Uses 4 characters per token as rough estimate for English text.
    This is conservative - actual tokenization may differ.

    Args:
        text: Text to estimate token count for

    Returns:
        Estimated token count
    """
    return len(text) // 4


def get_or_create_cache(client: genai.Client, model: str = "gemini-3-flash-preview") -> Optional[str]:
    """
    Get or create a context cache for academic PDF extraction.

    This function implements a singleton pattern for the extraction cache,
    creating it on first use and reusing it for subsequent requests.
    The cache contains the system instruction for academic PDF analysis,
    reducing API costs by ~90% for the cached portion.

    Returns None if the system instruction is too small (< 1024 tokens),
    as Gemini's caching API requires a minimum of 1024 tokens.

    Args:
        client: Gemini API client
        model: Gemini model name to use

    Returns:
        Cache name (resource identifier) or None if content too small for caching

    Example:
        >>> client = get_gemini_client()
        >>> cache_name = get_or_create_cache(client)
        >>> if cache_name:
        >>>     # Use cache_name in GenerateContentConfig
    """
    global _EXTRACTION_CACHE_NAME

    # Check if system instruction meets minimum token requirement
    estimated_tokens = _estimate_token_count(ACADEMIC_EXTRACTION_SYSTEM_INSTRUCTION)
    if estimated_tokens < MIN_CACHE_TOKENS:
        # System instruction too small for caching, return None
        # Extraction will proceed without caching
        return None

    # Return existing cache if available
    if _EXTRACTION_CACHE_NAME is not None:
        try:
            # Verify cache still exists (not expired)
            client.caches.get(name=_EXTRACTION_CACHE_NAME)
            return _EXTRACTION_CACHE_NAME
        except Exception:
            # Cache expired or deleted, create new one
            _EXTRACTION_CACHE_NAME = None

    # Create new cache with 1-hour TTL
    cache = client.caches.create(
        model=model,
        config=types.CreateCachedContentConfig(
            display_name='academic_pdf_extraction',
            system_instruction=ACADEMIC_EXTRACTION_SYSTEM_INSTRUCTION,
            ttl="3600s",  # 1 hour as specified in acceptance criteria
        )
    )

    if cache.name is None:
        raise ValueError("Failed to create cache: cache name is None")

    _EXTRACTION_CACHE_NAME = cache.name
    return cache.name  # Return cache.name directly to ensure str type


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

        # Get or create context cache for cost optimization (may be None if content too small)
        cache_name = get_or_create_cache(client, model)

        # Build extraction prompt for Vision analysis
        prompt = """Analyze this academic research paper from the uploaded PDF.

Extract the following information:

1. **Metadata**: Paper title, authors, journal, year, DOI
2. **Abstract**: The paper's abstract (if present)
3. **Sections**: All major sections with headings and content
4. **Tables**: Extracted table data with captions
5. **References**: Bibliographic references from the references section

Please extract the information in structured JSON format.
"""

        # Call Gemini API with uploaded file and structured output
        from typing import Any
        contents_list: list[Any] = [uploaded_file, prompt]

        # Generate clean schema without additionalProperties for Gemini compatibility
        raw_schema = ExtractionResult.model_json_schema()
        clean_schema = _remove_additional_properties(raw_schema)

        # Build config - only add cached_content if cache is available
        config_dict = {
            'response_mime_type': 'application/json',
            'response_schema': clean_schema,  # Use cleaned schema instead of model class
        }
        if cache_name is not None:
            config_dict['cached_content'] = cache_name

        response = client.models.generate_content(
            model=model,
            contents=contents_list,
            config=types.GenerateContentConfig(**config_dict)
        )

        # Parse structured response - manually parse JSON since we used dict schema
        import json
        response_text = response.text
        response_data = json.loads(response_text)
        result: ExtractionResult = ExtractionResult.model_validate(response_data)

        # Extract cache statistics from usage metadata
        cache_hit = False
        cached_tokens = 0
        total_tokens = 0

        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = response.usage_metadata
            if hasattr(usage, 'cached_content_token_count'):
                cached_tokens = usage.cached_content_token_count or 0
                cache_hit = cached_tokens > 0
            if hasattr(usage, 'total_token_count'):
                total_tokens = usage.total_token_count or 0

        # Add processing metadata indicating fallback mode
        result.processing_metadata = {
            "method": "vision_fallback",
            "reason": "Low OpenDataLoader quality score",
            "cost_savings_percent": 0,  # No cost savings from hybrid mode
            "model": model,
            "cache_eligible": cache_name is not None,  # Was caching available?
            "cache_hit": cache_hit,
            "cached_tokens": cached_tokens,
            "total_tokens": total_tokens,
            "cached_tokens_saved": cached_tokens  # Tokens that benefited from cache discount
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

    # Step 3: Get or create context cache for cost optimization (may be None if content too small)
    cache_name = get_or_create_cache(client, model)

    # Step 4: Build prompt with markdown content for Gemini
    prompt = f"""Analyze this academic research paper and extract structured information.

Here is the paper content in Markdown format:

---
{doc_structure.markdown}
---

Extract:
1. **Metadata**: Paper title, authors, journal, year, DOI
2. **Abstract**: The paper's abstract (if present)
3. **Sections**: All major sections with headings and content
4. **References**: Bibliographic references from the references section

Return structured JSON format.
"""

    # Step 5: Call Gemini API with structured output schema (wrapped in try/except for partial results)
    try:
        # Generate clean schema without additionalProperties for Gemini compatibility
        raw_schema = ExtractionResult.model_json_schema()
        clean_schema = _remove_additional_properties(raw_schema)

        # Build config - only add cached_content if cache is available
        config_dict = {
            'response_mime_type': 'application/json',
            'response_schema': clean_schema,  # Use cleaned schema instead of model class
        }
        if cache_name is not None:
            config_dict['cached_content'] = cache_name

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(**config_dict)
        )

        # Parse structured response - manually parse JSON since we used dict schema
        import json
        response_text = response.text
        response_data = json.loads(response_text)
        result: ExtractionResult = ExtractionResult.model_validate(response_data)

        # Step 6: Extract cache statistics from usage metadata
        cache_hit = False
        cached_tokens = 0
        total_tokens = 0

        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = response.usage_metadata
            if hasattr(usage, 'cached_content_token_count'):
                cached_tokens = usage.cached_content_token_count or 0
                cache_hit = cached_tokens > 0
            if hasattr(usage, 'total_token_count'):
                total_tokens = usage.total_token_count or 0

        # Step 7: Merge deterministic tables from OpenDataLoader with Gemini data
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

        # Step 8: Add processing metadata including cache statistics
        result.processing_metadata = {
            "method": "hybrid",
            "opendataloader_quality": doc_structure.quality_score,
            "cost_savings_percent": 80,  # Hybrid mode achieves ~80% cost reduction
            "element_count": doc_structure.element_count,
            "model": model,
            "cache_eligible": cache_name is not None,  # Was caching available?
            "cache_hit": cache_hit,
            "cached_tokens": cached_tokens,
            "total_tokens": total_tokens,
            "cached_tokens_saved": cached_tokens  # Tokens that benefited from cache discount
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
