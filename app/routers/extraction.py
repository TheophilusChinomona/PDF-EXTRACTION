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
)
from app.db.supabase_client import get_supabase_client
from app.models.extraction import ExtractionResult
from app.services.file_validator import validate_pdf
from app.services.gemini_client import get_gemini_client
from app.services.pdf_extractor import extract_pdf_data_hybrid

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

        if existing_id:
            # Return existing extraction result
            existing_result = await get_extraction(supabase_client, existing_id)

            if existing_result:
                return Response(
                    content=str(existing_result),
                    media_type="application/json",
                    status_code=status.HTTP_200_OK,
                    headers={"X-Extraction-ID": existing_id}
                )

        # Step 3: Save file temporarily to disk
        temp_file_path = os.path.join(
            tempfile.gettempdir(),
            f"pdf_extraction_{uuid.uuid4().hex}_{sanitized_filename}"
        )

        with open(temp_file_path, "wb") as f:
            f.write(content)

        # Step 4: Extract PDF data using hybrid pipeline
        gemini_client = get_gemini_client()

        try:
            extraction_result = await extract_pdf_data_hybrid(
                client=gemini_client,
                file_path=temp_file_path,
            )
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

        # Step 5: Store result in database
        file_info = {
            "file_name": sanitized_filename,
            "file_size_bytes": len(content),
            "file_hash": file_hash,
            "webhook_url": webhook_url,
        }

        try:
            extraction_id = await create_extraction(
                supabase_client,
                extraction_result,
                file_info
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error: {str(e)}"
            )

        # Step 6: Return extraction result
        return Response(
            content=extraction_result.model_dump_json(),
            media_type="application/json",
            status_code=status.HTTP_201_CREATED,
            headers={"X-Extraction-ID": extraction_id}
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
