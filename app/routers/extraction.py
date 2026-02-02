"""
PDF extraction API endpoints.

Provides endpoints for uploading PDFs and retrieving extraction results.
"""

import json
import logging
import os
import tempfile
import uuid
from typing import Any, Optional, Union

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status
from pydantic import ValidationError

from app.db.extractions import (
    check_duplicate,
    check_duplicate_any,
    create_extraction,
    get_extraction,
    list_extractions,
    update_extraction_status,
    update_extraction,
)
from app.db.memo_extractions import (
    check_memo_duplicate,
    create_memo_extraction,
    get_memo_extraction,
    update_memo_extraction_status,
    update_memo_extraction,
)
from app.db.review_queue import add_to_review_queue
from app.db.supabase_client import get_supabase_client
from app.middleware.rate_limit import get_limiter
from app.models.extraction import DocumentStructure, FullExamPaper
from app.models.memo_extraction import MarkingGuideline
from app.services.document_classifier import classify_document
from app.services.file_validator import validate_pdf
from app.services.gemini_client import get_gemini_client
from app.services.opendataloader_extractor import extract_pdf_structure
from app.services.pdf_extractor import extract_pdf_data_hybrid, PartialExtractionError
from app.services.memo_extractor import extract_memo_data_hybrid, PartialMemoExtractionError
from app.services.webhook_sender import send_extraction_completed_webhook

router = APIRouter(prefix="/api", tags=["extraction"])
limiter = get_limiter()
logger = logging.getLogger(__name__)


@router.post("/extract", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def extract_pdf(
    request: Request,
    file: UploadFile = File(..., description="PDF file to extract"),
    webhook_url: Optional[str] = Form(None, description="Optional webhook URL for completion notification"),
    doc_type: Optional[str] = Form(None, description="Document type: 'question_paper' or 'memo'. If omitted, auto-detected."),
) -> Response:
    """
    Extract structured data from a PDF file using hybrid pipeline.

    This endpoint:
    1. Validates the uploaded PDF file
    2. Checks for duplicates using file hash
    3. Extracts data using OpenDataLoader + Gemini hybrid pipeline
    4. Stores results in database
    5. Returns extraction result with UUID in X-Extraction-ID header

    Args:
        file: PDF file to process (max 200MB)
        webhook_url: Optional HTTPS URL to receive completion notification

    Returns:
        201: Extraction completed successfully
        400: Invalid file or validation error
        413: File too large (>200MB)
        422: Corrupted PDF file
        500: Processing error

    Raises:
        HTTPException: Various error conditions with appropriate status codes
    """
    temp_file_path: Optional[str] = None

    try:
        # Step 0: Validate doc_type (if explicitly provided)
        classification_method: Optional[str] = None
        precomputed_doc_structure: Optional[DocumentStructure] = None

        if doc_type is not None and doc_type not in ('question_paper', 'memo'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid doc_type '{doc_type}'. Must be 'question_paper' or 'memo'"
            )

        if doc_type is not None:
            classification_method = "user_provided"

        # Step 1: Validate PDF file
        try:
            content, file_hash, sanitized_filename = await validate_pdf(file)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Corrupted or invalid PDF: {str(e)}"
            )

        # Step 1a: Cross-table duplicate check (both extractions and memo_extractions)
        supabase_client = get_supabase_client()
        existing_any = await check_duplicate_any(supabase_client, file_hash)
        if existing_any:
            table_name, existing_id = existing_any
            if table_name == "extractions":
                existing_result = await get_extraction(supabase_client, existing_id)
            else:
                existing_result = await get_memo_extraction(supabase_client, existing_id)
            if existing_result and existing_result.get("status") == "completed":
                return Response(
                    content=json.dumps(existing_result),
                    media_type="application/json",
                    status_code=status.HTTP_200_OK,
                    headers={"X-Extraction-ID": existing_id},
                )

        # Step 1b: Auto-classify if doc_type not provided
        if doc_type is None:
            # Write temp file early so we can run OpenDataLoader for classification
            with tempfile.NamedTemporaryFile(
                prefix="pdf_extraction_", delete=False, suffix=".pdf"
            ) as tmp:
                tmp.write(content)
                temp_file_path = tmp.name

            # Extract structure (reused later to avoid duplicate work)
            precomputed_doc_structure = extract_pdf_structure(temp_file_path)

            # Run classifier cascade
            gemini_client = get_gemini_client()
            classification = classify_document(
                filename=sanitized_filename,
                markdown_text=precomputed_doc_structure.markdown,
                gemini_client=gemini_client,
            )
            doc_type = classification.doc_type
            classification_method = classification.method

        # Step 2: Check for duplicate in target table (route based on doc_type)
        if doc_type == 'memo':
            existing_id = await check_memo_duplicate(supabase_client, file_hash)
        else:
            existing_id = await check_duplicate(supabase_client, file_hash)

        is_retry = False
        retry_count = 0

        if existing_id:
            # Check if existing extraction is partial/failed - if so, retry it
            if doc_type == 'memo':
                existing_result = await get_memo_extraction(supabase_client, existing_id)
            else:
                existing_result = await get_extraction(supabase_client, existing_id)

            if existing_result:
                existing_status = existing_result.get("status")

                # If completed, return existing result
                if existing_status == "completed":
                    return Response(
                        content=json.dumps(existing_result),
                        media_type="application/json",
                        status_code=status.HTTP_200_OK,
                        headers={"X-Extraction-ID": existing_id}
                    )

                # If partial or failed, retry the extraction
                if existing_status in ("partial", "failed"):
                    is_retry = True
                    retry_count = existing_result.get("retry_count", 0) + 1

        # Step 3: Save file temporarily to disk (skip if already written during classification)
        if temp_file_path is None:
            with tempfile.NamedTemporaryFile(
                prefix="pdf_extraction_", delete=False, suffix=".pdf"
            ) as tmp:
                tmp.write(content)
                temp_file_path = tmp.name

        # Step 4: Extract PDF data using hybrid pipeline (route based on doc_type)
        # get_gemini_client() returns a singleton, so this is cheap even if called twice
        gemini_client = get_gemini_client()

        extraction_result: Optional[Union[FullExamPaper, MarkingGuideline]] = None
        extraction_status = 'completed'
        error_message = None

        try:
            if doc_type == 'memo':
                extraction_result = await extract_memo_data_hybrid(
                    client=gemini_client,
                    file_path=temp_file_path,
                    doc_structure=precomputed_doc_structure,
                )
            else:
                extraction_result = await extract_pdf_data_hybrid(
                    client=gemini_client,
                    file_path=temp_file_path,
                    doc_structure=precomputed_doc_structure,
                )
        except (PartialExtractionError, PartialMemoExtractionError) as e:
            # Gemini failed but OpenDataLoader succeeded - save partial result
            extraction_result = e.partial_result
            extraction_status = 'partial'
            error_message = str(e.original_exception)
        except ValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"PDF extraction failed validation: {str(e)}"
            )
        except Exception as e:
            # If retry count exceeds limit, set status to failed and prepare for review queue
            if retry_count > 5:
                extraction_status = 'failed'
                error_message = str(e)
                # extraction_result remains None for complete failures
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Processing error: {str(e)}"
                )

        # Step 4b: Inject classification metadata into extraction result
        if extraction_result is not None and classification_method:
            extraction_result.processing_metadata["classification_method"] = classification_method
            extraction_result.processing_metadata["doc_type"] = doc_type

        # Step 5: Store result in database (including partial results)
        file_info = {
            "file_name": sanitized_filename,
            "file_size_bytes": len(content),
            "file_hash": file_hash,
            "webhook_url": webhook_url,
            "error_message": error_message,
            "retry_count": retry_count,
        }

        try:
            # Handle failed extractions (no extraction_result)
            if extraction_status == 'failed' and extraction_result is None:
                if is_retry and existing_id:
                    # Update existing extraction to failed status (route based on doc_type)
                    if doc_type == 'memo':
                        await update_memo_extraction_status(
                            supabase_client,
                            existing_id,
                            status='failed',
                            error=error_message
                        )
                    else:
                        await update_extraction_status(
                            supabase_client,
                            existing_id,
                            status='failed',
                            error=error_message
                        )
                    extraction_id = existing_id
                else:
                    # For new failed extraction, we need a minimal ExtractionResult
                    # This shouldn't normally happen, but handle it by raising the error
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Processing error: {error_message}"
                    )
            elif extraction_result is not None:
                # Normal flow: we have extraction_result (completed or partial)
                if is_retry and existing_id:
                    # Update existing extraction with retry results (route based on doc_type)
                    if doc_type == 'memo':
                        await update_memo_extraction(
                            supabase_client,
                            existing_id,
                            extraction_result,  # type: ignore[arg-type]
                            status=extraction_status,
                            error_message=error_message,
                            retry_count=retry_count
                        )
                    else:
                        await update_extraction(
                            supabase_client,
                            existing_id,
                            extraction_result,  # type: ignore[arg-type]
                            status=extraction_status,
                            error_message=error_message,
                            retry_count=retry_count
                        )
                    extraction_id = existing_id
                else:
                    # New extraction (route based on doc_type)
                    if doc_type == 'memo':
                        extraction_id = await create_memo_extraction(
                            supabase_client,
                            extraction_result,  # type: ignore[arg-type]
                            file_info,
                            status=extraction_status
                        )
                    else:
                        extraction_id = await create_extraction(
                            supabase_client,
                            extraction_result,  # type: ignore[arg-type]
                            file_info,
                            status=extraction_status
                        )
            else:
                # Should not reach here
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Internal error: invalid extraction state"
                )

            # Add to review queue if retry count exceeded limit
            if retry_count > 5 and extraction_status == 'failed':
                # Determine error type from exception
                error_type = "processing_error"
                if error_message and "gemini" in error_message.lower():
                    error_type = "gemini_api_error"
                elif error_message and "validation" in error_message.lower():
                    error_type = "validation_error"

                # Get processing metadata if available
                processing_method_val = None
                quality_score_val = None
                if extraction_result and extraction_result.processing_metadata:
                    processing_method_val = extraction_result.processing_metadata.get("method")
                    quality_score_val = extraction_result.processing_metadata.get("opendataloader_quality")

                await add_to_review_queue(
                    supabase_client,
                    extraction_id,
                    error_type=error_type,
                    error_message=error_message or "Unknown error",
                    processing_method=processing_method_val,
                    quality_score=quality_score_val,
                    retry_count=retry_count
                )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error: {str(e)}"
            )

        # Step 6: Send webhook if configured
        if webhook_url:
            # Prepare webhook summary data
            webhook_data: dict[str, Any] = {
                'file_name': sanitized_filename,
                'status': extraction_status,
            }
            if extraction_result:
                # Add metadata based on doc_type
                if doc_type == 'memo' and isinstance(extraction_result, MarkingGuideline):
                    # Memo metadata from meta dict
                    webhook_data['subject'] = extraction_result.meta.get('subject')
                    webhook_data['year'] = extraction_result.meta.get('year')
                    webhook_data['session'] = extraction_result.meta.get('session')
                    webhook_data['grade'] = extraction_result.meta.get('grade')
                elif isinstance(extraction_result, FullExamPaper):
                    # Exam paper metadata
                    webhook_data['subject'] = extraction_result.subject
                    webhook_data['language'] = extraction_result.language
                    webhook_data['year'] = extraction_result.year
                    webhook_data['session'] = extraction_result.session
                    webhook_data['grade'] = extraction_result.grade

                # Add processing method (both types have this)
                processing_method = extraction_result.processing_metadata.get('method')
                if processing_method:
                    webhook_data['processing_method'] = processing_method

            # Fire and forget - don't wait for webhook
            import asyncio
            asyncio.create_task(
                send_extraction_completed_webhook(
                    webhook_url,
                    extraction_id,
                    extraction_status,
                    webhook_data
                )
            )

        # Step 7: Return extraction result
        # Use appropriate status code based on extraction status
        if extraction_status == 'failed':
            response_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        elif extraction_status == 'partial':
            response_status = status.HTTP_206_PARTIAL_CONTENT
        else:
            response_status = status.HTTP_201_CREATED

        # Prepare headers for response (including routing information for logging)
        response_headers = {
            "X-Extraction-ID": extraction_id,
            "X-Doc-Type": doc_type,
        }
        if classification_method:
            response_headers["X-Doc-Type-Method"] = classification_method

        # Add routing information to headers for logging middleware
        if extraction_result and extraction_result.processing_metadata:
            processing_method = extraction_result.processing_metadata.get("method")
            if processing_method:
                response_headers["X-Processing-Method"] = processing_method

            opendataloader_quality = extraction_result.processing_metadata.get("opendataloader_quality")
            if opendataloader_quality is not None:
                response_headers["X-Quality-Score"] = str(opendataloader_quality)

        # Build response content
        if extraction_result is not None:
            response_content = extraction_result.model_dump_json()
        else:
            # Failed extraction with no result
            response_content = json.dumps({
                "status": "failed",
                "error": error_message or "Extraction failed after maximum retries",
                "extraction_id": extraction_id,
                "queued_for_review": retry_count > 5
            })

        return Response(
            content=response_content,
            media_type="application/json",
            status_code=response_status,
            headers=response_headers
        )

    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError as e:
                logger.warning(
                    "Failed to remove temp file %s: %s",
                    temp_file_path,
                    e,
                    exc_info=True,
                )


@router.get("/extractions/{extraction_id}", status_code=status.HTTP_200_OK)
@limiter.limit("100/minute")  # type: ignore[untyped-decorator]
async def get_extraction_by_id(request: Request, extraction_id: str) -> Response:
    """
    Retrieve extraction result by ID.

    This endpoint fetches a previously completed extraction result
    by its UUID, including all extracted data, bounding boxes, and
    processing metadata.

    Args:
        extraction_id: UUID of the extraction to retrieve

    Returns:
        200: Extraction result found
        400: Invalid UUID format
        404: Extraction not found
        500: Database error

    Raises:
        HTTPException: Various error conditions with appropriate status codes
    """
    # Validate UUID format
    try:
        uuid.UUID(extraction_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID format: {extraction_id}"
        )

    # Retrieve extraction from database
    supabase_client = get_supabase_client()

    try:
        result = await get_extraction(supabase_client, extraction_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extraction not found: {extraction_id}"
        )

    # Return extraction result as JSON
    return Response(
        content=json.dumps(result),
        media_type="application/json",
        status_code=status.HTTP_200_OK
    )


@router.get("/extractions", status_code=status.HTTP_200_OK)
@limiter.limit("100/minute")  # type: ignore[untyped-decorator]
async def list_all_extractions(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    status_filter: Optional[str] = None
) -> Response:
    """
    List extraction records with pagination and optional status filtering.

    This endpoint returns a paginated list of extraction records,
    ordered by creation date (newest first). Results can be filtered
    by status.

    Args:
        limit: Maximum number of records to return (default: 50, max: 100)
        offset: Number of records to skip for pagination (default: 0)
        status_filter: Optional status filter ('pending', 'completed', 'failed', 'partial')

    Returns:
        200: List of extractions with pagination metadata
        400: Invalid parameters (limit, offset, or status)
        500: Database error

    Raises:
        HTTPException: Various error conditions with appropriate status codes
    """
    # Validate pagination parameters
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit must be between 1 and 100"
        )

    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Offset must be non-negative"
        )

    # Retrieve extractions from database
    supabase_client = get_supabase_client()

    try:
        results = await list_extractions(
            supabase_client,
            limit=limit,
            offset=offset,
            status=status_filter
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

    # Build response with pagination metadata
    response_data = {
        "data": results,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "count": len(results),
            "has_more": len(results) == limit
        }
    }

    return Response(
        content=json.dumps(response_data, default=str),  # default=str handles UUID/datetime
        media_type="application/json",
        status_code=status.HTTP_200_OK
    )


@router.get("/extractions/{extraction_id}/bounding-boxes", status_code=status.HTTP_200_OK)
@limiter.limit("100/minute")  # type: ignore[untyped-decorator]
async def get_bounding_boxes(request: Request, extraction_id: str) -> Response:
    """
    Retrieve all bounding boxes for an extraction.

    This endpoint returns all bounding box coordinates for elements
    in the extracted PDF, keyed by element_id. Useful for implementing
    citation features that need to link extracted content to specific
    locations in the PDF.

    Args:
        extraction_id: UUID of the extraction

    Returns:
        200: Dictionary of bounding boxes (element_id -> bbox)
        400: Invalid UUID format
        404: Extraction not found
        500: Database error

    Raises:
        HTTPException: Various error conditions with appropriate status codes
    """
    # Validate UUID format
    try:
        uuid.UUID(extraction_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID format: {extraction_id}"
        )

    # Retrieve extraction from database
    supabase_client = get_supabase_client()

    try:
        result = await get_extraction(supabase_client, extraction_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extraction not found: {extraction_id}"
        )

    # Extract bounding_boxes from result
    bounding_boxes = result.get("bounding_boxes", {})

    return Response(
        content=json.dumps(bounding_boxes),
        media_type="application/json",
        status_code=status.HTTP_200_OK
    )


@router.get("/extractions/{extraction_id}/elements/{element_id}", status_code=status.HTTP_200_OK)
@limiter.limit("100/minute")  # type: ignore[untyped-decorator]
async def get_element(request: Request, extraction_id: str, element_id: str) -> Response:
    """
    Retrieve a specific element with its bounding box and content.

    This endpoint returns detailed information about a specific element
    (heading, paragraph, table, etc.) including its bounding box coordinates
    and associated content. Useful for implementing precise citation features.

    Args:
        extraction_id: UUID of the extraction
        element_id: ID of the element (from bounding_boxes keys)

    Returns:
        200: Element data with bounding box, type, and content
        400: Invalid UUID format
        404: Extraction or element not found
        500: Database error

    Raises:
        HTTPException: Various error conditions with appropriate status codes
    """
    # Validate UUID format
    try:
        uuid.UUID(extraction_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID format: {extraction_id}"
        )

    # Retrieve extraction from database
    supabase_client = get_supabase_client()

    try:
        result = await get_extraction(supabase_client, extraction_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extraction not found: {extraction_id}"
        )

    # Extract bounding_boxes and find the specific element
    bounding_boxes = result.get("bounding_boxes", {})

    if element_id not in bounding_boxes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Element not found: {element_id}"
        )

    # Get the bounding box for this element
    bbox = bounding_boxes[element_id]

    # Try to find associated content from sections, tables, or other structured data
    element_content = None
    element_type = "unknown"

    # Check sections for matching element
    sections = result.get("sections", [])
    for section in sections:
        if isinstance(section, dict):
            section_bbox = section.get("bbox")
            if section_bbox and section_bbox == bbox:
                element_content = {
                    "heading": section.get("heading"),
                    "content": section.get("content"),
                    "page_number": section.get("page_number")
                }
                element_type = "section"
                break

    # Check tables if not found in sections
    if element_content is None:
        tables = result.get("tables", [])
        for table in tables:
            if isinstance(table, dict):
                table_bbox = table.get("bbox")
                if table_bbox and table_bbox == bbox:
                    element_content = {
                        "caption": table.get("caption"),
                        "page_number": table.get("page_number"),
                        "data": table.get("data")
                    }
                    element_type = "table"
                    break

    # If no specific content found, return just the bounding box
    if element_content is None:
        element_content = {}
        element_type = "element"

    # Build response
    element_data = {
        "element_id": element_id,
        "element_type": element_type,
        "bounding_box": bbox,
        "content": element_content
    }

    return Response(
        content=json.dumps(element_data),
        media_type="application/json",
        status_code=status.HTTP_200_OK
    )


@router.post("/extractions/{extraction_id}/retry", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def retry_extraction(request: Request, extraction_id: str) -> Response:
    """
    Retry a partial or failed extraction.

    Note: This endpoint requires re-uploading the original PDF file.
    For automatic retry, simply re-upload the same file to POST /extract.
    The system will detect the duplicate by file hash and automatically
    retry partial/failed extractions, incrementing the retry count.

    Args:
        extraction_id: UUID of the extraction to retry

    Returns:
        422: Instructs user to re-upload file to POST /extract

    Raises:
        HTTPException: Indicates retry requires file re-upload
    """
    # Validate UUID format
    try:
        uuid.UUID(extraction_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID format: {extraction_id}"
        )

    # For MVP: retry requires file re-upload
    # The POST /extract endpoint handles retry logic automatically
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "message": "Retry requires file re-upload",
            "instructions": "Upload the same PDF file to POST /api/extract. The system will detect the duplicate by file hash and automatically retry the extraction, updating this record.",
            "extraction_id": extraction_id
        }
    )
