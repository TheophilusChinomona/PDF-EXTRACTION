"""CRUD for gemini_batch_jobs table (Gemini Batch API job tracking)."""

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from supabase import Client


async def create_gemini_batch_job(
    client: Client,
    gemini_job_name: str,
    job_type: str,
    total_requests: int,
    source_job_id: str | None = None,
    request_metadata: dict[str, Any] | None = None,
) -> str:
    """Create a Gemini batch job record. Returns id (UUID string)."""
    record: dict[str, Any] = {
        "gemini_job_name": gemini_job_name,
        "job_type": job_type,
        "status": "pending",
        "total_requests": total_requests,
        "completed_requests": 0,
        "failed_requests": 0,
    }
    if source_job_id is not None:
        record["source_job_id"] = source_job_id
    if request_metadata is not None:
        record["request_metadata"] = request_metadata

    response = await asyncio.to_thread(
        lambda: client.table("gemini_batch_jobs").insert(record).execute()
    )
    if not response.data or len(response.data) == 0:
        raise RuntimeError("Insert gemini_batch_jobs returned no data")
    return str(response.data[0]["id"])


async def get_gemini_batch_job(
    client: Client,
    job_id: str,
) -> dict[str, Any] | None:
    """Get a Gemini batch job by id (our UUID). Returns None if not found."""
    try:
        UUID(job_id)
    except ValueError:
        return None
    response = await asyncio.to_thread(
        lambda: client.table("gemini_batch_jobs")
        .select("*")
        .eq("id", job_id)
        .maybe_single()
        .execute()
    )
    if response.data:
        row = response.data[0] if isinstance(response.data, list) else response.data
        return row
    return None


async def get_gemini_batch_job_by_gemini_name(
    client: Client,
    gemini_job_name: str,
) -> dict[str, Any] | None:
    """Get a Gemini batch job by gemini_job_name (e.g. batches/123)."""
    response = await asyncio.to_thread(
        lambda: client.table("gemini_batch_jobs")
        .select("*")
        .eq("gemini_job_name", gemini_job_name)
        .maybe_single()
        .execute()
    )
    if response.data:
        row = response.data[0] if isinstance(response.data, list) else response.data
        return row
    return None


async def update_gemini_batch_job_status(
    client: Client,
    job_id: str,
    status: str | None = None,
    completed_requests: int | None = None,
    failed_requests: int | None = None,
    result_file_name: str | None = None,
    error_message: str | None = None,
    completed_at: str | None = None,
    **fields: Any,
) -> dict[str, Any] | None:
    """Update Gemini batch job fields. Returns updated row or None."""
    updates: dict[str, Any] = dict(fields)
    if status is not None:
        updates["status"] = status
    if completed_requests is not None:
        updates["completed_requests"] = completed_requests
    if failed_requests is not None:
        updates["failed_requests"] = failed_requests
    if result_file_name is not None:
        updates["result_file_name"] = result_file_name
    if error_message is not None:
        updates["error_message"] = error_message
    if completed_at is not None:
        updates["completed_at"] = completed_at
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    if not updates:
        return await get_gemini_batch_job(client, job_id)
    response = await asyncio.to_thread(
        lambda: client.table("gemini_batch_jobs")
        .update(updates)
        .eq("id", job_id)
        .execute()
    )
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


async def get_gemini_batch_job_by_source_job_id(
    client: Client,
    source_job_id: str,
    job_type: str = "extraction",
) -> dict[str, Any] | None:
    """Get a Gemini batch job by source_job_id (e.g. batch_jobs.id or validation_jobs.id)."""
    response = await asyncio.to_thread(
        lambda: client.table("gemini_batch_jobs")
        .select("*")
        .eq("source_job_id", source_job_id)
        .eq("job_type", job_type)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not response.data or len(response.data) == 0:
        return None
    row = response.data[0]
    return row


async def get_pending_gemini_batch_jobs(
    client: Client,
    job_type: str | None = None,
) -> list[dict[str, Any]]:
    """List Gemini batch jobs with status = 'pending'. Optionally filter by job_type."""
    query = (
        client.table("gemini_batch_jobs")
        .select("*")
        .eq("status", "pending")
    )
    if job_type is not None:
        query = query.eq("job_type", job_type)
    response = await asyncio.to_thread(
        lambda: query.order("created_at", desc=False).execute()
    )
    if not response.data:
        return []
    return list(response.data) if isinstance(response.data, list) else [response.data]
