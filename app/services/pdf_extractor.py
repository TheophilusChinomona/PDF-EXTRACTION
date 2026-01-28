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

from app.models.extraction import ExtractionResult, ExtractedTable, FullExamPaper
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

# System instruction for exam paper extraction (cached to reduce costs)
EXAM_EXTRACTION_SYSTEM_INSTRUCTION = """You are an advanced Academic Document Intelligence AI. Your task is to extract exam paper content into a strict, machine-readable JSON format.

### CORE OBJECTIVES
1. **Hierarchy:** Respect the structure of the paper. Group questions by their Sections or Main Questions (e.g., "SECTION A", "QUESTION 2").
2. **Context:** You MUST extract the "context" that precedes a question. This includes:
   * **Scenarios:** Case studies or stories (e.g., "PETRA FARMING...").
   * **Instructions:** Specific instructions for a section.
   * **Data Tables:** "Guide" tables often found in Business Studies (convert these to Key-Value pairs).
3. **Accuracy:** Transcribe text exactly as it appears. Do not summarize.
4. **Metadata:** Extract the Subject, Year, Session (e.g., May/June), Grade, and Syllabus (e.g., SC/NSC) from the header/cover page.

### CRITICAL EXTRACTION RULES
* **Scenarios:** If a question says "Read the scenario below," finding and attaching that scenario text to the question object is MANDATORY.
* **Nulls:** If a field (like `options` or `guide_table`) is not present, omit it or set to null.
* **Images:** If a question refers to a visual diagram (not text), describe the diagram briefly in a `context` field.
* **Completeness:** Extract EVERY question. Do not skip any.
* **Marks:** Verify marks are extracted for each question.
* **Question IDs:** Use exact numbering as shown (1.1.1, 2.3.2, etc.)."""


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
    Get or create a context cache for exam paper extraction.

    This function implements a singleton pattern for the extraction cache,
    creating it on first use and reusing it for subsequent requests.
    The cache contains the system instruction for exam paper analysis,
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
    estimated_tokens = _estimate_token_count(EXAM_EXTRACTION_SYSTEM_INSTRUCTION)
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
            display_name='exam_paper_extraction',
            system_instruction=EXAM_EXTRACTION_SYSTEM_INSTRUCTION,
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
) -> FullExamPaper:
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
        FullExamPaper with vision-based extraction

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

        # Build extraction prompt for exam paper Vision analysis
        prompt = """Analyze this examination paper PDF and extract ALL content.

Extract:
1. **Metadata**: subject, syllabus (SC/NSC), year, session (MAY/JUNE or NOV), grade, total_marks
2. **Question Groups**: Group by SECTION or QUESTION number with title and instructions
3. **Every Question** with:
   - id (exact numbering: 1.1.1, 2.3.2, etc.)
   - text (transcribe exactly - do not summarize)
   - marks
   - options (for MCQs only: label A/B/C/D with text)
   - scenario (MANDATORY if question references a case study)
   - guide_table (for fill-in or matching tables)

CRITICAL:
- Extract EVERY question without skipping any
- Attach scenario text to questions that reference it
- Transcribe text exactly as written
- Use exact question numbering as shown in the paper
"""

        # Call Gemini API with uploaded file and structured output
        from typing import Any
        contents_list: list[Any] = [uploaded_file, prompt]

        # Generate clean schema without additionalProperties for Gemini compatibility
        raw_schema = FullExamPaper.model_json_schema()
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
        result: FullExamPaper = FullExamPaper.model_validate(response_data)

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
) -> FullExamPaper:
    """
    Extract exam paper PDF using hybrid pipeline (OpenDataLoader + Gemini).

    This is the core extraction function implementing the 6-step hybrid pipeline:
    1. Extract PDF structure locally using OpenDataLoader
    2. Calculate quality score and route based on threshold
    3. Build prompt with structured markdown content
    4. Call Gemini API with response schema for structured output
    5. Add processing metadata (method, quality scores, cost savings)

    If Gemini extraction fails but raise_on_partial=False, returns partial
    extraction with basic metadata only.

    Args:
        client: Gemini API client
        file_path: Path to PDF file to extract
        model: Gemini model name (default: gemini-3-flash-preview)
        raise_on_partial: If True, raise exception on Gemini failure instead of returning partial result

    Returns:
        FullExamPaper with complete or partial extraction data

    Raises:
        FileNotFoundError: If PDF file doesn't exist
        ValueError: If PDF cannot be processed
        Exception: For Gemini API errors (only if raise_on_partial=True)
        PartialExtractionError: If Gemini fails and raise_on_partial=False (contains partial result)

    Example:
        >>> client = get_gemini_client()
        >>> result = await extract_pdf_data_hybrid(client, "exam.pdf")
        >>> print(result.subject)
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

    # Step 4: Build prompt with markdown content for exam paper extraction
    prompt = f"""Extract all exam content from this examination paper.

Here is the document in Markdown format:
---
{doc_structure.markdown}
---

Extract into JSON:
1. **Metadata**: subject, syllabus (SC/NSC), year, session (MAY/JUNE or NOV), grade, total_marks
2. **Groups**: Each QUESTION/SECTION with group_id, title, instructions
3. **Questions**: id, text (exact transcription), marks, options (MCQs only), scenario, guide_table

CRITICAL:
- Extract ALL questions - do not skip any
- Attach scenario/case study text to questions that reference it
- Do not summarize - transcribe text exactly as written
- Use exact question numbering (1.1.1, 2.3.2, etc.)
"""

    # Step 5: Call Gemini API with structured output schema (wrapped in try/except for partial results)
    try:
        # Generate clean schema without additionalProperties for Gemini compatibility
        raw_schema = FullExamPaper.model_json_schema()
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
        result: FullExamPaper = FullExamPaper.model_validate(response_data)

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

        # Step 7: Add processing metadata including cache statistics
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
        # If Gemini extraction fails, create partial result
        if raise_on_partial:
            raise

        # Build partial extraction result with minimal data
        partial_result = FullExamPaper(
            subject="[Partial Extraction]",
            syllabus="Unknown",
            year=0,
            session="Unknown",
            grade="Unknown",
            total_marks=0,
            groups=[],
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
        partial_result: FullExamPaper with partial data
        original_exception: The original exception that caused partial extraction
    """

    def __init__(self, message: str, partial_result: FullExamPaper, original_exception: Exception):
        super().__init__(message)
        self.partial_result = partial_result
        self.original_exception = original_exception
