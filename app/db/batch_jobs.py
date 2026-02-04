"""Database functions for managing batch processing jobs.

This module provides CRUD operations for batch jobs in Supabase,
including creation, status updates, and routing statistics tracking.
"""

from typing import Dict, Any, List, Optional
from uuid import UUID
from supabase import Client


async def create_batch_job(
    client: Client,
    total_files: int,
    webhook_url: Optional[str] = None
) -> str:
    """Create a new batch processing job.

    Args:
        client: Supabase client instance
        total_files: Total number of files in the batch (1-100)
        webhook_url: Optional webhook URL for completion notifications

    Returns:
        str: UUID of created batch job

    Raises:
        ValueError: If total_files is out of range
        Exception: If database insertion fails
    """
    if total_files < 1 or total_files > 100:
        raise ValueError(f"total_files must be between 1 and 100, got {total_files}")

    record = {
        'total_files': total_files,
        'status': 'pending',
        'completed_files': 0,
        'failed_files': 0,
        'routing_stats': {'hybrid': 0, 'vision_fallback': 0, 'pending': total_files},
        'extraction_ids': [],
        'webhook_url': webhook_url
    }

    try:
        response = client.table('batch_jobs').insert(record).execute()
        if not response.data or len(response.data) == 0:
            raise Exception("Insert returned no data")
        return str(response.data[0]['id'])
    except Exception as e:
        raise Exception(f"Failed to create batch job: {str(e)}")


async def get_batch_job(
    client: Client,
    batch_job_id: str
) -> Optional[Dict[str, Any]]:
    """Retrieve a batch job by ID.

    Args:
        client: Supabase client instance
        batch_job_id: UUID string of the batch job

    Returns:
        Optional[Dict[str, Any]]: Batch job record, or None if not found

    Raises:
        ValueError: If batch_job_id is not a valid UUID
        Exception: If database query fails
    """
    # Validate UUID format
    try:
        UUID(batch_job_id)
    except ValueError:
        raise ValueError(f"Invalid UUID format: {batch_job_id}")

    try:
        response = client.table('batch_jobs').select('*').eq('id', batch_job_id).execute()
        if not response.data or len(response.data) == 0:
            return None
        result: Dict[str, Any] = response.data[0]
        return result
    except Exception as e:
        raise Exception(f"Failed to retrieve batch job: {str(e)}")


async def add_extraction_to_batch(
    client: Client,
    batch_job_id: str,
    extraction_id: str,
    processing_method: str,
    status: str,
    cost_estimate_usd: float = 0.0,
    cost_savings_usd: float = 0.0
) -> None:
    """Add an extraction result to a batch job and update statistics.

    Args:
        client: Supabase client instance
        batch_job_id: UUID of the batch job
        extraction_id: UUID of the extraction to add
        processing_method: Method used ('hybrid' or 'vision_fallback')
        status: Extraction status ('completed' or 'failed')
        cost_estimate_usd: Cost for this extraction
        cost_savings_usd: Cost savings for this extraction

    Raises:
        ValueError: If UUIDs are invalid or status/method are invalid
        Exception: If database update fails
    """
    # Validate UUIDs
    try:
        UUID(batch_job_id)
        UUID(extraction_id)
    except ValueError as e:
        raise ValueError(f"Invalid UUID: {str(e)}")

    # Validate processing_method
    valid_methods = ['hybrid', 'vision_fallback', 'batch_api']
    if processing_method not in valid_methods:
        raise ValueError(f"Invalid processing_method '{processing_method}'. Must be one of: {', '.join(valid_methods)}")

    # Validate status
    valid_statuses = ['completed', 'failed', 'partial']
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}")

    try:
        # First, get current batch job state
        batch_job = await get_batch_job(client, batch_job_id)
        if not batch_job:
            raise Exception(f"Batch job {batch_job_id} not found")

        # Update counts
        completed_files = batch_job['completed_files']
        failed_files = batch_job['failed_files']
        if status == 'completed' or status == 'partial':
            completed_files += 1
        else:
            failed_files += 1

        # Update routing stats
        routing_stats = batch_job['routing_stats']
        routing_stats['pending'] = max(0, routing_stats['pending'] - 1)
        routing_stats[processing_method] = routing_stats.get(processing_method, 0) + 1

        # Update extraction IDs
        extraction_ids = batch_job['extraction_ids']
        extraction_ids.append(extraction_id)

        # Update cost tracking
        current_cost = batch_job.get('cost_estimate_usd') or 0.0
        current_savings = batch_job.get('cost_savings_usd') or 0.0
        new_cost = current_cost + cost_estimate_usd
        new_savings = current_savings + cost_savings_usd

        # Determine batch status
        total_files = batch_job['total_files']
        if completed_files + failed_files == total_files:
            if failed_files == 0:
                batch_status = 'completed'
            elif completed_files == 0:
                batch_status = 'failed'
            else:
                batch_status = 'partial'
        else:
            batch_status = 'processing'

        # Update batch job
        update_data = {
            'completed_files': completed_files,
            'failed_files': failed_files,
            'routing_stats': routing_stats,
            'extraction_ids': extraction_ids,
            'cost_estimate_usd': new_cost,
            'cost_savings_usd': new_savings,
            'status': batch_status
        }

        response = client.table('batch_jobs').update(update_data).eq('id', batch_job_id).execute()
        if not response.data or len(response.data) == 0:
            raise Exception(f"No batch job found with id {batch_job_id}")
    except Exception as e:
        raise Exception(f"Failed to update batch job: {str(e)}")


async def list_batch_jobs(
    client: Client,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List batch jobs with pagination and optional filtering.

    Args:
        client: Supabase client instance
        limit: Maximum number of records to return (default: 50)
        offset: Number of records to skip (default: 0)
        status: Optional status filter

    Returns:
        List[Dict[str, Any]]: List of batch job records

    Raises:
        ValueError: If status filter is invalid
        Exception: If database query fails
    """
    if status is not None:
        valid_statuses = ['pending', 'processing', 'completed', 'failed', 'partial']
        if status not in valid_statuses:
            raise ValueError(f"Invalid status filter '{status}'. Must be one of: {', '.join(valid_statuses)}")

    try:
        query = client.table('batch_jobs').select('*')

        if status is not None:
            query = query.eq('status', status)

        query = query.order('created_at', desc=True).range(offset, offset + limit - 1)

        response = query.execute()
        return response.data if response.data else []
    except Exception as e:
        raise Exception(f"Failed to list batch jobs: {str(e)}")
