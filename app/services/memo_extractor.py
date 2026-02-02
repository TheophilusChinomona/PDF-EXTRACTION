"""
Hybrid memo extraction pipeline for marking guidelines (memos).

This module implements memo extraction logic that routes between:
- Hybrid mode: OpenDataLoader structure + Gemini semantic analysis
- Vision fallback: Direct Gemini Vision API for low-quality PDFs

Reuses core infrastructure from pdf_extractor.py with memo-specific prompts.
"""

import asyncio
import json
import logging
from typing import Optional, Any, Dict
from pydantic import ValidationError
from google import genai
from google.genai import types

from app.models.extraction import DocumentStructure
from app.models.memo_extraction import MarkingGuideline
from app.services.opendataloader_extractor import extract_pdf_structure
from app.services.pdf_extractor import _remove_additional_properties, _estimate_token_count
from app.utils.retry import retry_with_backoff


# Minimum tokens required for Gemini context caching (API requirement)
MIN_CACHE_TOKENS = 1024

# Global memo cache name (separate from exam paper cache) with thread-safe lock
_memo_cache_lock = asyncio.Lock()
_MEMO_CACHE_NAME: Optional[str] = None


def _is_cache_expired_error(e: Exception) -> bool:
    """True if exception indicates cache not found/expired (Gap 9.4, 3.2)."""
    msg = str(e).lower()
    return "cache" in msg and (
        "not found" in msg or "expired" in msg or "invalid" in msg or "not exist" in msg
    )

# System instruction for memo extraction (adapted from sample system prompt)
MEMO_EXTRACTION_SYSTEM_INSTRUCTION = """You are an expert Chief Examiner and Archivist. Your task is to extract the **Marking Guideline (Memorandum)** for an exam paper into structured JSON.

### CORE OBJECTIVES
1. **Extract the "Source of Truth":** I need every possible correct answer listed in the memo. If the memo lists 10 facts but the question only asks for 4, **EXTRACT ALL 10**. This allows us to grade any valid answer a student gives.
2. **Capture Marker Instructions:** This is critical. If the text says "Mark the first TWO (2) only" or "Accept responses in any order," you MUST extract this into the `marker_instruction` field.
3. **Handle Structure:**
   * **Section A:** Usually simple key-value pairs (1.1.1 -> A) or match columns (1.3.1 -> C).
   * **Section B (Direct Questions):** Usually lists of bullet points. Capture these as `model_answers`.
   * **Section C (Essays):** These are complex. You must break them down into `introduction`, `body_sections` (by sub-heading), and `conclusion`.

### SPECIAL HANDLING RULES
* **Ignore Preamble:** Skip the first few pages containing "Notes to Markers" (e.g., "Use a red pen," "Cognitive verbs"). Start extraction from **SECTION A**.
* **Sub-Questions:** For questions like 1.2, extract the specific answer for 1.2.1, 1.2.2, etc., into the `answers` list as [{"sub_id": "1.2.1", "value": "Answer"}, ...].
* **Match Columns:** If the memo answers a "Match Column" question, extract as [{"sub_id": "1.3.1", "value": "C (description...)"}, ...].
* **Positive/Negative Split:** If a question asks for positives AND negatives (e.g., "Impact of TQM"), use `model_answers` as dict: {"positives": [...], "negatives": [...]}.
* **Structured Answers:** For questions requiring paired responses (Strategy/Motivation, Function/Motivation), use `structured_answer`: [{"strategy": "...", "motivation": "..."}, ...].
* **Essay Body Sections:** Each body section has flexible structure with keys like "sub_topic", "points", "positives", "negatives", "rights" depending on content type.

### SECTION-SPECIFIC EXTRACTION RULES

**SECTION A (Multiple Choice, Fill-in-blank, Match Columns):**
- Multiple choice: Extract as `marks` only (no correct answer shown in memo, just marks allocated)
- Fill-in-blank: Extract as `answers` list with sub_id/value pairs
- Match columns: Extract as `answers` list with sub_id/value pairs (e.g., "1.3.1" -> "C (description)")

**SECTION B (Short Answer Questions):**
- Extract question `text` (the topic/heading)
- Extract ALL valid facts into `model_answers` (list) even if more facts than marks
- Capture `marker_instruction` if present (e.g., "Mark the first FOUR (4) only")
- Use `max_marks` for questions where more answers are given than marks available
- For positive/negative questions: use `model_answers` as {"positives": [...], "negatives": [...]}
- For paired answers: use `structured_answer` list with appropriate keys (strategy/motivation, function/motivation, etc.)

**SECTION C (Essay Questions):**
- Extract `topic` (main essay topic name)
- Use `max_marks` for total marks (usually 40)
- Extract `essay_structure`:
  * `introduction`: List of valid introduction points
  * `body_sections`: List of dicts, each with:
    - "sub_topic": The sub-heading name
    - "points": List of valid facts (for simple lists)
    - OR "positives"/"negatives": Lists for impact questions
    - OR "rights": List for rights-based questions
  * `conclusion`: List of valid conclusion points

### METADATA EXTRACTION
Extract from cover page or first page:
- subject: Full subject name (e.g., "Business Studies P1")
- type: "Marking Guideline (Memorandum)"
- year: Integer (e.g., 2025)
- session: "MAY/JUNE" or "NOV"
- grade: String (e.g., "12")
- total_marks: Integer total marks for the paper

### JSON OUTPUT FORMAT
Output ONLY valid JSON matching the `MarkingGuideline` schema. Do NOT include explanatory text outside the JSON structure."""


async def get_or_create_memo_cache(client: genai.Client, model: str = "gemini-3-flash-preview") -> Optional[str]:
    """
    Get or create a context cache for memo extraction.

    This function implements a singleton pattern for the memo cache,
    separate from the exam paper cache. The cache contains the system
    instruction for memo analysis, reducing API costs by ~90% for the
    cached portion.

    Returns None if the system instruction is too small (< 1024 tokens),
    as Gemini's caching API requires a minimum of 1024 tokens.

    Args:
        client: Gemini API client
        model: Gemini model name to use

    Returns:
        Cache name (resource identifier) or None if content too small for caching

    Example:
        >>> client = get_gemini_client()
        >>> cache_name = await get_or_create_memo_cache(client)
        >>> if cache_name:
        >>>     # Use cache_name in GenerateContentConfig
    """
    global _MEMO_CACHE_NAME

    # Check outside lock (no shared state)
    estimated_tokens = _estimate_token_count(MEMO_EXTRACTION_SYSTEM_INSTRUCTION)
    if estimated_tokens < MIN_CACHE_TOKENS:
        # System instruction too small for caching, return None
        return None

    # Acquire lock for thread-safe access
    async with _memo_cache_lock:
        # Return existing cache if available
        if _MEMO_CACHE_NAME is not None:
            try:
                # Verify cache still exists (not expired)
                client.caches.get(name=_MEMO_CACHE_NAME)
                return _MEMO_CACHE_NAME
            except Exception:
                # Cache expired or deleted, create new one
                _MEMO_CACHE_NAME = None

        # Create new cache with 1-hour TTL
        cache = client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                display_name='memo_extraction',
                system_instruction=MEMO_EXTRACTION_SYSTEM_INSTRUCTION,
                ttl="3600s",  # 1 hour
            )
        )

        if cache.name is None:
            raise ValueError("Failed to create memo cache: cache name is None")

        _MEMO_CACHE_NAME = cache.name
        return cache.name


@retry_with_backoff()
async def extract_memo_with_vision_fallback(
    client: genai.Client,
    file_path: str,
    model: str = "gemini-3-flash-preview"
) -> MarkingGuideline:
    """
    Extract memo using Gemini Vision API fallback (for low-quality PDFs).

    This function uploads the PDF to Gemini Files API and uses Vision analysis
    when OpenDataLoader quality score is too low (<0.7).

    Args:
        client: Gemini API client
        file_path: Path to PDF file
        model: Gemini model name to use

    Returns:
        MarkingGuideline with vision-based extraction

    Raises:
        FileNotFoundError: If PDF file doesn't exist
        ValueError: If file upload or processing fails
        Exception: For Gemini API errors

    Example:
        >>> client = get_gemini_client()
        >>> result = extract_memo_with_vision_fallback(client, "memo_scanned.pdf")
        >>> print(result.processing_metadata["method"])  # "vision_fallback"
    """
    uploaded_file = None

    try:
        # Upload PDF file to Gemini Files API
        uploaded_file = client.files.upload(file=file_path)

        # Get or create context cache for cost optimization
        cache_name = await get_or_create_memo_cache(client, model)

        # Build extraction prompt for memo Vision analysis
        prompt = """Analyze this marking guideline (memorandum) PDF and extract ALL content.

METADATA: Extract subject, type ("Marking Guideline (Memorandum)"), year, session (MAY/JUNE or NOV), grade, total_marks.

CRITICAL RULES:
- Skip "Notes to Markers" preamble - start from SECTION A
- Extract EVERY valid answer listed, even if more answers than marks
- Capture marker instructions (e.g., "Mark the first TWO only")
- For essays (Section C): Break into introduction, body_sections (with sub-topics), conclusion

SECTION A (MCQ/Fill-blank/Match):
- MCQ: Just marks (no answers shown)
- Fill-blank: `answers` list [{"sub_id": "1.2.1", "value": "..."}, ...]
- Match: `answers` list [{"sub_id": "1.3.1", "value": "C (description)"}, ...]

SECTION B (Short Answer):
- Extract question `text` (topic)
- Extract ALL facts into `model_answers` list
- Use dict for positive/negative: {"positives": [...], "negatives": [...]}
- Use `structured_answer` for paired responses: [{"strategy": "...", "motivation": "..."}, ...]
- Capture `marker_instruction` if present

SECTION C (Essays):
- Extract `topic` and `max_marks`
- Build `essay_structure`:
  * introduction: [...]
  * body_sections: [{"sub_topic": "...", "points": [...]}, ...] (or use "positives"/"negatives"/"rights" instead of "points")
  * conclusion: [...]

Extract ALL content without skipping any questions or answers."""

        # Call Gemini API with uploaded file and structured output
        from typing import Any
        contents_list: list[Any] = [uploaded_file, prompt]

        # Generate clean schema without additionalProperties for Gemini compatibility
        raw_schema = MarkingGuideline.model_json_schema()
        clean_schema = _remove_additional_properties(raw_schema)

        # Build config - only add cached_content if cache is available
        config_dict = {
            'response_mime_type': 'application/json',
            'response_schema': clean_schema,
        }
        if cache_name is not None:
            config_dict['cached_content'] = cache_name

        try:
            response = client.models.generate_content(
                model=model,
                contents=contents_list,
                config=types.GenerateContentConfig(**config_dict)
            )
        except Exception as e:
            if cache_name is not None and _is_cache_expired_error(e):
                global _MEMO_CACHE_NAME
                _MEMO_CACHE_NAME = None
                config_dict = {k: v for k, v in config_dict.items() if k != 'cached_content'}
                response = client.models.generate_content(
                    model=model,
                    contents=contents_list,
                    config=types.GenerateContentConfig(**config_dict)
                )
            else:
                raise

        # Parse structured response
        response_text = response.text
        if response_text is None:
            raise ValueError("Gemini API returned empty response")
        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logging.getLogger(__name__).warning(
                "Gemini response JSON decode failed: %s; response snippet: %s",
                e,
                (response_text[:500] if response_text else "") + "...",
            )
            raise ValueError(f"Invalid JSON in Gemini response: {e}") from e
        try:
            result = MarkingGuideline.model_validate(response_data)
        except ValidationError as e:
            logging.getLogger(__name__).warning(
                "Gemini response schema validation failed: %s; data keys: %s",
                e,
                list(response_data.keys()) if isinstance(response_data, dict) else type(response_data).__name__,
            )
            raise

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
            "cache_eligible": cache_name is not None,
            "cache_hit": cache_hit,
            "cached_tokens": cached_tokens,
            "total_tokens": total_tokens,
            "cached_tokens_saved": cached_tokens
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
async def extract_memo_data_hybrid(
    client: genai.Client,
    file_path: str,
    model: str = "gemini-3-flash-preview",
    raise_on_partial: bool = False,
    doc_structure: Optional[DocumentStructure] = None,
) -> MarkingGuideline:
    """
    Extract memo PDF using hybrid pipeline (OpenDataLoader + Gemini).

    This is the core extraction function implementing the hybrid pipeline:
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
        MarkingGuideline with complete or partial extraction data

    Raises:
        FileNotFoundError: If PDF file doesn't exist
        ValueError: If PDF cannot be processed
        Exception: For Gemini API errors (only if raise_on_partial=True)
        PartialMemoExtractionError: If Gemini fails and raise_on_partial=False (contains partial result)

    Example:
        >>> client = get_gemini_client()
        >>> result = await extract_memo_data_hybrid(client, "memo.pdf")
        >>> print(result.meta["subject"])
        >>> print(result.processing_metadata["method"])  # "hybrid"
    """
    # Step 1: Extract PDF structure using OpenDataLoader (local, fast, free)
    # Re-use pre-computed structure if provided (avoids duplicate work during classification)
    if doc_structure is None:
        doc_structure = extract_pdf_structure(file_path)

    # Step 2: Route based on quality score
    if doc_structure.quality_score < 0.7:
        # Low quality: fallback to Gemini Vision API
        return await extract_memo_with_vision_fallback(client, file_path, model)

    # Step 3: Get or create context cache for cost optimization
    cache_name = await get_or_create_memo_cache(client, model)

    # Step 4: Build prompt with markdown content for memo extraction
    prompt = f"""Extract all content from this marking guideline (memorandum).

Here is the document in Markdown format:
---
{doc_structure.markdown}
---

METADATA: Extract subject, type ("Marking Guideline (Memorandum)"), year, session (MAY/JUNE or NOV), grade, total_marks.

CRITICAL RULES:
- Skip "Notes to Markers" preamble at the beginning
- Start extraction from SECTION A
- Extract EVERY valid answer listed, even if there are more answers than marks allocated
- Capture marker instructions verbatim (e.g., "Mark the first TWO (2) only")
- For essays (Section C): Break down into introduction, body_sections (with sub-topics), conclusion

SECTION A (MCQ/Fill-blank/Match):
- MCQ: Extract just `marks` field (correct answer not shown in memo)
- Fill-blank: Use `answers` list [{{"sub_id": "1.2.1", "value": "parental"}}, ...]
- Match: Use `answers` list [{{"sub_id": "1.3.1", "value": "C (protects both lenders...)"}}, ...]

SECTION B (Short Answer Questions):
- Extract question `text` (the topic/heading like "Advantages of intensive strategies")
- Extract ALL valid facts into `model_answers` as a list (even if 10 facts for 4 marks)
- For positive/negative questions: use dict {{"positives": [...], "negatives": [...]}}
- For paired answers: use `structured_answer` list [{{"strategy": "Concentric diversification", "motivation": "They added..."}}, ...]
- Always capture `marker_instruction` if present
- Use `max_marks` field when memo provides more answers than marks available

SECTION C (Essay Questions):
- Extract `topic` (main essay topic like "Consumer Protection Act (CPA)")
- Set `max_marks` (usually 40)
- Build `essay_structure`:
  * `introduction`: List of valid introduction points
  * `body_sections`: List of dicts with flexible structure:
    - {{"sub_topic": "Purpose of the CPA", "points": [...]}}
    - {{"sub_topic": "Impact on Businesses", "positives": [...], "negatives": [...]}}
    - {{"sub_topic": "Consumer Rights", "rights": [...]}}
  * `conclusion`: List of valid conclusion points

IMPORTANT: Extract ALL questions from ALL sections without skipping any."""

    # Step 5: Call Gemini API with structured output schema
    try:
        # Generate clean schema without additionalProperties for Gemini compatibility
        raw_schema = MarkingGuideline.model_json_schema()
        clean_schema = _remove_additional_properties(raw_schema)

        # Build config - only add cached_content if cache is available
        config_dict = {
            'response_mime_type': 'application/json',
            'response_schema': clean_schema,
        }
        if cache_name is not None:
            config_dict['cached_content'] = cache_name

        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(**config_dict)
            )
        except Exception as e:
            if cache_name is not None and _is_cache_expired_error(e):
                global _MEMO_CACHE_NAME
                _MEMO_CACHE_NAME = None
                config_dict = {k: v for k, v in config_dict.items() if k != 'cached_content'}
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_dict)
                )
            else:
                raise

        # Parse structured response
        response_text = response.text
        if response_text is None:
            raise ValueError("Gemini API returned empty response")
        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logging.getLogger(__name__).warning(
                "Gemini response JSON decode failed: %s; response snippet: %s",
                e,
                (response_text[:500] if response_text else "") + "...",
            )
            raise ValueError(f"Invalid JSON in Gemini response: {e}") from e
        try:
            result = MarkingGuideline.model_validate(response_data)
        except ValidationError as e:
            logging.getLogger(__name__).warning(
                "Gemini response schema validation failed: %s; data keys: %s",
                e,
                list(response_data.keys()) if isinstance(response_data, dict) else type(response_data).__name__,
            )
            raise

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
            "cache_eligible": cache_name is not None,
            "cache_hit": cache_hit,
            "cached_tokens": cached_tokens,
            "total_tokens": total_tokens,
            "cached_tokens_saved": cached_tokens
        }

        return result

    except Exception as e:
        # If Gemini extraction fails, create partial result
        if raise_on_partial:
            raise

        # Build partial extraction result with minimal data
        partial_result = MarkingGuideline(
            meta={
                "subject": "[Partial Extraction]",
                "type": "Marking Guideline (Memorandum)",
                "year": 0,
                "session": "Unknown",
                "grade": "Unknown",
                "total_marks": 0
            },
            sections=[],
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

        # Re-raise as PartialMemoExtractionError containing the partial result
        raise PartialMemoExtractionError(
            message=f"Gemini memo extraction failed: {str(e)}",
            partial_result=partial_result,
            original_exception=e
        )


class PartialMemoExtractionError(Exception):
    """Exception raised when extraction partially succeeds with OpenDataLoader but Gemini fails.

    Attributes:
        message: Error message
        partial_result: MarkingGuideline with partial data
        original_exception: The original exception that caused partial extraction
    """

    def __init__(self, message: str, partial_result: MarkingGuideline, original_exception: Exception):
        super().__init__(message)
        self.partial_result = partial_result
        self.original_exception = original_exception


if __name__ == "__main__":
    """CLI entry point for memo extraction.

    Usage:
        python -m app.services.memo_extractor path/to/memo.pdf

    Outputs:
        - Prints JSON to stdout
        - Auto-saves to {input_filename}_memo_result.json alongside input PDF
    """
    import sys
    import os
    import asyncio
    import json
    from app.services.gemini_client import get_gemini_client

    # Check for file path argument
    if len(sys.argv) < 2:
        print("Usage: python -m app.services.memo_extractor path/to/memo.pdf", file=sys.stderr)
        sys.exit(1)

    file_path = sys.argv[1]

    # Check if file exists
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    # Initialize Gemini client
    try:
        client = get_gemini_client()
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Run extraction
    try:
        import hashlib

        result = asyncio.run(extract_memo_data_hybrid(client, file_path))

        # Derive document ID from file content hash (deterministic, deduplication-safe)
        with open(file_path, 'rb') as fh:
            document_id = hashlib.sha256(fh.read()).hexdigest()[:12]

        # Build canonical filename from extracted metadata
        canonical_stem = result.build_canonical_filename(document_id)

        # Convert to JSON
        result_json = result.model_dump()
        json_str = json.dumps(result_json, indent=2, ensure_ascii=False)

        # Print to stdout
        print(json_str)

        # Save JSON with canonical name alongside input PDF
        input_dir = os.path.dirname(file_path) or "."
        json_path = os.path.join(input_dir, f"{canonical_stem}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            f.write(json_str)

        # Rename the input PDF to canonical name
        pdf_path = os.path.join(input_dir, f"{canonical_stem}.pdf")
        os.rename(file_path, pdf_path)

        print(f"\n[PDF renamed to: {pdf_path}]", file=sys.stderr)
        print(f"[JSON saved to:  {json_path}]", file=sys.stderr)

    except PartialMemoExtractionError as e:
        print(f"Error: Partial extraction - {e}", file=sys.stderr)
        print(f"Partial result: {e.partial_result.model_dump_json(indent=2)}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: Extraction failed - {e}", file=sys.stderr)
        sys.exit(1)
