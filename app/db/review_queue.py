"""Database functions for managing review queue records.

This module provides CRUD operations for the review queue in Supabase,
including adding failed extractions to the queue, retrieving pending items,
and resolving reviewed items.
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from supabase import Client


async def add_to_review_queue(
    client: Client,
    extraction_id: str,
    error_type: str,
    error_message: str,
    processing_method: Optional[str] = None,
    quality_score: Optional[float] = None,
    retry_count: int = 0,
) -> str:
    """Add a failed extraction to the manual review queue.

    Args:
        client: Supabase client instance
        extraction_id: UUID of the failed extraction
        error_type: Classification of error (e.g., 'gemini_api_error', 'validation_error')
        error_message: Detailed error message for debugging
        processing_method: Method that was attempted ('hybrid' or 'vision_fallback')
        quality_score: OpenDataLoader quality score if available
        retry_count: Number of retries before queuing for review

    Returns:
        str: UUID of created review queue record

    Raises:
        ValueError: If required fields are invalid
        Exception: If database insertion fails
    """
    # Validate UUID format
    try:
        UUID(extraction_id)
    except ValueError:
        raise ValueError(f"Invalid extraction_id UUID format: {extraction_id}")

    # Prepare database record
    record = {
        'extraction_id': extraction_id,
        'error_type': error_type,
        'error_message': error_message,
        'processing_method': processing_method,
        'quality_score': quality_score,
        'retry_count': retry_count,
    }

    try:
        response = client.table('review_queue').insert(record).execute()
        if not response.data or len(response.data) == 0:
            raise Exception("Insert returned no data")
        return str(response.data[0]['id'])
    except Exception as e:
        raise Exception(f"Failed to add to review queue: {str(e)}")


async def get_pending_reviews(
    client: Client,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Retrieve pending review queue items (not yet resolved).

    Args:
        client: Supabase client instance
        limit: Maximum number of records to return (default: 50, max: 100)
        offset: Number of records to skip for pagination (default: 0)

    Returns:
        List[Dict]: List of pending review queue records with extraction data

    Raises:
        ValueError: If limit or offset are invalid
        Exception: If database query fails
    """
    # Validate pagination parameters
    if limit < 1 or limit > 100:
        raise ValueError("Limit must be between 1 and 100")
    if offset < 0:
        raise ValueError("Offset must be non-negative")

    try:
        # Query review_queue joined with extractions for file context
        response = (
            client.table('review_queue')
            .select('''
                id,
                extraction_id,
                error_type,
                error_message,
                processing_method,
                quality_score,
                retry_count,
                queued_at,
                extractions!inner (
                    file_name,
                    file_size_bytes,
                    file_hash,
                    status
                )
            ''')
            .is_('resolution', 'null')
            .order('queued_at', desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        return response.data if response.data else []
    except Exception as e:
        raise Exception(f"Failed to retrieve pending reviews: {str(e)}")


async def resolve_review(
    client: Client,
    review_id: str,
    resolution: str,
    reviewer_notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Mark a review queue item as resolved.

    Args:
        client: Supabase client instance
        review_id: UUID of the review queue record
        resolution: Resolution status ('fixed', 'false_positive', 'unable_to_process')
        reviewer_notes: Optional human reviewer notes and actions taken

    Returns:
        Dict: Updated review queue record

    Raises:
        ValueError: If review_id or resolution are invalid
        Exception: If database update fails
    """
    # Validate UUID format
    try:
        UUID(review_id)
    except ValueError:
        raise ValueError(f"Invalid review_id UUID format: {review_id}")

    # Validate resolution
    valid_resolutions = ['fixed', 'false_positive', 'unable_to_process']
    if resolution not in valid_resolutions:
        raise ValueError(f"Invalid resolution '{resolution}'. Must be one of: {', '.join(valid_resolutions)}")

    # Prepare update
    import datetime
    update_data = {
        'resolution': resolution,
        'reviewer_notes': reviewer_notes,
        'reviewed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    try:
        response = (
            client.table('review_queue')
            .update(update_data)
            .eq('id', review_id)
            .execute()
        )

        if not response.data or len(response.data) == 0:
            raise Exception("Review queue item not found")

        result: Dict[str, Any] = response.data[0]
        return result
    except Exception as e:
        raise Exception(f"Failed to resolve review: {str(e)}")


async def get_review_by_id(
    client: Client,
    review_id: str,
) -> Optional[Dict[str, Any]]:
    """Retrieve a review queue record by ID.

    Args:
        client: Supabase client instance
        review_id: UUID string of the review queue record

    Returns:
        Optional[Dict]: Review queue record with extraction data, or None if not found

    Raises:
        ValueError: If review_id is invalid
        Exception: If database query fails
    """
    # Validate UUID format
    try:
        UUID(review_id)
    except ValueError:
        raise ValueError(f"Invalid review_id UUID format: {review_id}")

    try:
        response = (
            client.table('review_queue')
            .select('''
                id,
                extraction_id,
                error_type,
                error_message,
                processing_method,
                quality_score,
                retry_count,
                resolution,
                reviewer_notes,
                queued_at,
                reviewed_at,
                extractions!inner (
                    file_name,
                    file_size_bytes,
                    file_hash,
                    status
                )
            ''')
            .eq('id', review_id)
            .single()
            .execute()
        )

        return response.data if response.data else None
    except Exception as e:
        # Single() raises if not found
        if "not found" in str(e).lower():
            return None
        raise Exception(f"Failed to retrieve review: {str(e)}")
