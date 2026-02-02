"""Database functions for managing extraction records.

This module provides CRUD operations for extraction results in Supabase,
including insertion, retrieval, deduplication, and status updates.
"""

import asyncio
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from supabase import Client

from app.models.extraction import FullExamPaper


async def create_extraction(
    client: Client,
    data: FullExamPaper,
    file_info: Dict[str, Any],
    status: str = 'completed'
) -> str:
    """Insert a new extraction result into the database.

    Args:
        client: Supabase client instance
        data: Extraction result with all extracted data
        file_info: File metadata dictionary with keys:
            - file_name (str): Sanitized filename
            - file_size_bytes (int): File size in bytes
            - file_hash (str): SHA-256 hash for deduplication
            - processing_time_seconds (float, optional): Processing duration
            - webhook_url (str, optional): Webhook notification URL
            - error_message (str, optional): Error details for partial/failed status
        status: Extraction status ('completed', 'partial', 'failed', 'pending')

    Returns:
        str: UUID of created extraction record

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

    # Prepare database record for exam paper
    record = {
        'file_name': file_info['file_name'],
        'file_size_bytes': file_info['file_size_bytes'],
        'file_hash': file_info['file_hash'],
        'status': status,
        'processing_method': processing_method,
        'quality_score': quality_score,
        # Exam paper metadata
        'subject': data.subject,
        'syllabus': data.syllabus,
        'year': data.year,
        'session': data.session,
        'grade': data.grade,
        'language': data.language,
        'total_marks': data.total_marks,
        # Question data as JSON
        'groups': [g.model_dump() for g in data.groups],
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
            lambda: client.table('extractions').insert(record).execute()
        )
        if not response.data or len(response.data) == 0:
            raise RuntimeError("Insert returned no data")
        return str(response.data[0]['id'])
    except Exception as e:
        # ON CONFLICT: unique partial index (file_hash WHERE status IN completed/pending)
        err_msg = str(e).lower()
        if "23505" in err_msg or "unique" in err_msg or "duplicate" in err_msg:
            existing = await _get_id_by_file_hash(client, file_info['file_hash'])
            if existing:
                return existing
        raise RuntimeError(f"Failed to insert extraction: {str(e)}") from e


async def _get_id_by_file_hash(client: Client, file_hash: str) -> Optional[str]:
    """Return extraction id for file_hash where status in ('completed','pending'), or None."""
    try:
        response = await asyncio.to_thread(
            lambda: client.table('extractions')
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


async def get_extraction(
    client: Client,
    extraction_id: str
) -> Optional[Dict[str, Any]]:
    """Retrieve an extraction record by ID.

    Args:
        client: Supabase client instance
        extraction_id: UUID string of the extraction

    Returns:
        Optional[Dict[str, Any]]: Extraction record as dictionary, or None if not found

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
            lambda: client.table('extractions').select('*').eq('id', extraction_id).execute()
        )
        if not response.data or len(response.data) == 0:
            return None
        # Type cast for mypy - response.data is a list of dicts
        result: Dict[str, Any] = response.data[0]
        return result
    except Exception as e:
        raise Exception(f"Failed to retrieve extraction: {str(e)}")


async def check_duplicate(
    client: Client,
    file_hash: str
) -> Optional[str]:
    """Check if a PDF with the same hash has already been processed (completed or pending).

    Args:
        client: Supabase client instance
        file_hash: SHA-256 hash of the file

    Returns:
        Optional[str]: UUID of existing extraction if found, None otherwise

    Raises:
        RuntimeError: If database query fails
    """
    try:
        return await _get_id_by_file_hash(client, file_hash)
    except Exception as e:
        raise RuntimeError(f"Failed to check duplicate: {str(e)}") from e


async def check_duplicate_any(
    client: Client,
    file_hash: str
) -> Optional[Tuple[str, str]]:
    """Check both extractions and memo_extractions for an existing completed/pending record.

    Returns:
        ('extractions', id) or ('memo_extractions', id) if found, None otherwise.
    """
    from app.db import memo_extractions
    ex_id = await check_duplicate(client, file_hash)
    if ex_id:
        return ("extractions", ex_id)
    memo_id = await memo_extractions.check_memo_duplicate(client, file_hash)
    if memo_id:
        return ("memo_extractions", memo_id)
    return None


async def update_extraction_status(
    client: Client,
    extraction_id: str,
    status: str,
    error: Optional[str] = None
) -> None:
    """Update the status of an extraction record.

    Args:
        client: Supabase client instance
        extraction_id: UUID string of the extraction
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
            lambda: client.table('extractions').update(update_data).eq('id', extraction_id).execute()
        )
        if not response.data or len(response.data) == 0:
            raise RuntimeError(f"No extraction found with id {extraction_id}")
    except Exception as e:
        raise RuntimeError(f"Failed to update extraction status: {str(e)}") from e


async def list_extractions(
    client: Client,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List extraction records with pagination and optional filtering.

    Args:
        client: Supabase client instance
        limit: Maximum number of records to return (default: 50)
        offset: Number of records to skip (default: 0)
        status: Optional status filter ('pending', 'completed', 'failed', 'partial')

    Returns:
        List[Dict[str, Any]]: List of extraction records

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
        query = client.table('extractions').select('*')

        # Apply status filter if provided
        if status is not None:
            query = query.eq('status', status)

        # Apply pagination and ordering
        query = query.order('created_at', desc=True).range(offset, offset + limit - 1)

        response = await asyncio.to_thread(lambda: query.execute())
        return response.data if response.data else []
    except Exception as e:
        raise Exception(f"Failed to list extractions: {str(e)}")


async def update_extraction(
    client: Client,
    extraction_id: str,
    data: FullExamPaper,
    status: str,
    error_message: Optional[str] = None,
    retry_count: int = 0
) -> None:
    """Update an existing extraction with new data (for retries).

    Args:
        client: Supabase client instance
        extraction_id: UUID of the extraction to update
        data: New extraction result data
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

    # Prepare update data for exam paper
    update_data = {
        'status': status,
        'processing_method': processing_method,
        'quality_score': quality_score,
        # Exam paper metadata
        'subject': data.subject,
        'syllabus': data.syllabus,
        'year': data.year,
        'session': data.session,
        'grade': data.grade,
        'language': data.language,
        'total_marks': data.total_marks,
        # Question data as JSON
        'groups': [g.model_dump() for g in data.groups],
        # Processing info
        'processing_metadata': data.processing_metadata,
        'error_message': error_message,
        'retry_count': retry_count
    }

    try:
        response = await asyncio.to_thread(
            lambda: client.table('extractions').update(update_data).eq('id', extraction_id).execute()
        )
        if not response.data or len(response.data) == 0:
            raise RuntimeError(f"No extraction found with id {extraction_id}")
    except Exception as e:
        raise RuntimeError(f"Failed to update extraction: {str(e)}") from e
