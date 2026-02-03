"""CRUD for validation_jobs table (batch validation job progress)."""

import asyncio
from typing import Any, Dict, Optional
from uuid import UUID

from supabase import Client


async def create_validation_job(
    client: Client,
    total_files: int,
    status: str = "pending",
) -> str:
    """Create a validation job. Returns job id (UUID string)."""
    record = {
        "status": status,
        "total_files": total_files,
        "processed_files": 0,
        "accepted_files": 0,
        "rejected_files": 0,
        "review_required_files": 0,
        "failed_files": 0,
    }
    response = await asyncio.to_thread(
        lambda: client.table("validation_jobs").insert(record).execute()
    )
    if not response.data or len(response.data) == 0:
        raise RuntimeError("Insert returned no data")
    return str(response.data[0]["id"])


async def get_validation_job(client: Client, job_id: UUID) -> Optional[Dict[str, Any]]:
    """Get validation job by id. Returns None if not found."""
    response = await asyncio.to_thread(
        lambda: client.table("validation_jobs")
        .select("*")
        .eq("id", str(job_id))
        .maybe_single()
        .execute()
    )
    if response.data:
        row = response.data[0] if isinstance(response.data, list) else response.data
        return row
    return None


async def update_validation_job(
    client: Client,
    job_id: UUID,
    status: Optional[str] = None,
    processed_files: Optional[int] = None,
    accepted_files: Optional[int] = None,
    rejected_files: Optional[int] = None,
    review_required_files: Optional[int] = None,
    failed_files: Optional[int] = None,
    completed_at: Optional[str] = None,
    **fields: Any,
) -> Optional[Dict[str, Any]]:
    """Update validation job progress. Returns updated row or None."""
    updates: Dict[str, Any] = dict(fields)
    if status is not None:
        updates["status"] = status
    if processed_files is not None:
        updates["processed_files"] = processed_files
    if accepted_files is not None:
        updates["accepted_files"] = accepted_files
    if rejected_files is not None:
        updates["rejected_files"] = rejected_files
    if review_required_files is not None:
        updates["review_required_files"] = review_required_files
    if failed_files is not None:
        updates["failed_files"] = failed_files
    if completed_at is not None:
        updates["completed_at"] = completed_at
    if not updates:
        return await get_validation_job(client, job_id)
    response = await asyncio.to_thread(
        lambda: client.table("validation_jobs")
        .update(updates)
        .eq("id", str(job_id))
        .execute()
    )
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None
