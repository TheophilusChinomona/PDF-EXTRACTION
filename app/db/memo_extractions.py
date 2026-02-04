"""Database functions for managing memo extraction records.

This module provides CRUD operations for memo (marking guideline) extraction
results in Supabase, including insertion, retrieval, deduplication, and status updates.

Mirrors the patterns from extractions.py but targets the memo_extractions table.
"""

import asyncio
from typing import Optional, List, Dict, Any
from uuid import UUID
from supabase import Client

from app.models.memo_extraction import MarkingGuideline


async def create_memo_extraction(
    client: Client,
    data: MarkingGuideline,
    file_info: Dict[str, Any],
    status: str = 'completed'
) -> str:
    """Insert a new memo extraction result into the database.

    Args:
        client: Supabase client instance
        data: Memo extraction result with all extracted data
        file_info: File metadata dictionary with keys:
            - file_name (str): Sanitized filename
            - file_size_bytes (int): File size in bytes
            - file_hash (str): SHA-256 hash for deduplication
            - processing_time_seconds (float, optional): Processing duration
            - webhook_url (str, optional): Webhook notification URL
            - error_message (str, optional): Error details for partial/failed status
        status: Extraction status ('completed', 'partial', 'failed', 'pending')

    Returns:
        str: UUID of created memo extraction record

    Raises:
        ValueError: If required file_info fields are missing or status is invalid
        Exception: If database insertion fails
    """
    # Validate required file_info fields
    required_fields = ['file_name', 'file_size_bytes', 'file_hash']
    missing = [f for f in required_fields if f not in file_info]
    if missing:
        raise ValueError(f"Missing required file_info fields: {', '.join(missing)}")

    # Validate status
    valid_statuses = ['pending', 'completed', 'failed', 'partial']
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}")

    # Extract processing metadata
    proc_meta = data.processing_metadata
    processing_method = proc_meta.get('method', 'hybrid')
    quality_score = proc_meta.get('opendataloader_quality', 0.0)
    cost_estimate = proc_meta.get('cost_estimate_usd', 0.0)

    # Extract memo metadata from meta dict
    meta = data.meta
    subject = meta.get('subject', 'Unknown')
    year = meta.get('year', 0)
    session = meta.get('session', 'Unknown')
    grade = meta.get('grade', 'Unknown')
    total_marks = meta.get('total_marks', 0)

    # Prepare database record for memo
    record = {
        'file_name': file_info['file_name'],
        'file_size_bytes': file_info['file_size_bytes'],
        'file_hash': file_info['file_hash'],
        'status': status,
        'processing_method': processing_method,
        'quality_score': quality_score,
        # Memo metadata
        'subject': subject,
        'year': year,
        'session': session,
        'grade': grade,
        'total_marks': total_marks,
        # Sections data as JSON
        'sections': [s.model_dump() for s in data.sections],
        # Processing info
        'processing_metadata': data.processing_metadata,
        'processing_time_seconds': file_info.get('processing_time_seconds'),
        'cost_estimate_usd': cost_estimate,
        'webhook_url': file_info.get('webhook_url'),
        'retry_count': file_info.get('retry_count', 0),
        'error_message': file_info.get('error_message')
    }

    # Optional: link back to scraped_files for end-to-end traceability
    if file_info.get('scraped_file_id'):
        record['scraped_file_id'] = file_info['scraped_file_id']

    try:
        response = await asyncio.to_thread(
            lambda: client.table('memo_extractions').insert(record).execute()
        )
        if not response.data or len(response.data) == 0:
            raise RuntimeError("Insert returned no data")
        return str(response.data[0]['id'])
    except Exception as e:
        err_msg = str(e).lower()
        if "23505" in err_msg or "unique" in err_msg or "duplicate" in err_msg:
            existing = await _get_memo_id_by_file_hash(client, file_info['file_hash'])
            if existing:
                return existing
        raise RuntimeError(f"Failed to insert memo extraction: {str(e)}") from e


async def _get_memo_id_by_file_hash(client: Client, file_hash: str) -> Optional[str]:
    """Return memo extraction id for file_hash where status in ('completed','pending'), or None."""
    try:
        response = await asyncio.to_thread(
            lambda: client.table('memo_extractions')
            .select('id')
            .eq('file_hash', file_hash)
            .in_('status', ['completed', 'pending'])
            .limit(1)
            .execute()
        )
        if not response.data or len(response.data) == 0:
            return None
        return str(response.data[0]['id'])
    except Exception:
        return None


async def get_memo_extraction_by_scraped_file_id(
    client: Client,
    scraped_file_id: UUID,
) -> Optional[Dict[str, Any]]:
    """Get memo extraction by scraped_file_id. Returns first match or None."""
    try:
        response = await asyncio.to_thread(
            lambda: client.table("memo_extractions")
            .select("*")
            .eq("scraped_file_id", str(scraped_file_id))
            .limit(1)
            .execute()
        )
        if not response.data or len(response.data) == 0:
            return None
        return response.data[0]
    except Exception:
        return None


async def get_memo_extraction(
    client: Client,
    extraction_id: str
) -> Optional[Dict[str, Any]]:
    """Retrieve a memo extraction record by ID.

    Args:
        client: Supabase client instance
        extraction_id: UUID string of the memo extraction

    Returns:
        Optional[Dict[str, Any]]: Memo extraction record as dictionary, or None if not found

    Raises:
        ValueError: If extraction_id is not a valid UUID
        Exception: If database query fails
    """
    # Validate UUID format
    try:
        UUID(extraction_id)
    except ValueError:
        raise ValueError(f"Invalid UUID format: {extraction_id}")

    try:
        response = await asyncio.to_thread(
            lambda: client.table('memo_extractions').select('*').eq('id', extraction_id).execute()
        )
        if not response.data or len(response.data) == 0:
            return None
        # Type cast for mypy - response.data is a list of dicts
        result: Dict[str, Any] = response.data[0]
        return result
    except Exception as e:
        raise RuntimeError(f"Failed to retrieve memo extraction: {str(e)}") from e


async def check_memo_duplicate(
    client: Client,
    file_hash: str
) -> Optional[str]:
    """Check if a memo PDF with the same hash has already been processed (completed or pending).

    Args:
        client: Supabase client instance
        file_hash: SHA-256 hash of the file

    Returns:
        Optional[str]: UUID of existing memo extraction if found, None otherwise

    Raises:
        RuntimeError: If database query fails
    """
    try:
        return await _get_memo_id_by_file_hash(client, file_hash)
    except Exception as e:
        raise RuntimeError(f"Failed to check memo duplicate: {str(e)}") from e


async def update_memo_extraction_status(
    client: Client,
    extraction_id: str,
    status: str,
    error: Optional[str] = None
) -> None:
    """Update the status of a memo extraction record.

    Args:
        client: Supabase client instance
        extraction_id: UUID string of the memo extraction
        status: New status ('pending', 'completed', 'failed', 'partial')
        error: Optional error message (for failed/partial status)

    Raises:
        ValueError: If extraction_id is not a valid UUID or status is invalid
        Exception: If database update fails
    """
    # Validate UUID format
    try:
        UUID(extraction_id)
    except ValueError:
        raise ValueError(f"Invalid UUID format: {extraction_id}")

    # Validate status
    valid_statuses = ['pending', 'completed', 'failed', 'partial']
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}")

    # Prepare update data
    update_data: Dict[str, Any] = {'status': status}
    if error is not None:
        update_data['error_message'] = error

    try:
        response = await asyncio.to_thread(
            lambda: client.table('memo_extractions').update(update_data).eq('id', extraction_id).execute()
        )
        if not response.data or len(response.data) == 0:
            raise RuntimeError(f"No memo extraction found with id {extraction_id}")
    except Exception as e:
        raise RuntimeError(f"Failed to update memo extraction status: {str(e)}") from e


async def list_memo_extractions(
    client: Client,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List memo extraction records with pagination and optional filtering.

    Args:
        client: Supabase client instance
        limit: Maximum number of records to return (default: 50)
        offset: Number of records to skip (default: 0)
        status: Optional status filter ('pending', 'completed', 'failed', 'partial')

    Returns:
        List[Dict[str, Any]]: List of memo extraction records

    Raises:
        ValueError: If status filter is invalid
        Exception: If database query fails
    """
    # Validate status filter if provided
    if status is not None:
        valid_statuses = ['pending', 'completed', 'failed', 'partial']
        if status not in valid_statuses:
            raise ValueError(f"Invalid status filter '{status}'. Must be one of: {', '.join(valid_statuses)}")

    try:
        query = client.table('memo_extractions').select('*')

        # Apply status filter if provided
        if status is not None:
            query = query.eq('status', status)

        # Apply pagination and ordering
        query = query.order('created_at', desc=True).range(offset, offset + limit - 1)

        response = await asyncio.to_thread(lambda: query.execute())
        return response.data if response.data else []
    except Exception as e:
        raise RuntimeError(f"Failed to list memo extractions: {str(e)}") from e


async def update_memo_extraction(
    client: Client,
    extraction_id: str,
    data: MarkingGuideline,
    status: str,
    error_message: Optional[str] = None,
    retry_count: int = 0
) -> None:
    """Update an existing memo extraction with new data (for retries).

    Args:
        client: Supabase client instance
        extraction_id: UUID of the memo extraction to update
        data: New memo extraction result data
        status: New status ('completed', 'partial', 'failed')
        error_message: Optional error message
        retry_count: Current retry count

    Raises:
        ValueError: If extraction_id is not valid UUID or status is invalid
        Exception: If database update fails
    """
    # Validate UUID format
    try:
        UUID(extraction_id)
    except ValueError:
        raise ValueError(f"Invalid UUID format: {extraction_id}")

    # Validate status
    valid_statuses = ['pending', 'completed', 'failed', 'partial']
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}")

    # Extract processing metadata
    proc_meta = data.processing_metadata
    processing_method = proc_meta.get('method', 'hybrid')
    quality_score = proc_meta.get('opendataloader_quality', 0.0)
    cost_estimate = proc_meta.get('cost_estimate_usd', 0.0)

    # Extract memo metadata from meta dict
    meta = data.meta
    subject = meta.get('subject', 'Unknown')
    year = meta.get('year', 0)
    session = meta.get('session', 'Unknown')
    grade = meta.get('grade', 'Unknown')
    total_marks = meta.get('total_marks', 0)

    # Prepare update data for memo
    update_data = {
        'status': status,
        'processing_method': processing_method,
        'quality_score': quality_score,
        # Memo metadata
        'subject': subject,
        'year': year,
        'session': session,
        'grade': grade,
        'total_marks': total_marks,
        # Sections data as JSON
        'sections': [s.model_dump() for s in data.sections],
        # Processing info
        'processing_metadata': data.processing_metadata,
        'error_message': error_message,
        'retry_count': retry_count,
        'cost_estimate_usd': cost_estimate
    }

    try:
        response = await asyncio.to_thread(
            lambda: client.table('memo_extractions').update(update_data).eq('id', extraction_id).execute()
        )
        if not response.data or len(response.data) == 0:
            raise RuntimeError(f"No memo extraction found with id {extraction_id}")
    except Exception as e:
        raise RuntimeError(f"Failed to update memo extraction: {str(e)}") from e
