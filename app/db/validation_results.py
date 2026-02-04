"""CRUD for validation_results table (validation outcome per scraped file)."""

import asyncio
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from supabase import Client


async def create_validation_result(
    client: Client,
    status: str,
    scraped_file_id: Optional[UUID] = None,
    file_id: Optional[str] = None,
    confidence_score: Optional[float] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    year: Optional[Union[int, str]] = None,
    paper_type: Optional[str] = None,
    paper_number: Optional[int] = None,
    session: Optional[str] = None,
    syllabus: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Insert or replace validation result for a scraped file. Accepts either scraped_file_id (UUID) or file_id (TEXT)."""
    if scraped_file_id is None and file_id is None:
        raise ValueError("Either scraped_file_id or file_id must be provided")
    record: Dict[str, Any] = {
        "status": status,
        "confidence_score": confidence_score,
        "subject": subject,
        "grade": grade,
        "year": year,
        "paper_type": paper_type,
        "paper_number": paper_number,
        "session": session,
        "syllabus": syllabus,
        "metadata": metadata or {},
    }
    if scraped_file_id is not None:
        record["scraped_file_id"] = str(scraped_file_id)
    if file_id is not None:
        record["file_id"] = file_id
    if scraped_file_id is not None:
        await asyncio.to_thread(
            lambda: client.table("validation_results").upsert(record, on_conflict="scraped_file_id").execute()
        )
    else:
        await asyncio.to_thread(lambda: client.table("validation_results").insert(record).execute())


async def get_validation_result(client: Client, scraped_file_id: UUID) -> Optional[Dict[str, Any]]:
    """Get validation result by scraped_file_id. Returns None if not found."""
    response = await asyncio.to_thread(
        lambda: client.table("validation_results")
        .select("*")
        .eq("scraped_file_id", str(scraped_file_id))
        .maybe_single()
        .execute()
    )
    if response.data:
        row = response.data[0] if isinstance(response.data, list) else response.data
        return row
    return None


async def get_linked_scraped_file(client: Client, scraped_file_id: UUID) -> Optional[Dict[str, Any]]:
    """Retrieve the linked scraped_files record for a given scraped_file_id."""
    response = await asyncio.to_thread(
        lambda: client.table("scraped_files").select("*").eq("id", str(scraped_file_id)).maybe_single().execute()
    )
    if response.data:
        row = response.data[0] if isinstance(response.data, list) else response.data
        return row
    return None


async def link_validation_to_scraped_file(
    client: Client, validation_result_id: UUID, scraped_file_id: UUID
) -> Optional[Dict[str, Any]]:
    """Link an existing validation_result to a scraped_file by setting scraped_file_id. Returns updated row or None."""
    response = await asyncio.to_thread(
        lambda: client.table("validation_results")
        .update({"scraped_file_id": str(scraped_file_id)})
        .eq("id", str(validation_result_id))
        .execute()
    )
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


async def update_validation_result(
    client: Client,
    scraped_file_id: UUID,
    status: Optional[str] = None,
    metadata_override: Optional[Dict[str, Any]] = None,
    **fields: Any,
) -> Optional[Dict[str, Any]]:
    """Update validation result. Returns updated row or None."""
    updates: Dict[str, Any] = dict(fields)
    if status is not None:
        updates["status"] = status
    if metadata_override is not None:
        updates["metadata"] = metadata_override
    if not updates:
        return await get_validation_result(client, scraped_file_id)
    response = await asyncio.to_thread(
        lambda: client.table("validation_results")
        .update(updates)
        .eq("scraped_file_id", str(scraped_file_id))
        .execute()
    )
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


async def list_validation_results(
    client: Client,
    status: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[List[Dict[str, Any]], int]:
    """List validation_results with optional status filter. Returns (items, total)."""
    count_query = client.table("validation_results").select("scraped_file_id", count="exact")
    if status is not None:
        count_query = count_query.eq("status", status)
    count_response = await asyncio.to_thread(lambda: count_query.execute())
    total = count_response.count if hasattr(count_response, "count") and count_response.count is not None else 0
    query = client.table("validation_results").select("*")
    if status is not None:
        query = query.eq("status", status)
    response = await asyncio.to_thread(
        lambda: query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    )
    items = response.data or []
    return items, total


async def list_review_queue(
    client: Client,
    page: int = 1,
    page_size: int = 20,
) -> tuple[List[Dict[str, Any]], int]:
    """List validation_results with status = review_required. Returns (items, total)."""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20
    offset = (page - 1) * page_size
    count_response = await asyncio.to_thread(
        lambda: client.table("validation_results")
        .select("scraped_file_id", count="exact")
        .eq("status", "review_required")
        .execute()
    )
    total = count_response.count if hasattr(count_response, "count") and count_response.count is not None else 0
    response = await asyncio.to_thread(
        lambda: client.table("validation_results")
        .select("*")
        .eq("status", "review_required")
        .order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )
    items = response.data or []
    return items, total
