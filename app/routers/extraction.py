"""
PDF extraction API endpoints.

Provides endpoints for uploading PDFs and retrieving extraction results.
"""

import os
import tempfile
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from pydantic import ValidationError

from app.db.extractions import (
    check_duplicate,
    create_extraction,
    get_extraction,
    list_extractions,
    update_extraction_status,
    update_extraction,
)
from app.db.supabase_client import get_supabase_client
from app.models.extraction import ExtractionResult
from app.services.file_validator import validate_pdf
from app.services.gemini_client import get_gemini_client
from app.services.pdf_extractor import extract_pdf_data_hybrid, PartialExtractionError

router = APIRouter(prefix="/api", tags=["extraction"])


@router.post("/extract", status_code=status.HTTP_201_CREATED)
async def extract_pdf(
    file: UploadFile = File(..., description="PDF file to extract"),
    webhook_url: Optional[str] = Form(None, description="Optional webhook URL for completion notification"),
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

        # Step 2: Check for duplicate
        supabase_client = get_supabase_client()
        existing_id = await check_duplicate(supabase_client, file_hash)

        is_retry = False
        retry_count = 0

        if existing_id:
            # Check if existing extraction is partial/failed - if so, retry it
            existing_result = await get_extraction(supabase_client, existing_id)

            if existing_result:
                existing_status = existing_result.get("status")

                # If completed, return existing result
                if existing_status == "completed":
                    return Response(
                        content=str(existing_result),
                        media_type="application/json",
                        status_code=status.HTTP_200_OK,
                        headers={"X-Extraction-ID": existing_id}
                    )

                # If partial or failed, retry the extraction
                if existing_status in ("partial", "failed"):
                    is_retry = True
                    retry_count = existing_result.get("retry_count", 0) + 1

        # Step 3: Save file temporarily to disk
        temp_file_path = os.path.join(
            tempfile.gettempdir(),
            f"pdf_extraction_{uuid.uuid4().hex}_{sanitized_filename}"
        )

        with open(temp_file_path, "wb") as f:
            f.write(content)

        # Step 4: Extract PDF data using hybrid pipeline
        gemini_client = get_gemini_client()

        extraction_result = None
        extraction_status = 'completed'
        error_message = None

        try:
            extraction_result = await extract_pdf_data_hybrid(
                client=gemini_client,
                file_path=temp_file_path,
            )
        except PartialExtractionError as e:
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
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Processing error: {str(e)}"
            )

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
            if is_retry and existing_id:
                # Update existing extraction with retry results
                await update_extraction(
                    supabase_client,
                    existing_id,
                    extraction_result,
                    status=extraction_status,
                    error_message=error_message,
                    retry_count=retry_count
                )
                extraction_id = existing_id
            else:
                # New extraction
                extraction_id = await create_extraction(
                    supabase_client,
                    extraction_result,
                    file_info,
                    status=extraction_status
                )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error: {str(e)}"
            )

        # Step 6: Return extraction result
        # Use 206 Partial Content for partial extractions, 201 for complete
        response_status = status.HTTP_206_PARTIAL_CONTENT if extraction_status == 'partial' else status.HTTP_201_CREATED

        # Prepare headers for response (including routing information for logging)
        response_headers = {
            "X-Extraction-ID": extraction_id,
        }

        # Add routing information to headers for logging middleware
        if extraction_result and extraction_result.processing_metadata:
            processing_method = extraction_result.processing_metadata.get("method")
            if processing_method:
                response_headers["X-Processing-Method"] = processing_method

            opendataloader_quality = extraction_result.processing_metadata.get("opendataloader_quality")
            if opendataloader_quality is not None:
                response_headers["X-Quality-Score"] = str(opendataloader_quality)

        return Response(
            content=extraction_result.model_dump_json(),
            media_type="application/json",
            status_code=response_status,
            headers=response_headers
        )

    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                # Silently ignore cleanup errors
                pass


@router.get("/extractions/{extraction_id}", status_code=status.HTTP_200_OK)
async def get_extraction_by_id(extraction_id: str) -> Response:
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
    import json
    return Response(
        content=json.dumps(result),
        media_type="application/json",
        status_code=status.HTTP_200_OK
    )


@router.get("/extractions", status_code=status.HTTP_200_OK)
async def list_all_extractions(
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

    import json
    return Response(
        content=json.dumps(response_data, default=str),  # default=str handles UUID/datetime
        media_type="application/json",
        status_code=status.HTTP_200_OK
    )


@router.get("/extractions/{extraction_id}/bounding-boxes", status_code=status.HTTP_200_OK)
async def get_bounding_boxes(extraction_id: str) -> Response:
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

    import json
    return Response(
        content=json.dumps(bounding_boxes),
        media_type="application/json",
        status_code=status.HTTP_200_OK
    )


@router.get("/extractions/{extraction_id}/elements/{element_id}", status_code=status.HTTP_200_OK)
async def get_element(extraction_id: str, element_id: str) -> Response:
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

    import json
    return Response(
        content=json.dumps(element_data),
        media_type="application/json",
        status_code=status.HTTP_200_OK
    )


@router.post("/extractions/{extraction_id}/retry", status_code=status.HTTP_200_OK)
async def retry_extraction(extraction_id: str) -> Response:
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
