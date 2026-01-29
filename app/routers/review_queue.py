"""
Review queue API endpoints.

Provides endpoints for managing manual review queue for failed extractions.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.db.review_queue import get_pending_reviews, resolve_review, get_review_by_id
from app.db.supabase_client import get_supabase_client
from app.middleware.rate_limit import get_limiter

router = APIRouter(prefix="/api", tags=["review-queue"])
limiter = get_limiter()


class ResolveReviewRequest(BaseModel):
    """Request model for resolving a review."""
    resolution: str = Field(..., description="Resolution status: fixed, false_positive, or unable_to_process")
    reviewer_notes: Optional[str] = Field(None, description="Optional human reviewer notes and actions taken")


@router.get("/review-queue", status_code=status.HTTP_200_OK)
@limiter.limit("100/minute")  # type: ignore[untyped-decorator]
async def get_review_queue(
    request: Request,
    limit: int = 50,
    offset: int = 0,
) -> Response:
    """
    Retrieve pending review queue items (not yet resolved).

    This endpoint returns a paginated list of failed extractions that
    have exceeded the retry limit and require manual review. Items are
    ordered by queued_at timestamp (newest first).

    Args:
        limit: Maximum number of records to return (default: 50, max: 100)
        offset: Number of records to skip for pagination (default: 0)

    Returns:
        200: List of pending review queue items with pagination metadata
        400: Invalid parameters (limit or offset)
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

    # Retrieve pending reviews from database
    supabase_client = get_supabase_client()

    try:
        results = await get_pending_reviews(
            supabase_client,
            limit=limit,
            offset=offset
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


@router.post("/review-queue/{review_id}/resolve", status_code=status.HTTP_200_OK)
@limiter.limit("100/minute")  # type: ignore[untyped-decorator]
async def resolve_review_item(
    request: Request,
    review_id: str,
    body: ResolveReviewRequest
) -> Response:
    """
    Mark a review queue item as resolved.

    This endpoint allows data quality managers to mark a failed extraction
    as reviewed and provide resolution status and optional notes.

    Args:
        review_id: UUID of the review queue record
        body: Resolution request with status and optional notes

    Returns:
        200: Review successfully resolved
        400: Invalid UUID format or resolution status
        404: Review queue item not found
        500: Database error

    Raises:
        HTTPException: Various error conditions with appropriate status codes
    """
    # Validate UUID format
    try:
        uuid.UUID(review_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID format: {review_id}"
        )

    # Resolve the review
    supabase_client = get_supabase_client()

    try:
        result = await resolve_review(
            supabase_client,
            review_id,
            resolution=body.resolution,
            reviewer_notes=body.reviewer_notes
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Check if item not found
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Review queue item not found: {review_id}"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

    # Return updated review record
    import json
    return Response(
        content=json.dumps(result, default=str),
        media_type="application/json",
        status_code=status.HTTP_200_OK
    )


@router.get("/review-queue/{review_id}", status_code=status.HTTP_200_OK)
@limiter.limit("100/minute")  # type: ignore[untyped-decorator]
async def get_review_item(request: Request, review_id: str) -> Response:
    """
    Retrieve a specific review queue item by ID.

    This endpoint fetches details of a specific review queue item,
    including the associated extraction metadata.

    Args:
        review_id: UUID of the review queue record

    Returns:
        200: Review queue item found
        400: Invalid UUID format
        404: Review queue item not found
        500: Database error

    Raises:
        HTTPException: Various error conditions with appropriate status codes
    """
    # Validate UUID format
    try:
        uuid.UUID(review_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID format: {review_id}"
        )

    # Retrieve review from database
    supabase_client = get_supabase_client()

    try:
        result = await get_review_by_id(supabase_client, review_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review queue item not found: {review_id}"
        )

    # Return review record as JSON
    import json
    return Response(
        content=json.dumps(result, default=str),
        media_type="application/json",
        status_code=status.HTTP_200_OK
    )
