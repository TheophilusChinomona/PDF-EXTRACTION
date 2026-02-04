"""CRUD for document_versions table (duplicate QP/Memo tracking)."""

import asyncio
from typing import Any, Dict, List, Optional
from uuid import UUID

from supabase import Client


async def create_document_version(
    client: Client,
    exam_set_id: UUID,
    original_id: UUID,
    duplicate_id: UUID,
    slot: str,
    is_active: bool = False,
) -> str:
    """Create a document_versions record for a duplicate. Returns id."""
    record: Dict[str, Any] = {
        "exam_set_id": str(exam_set_id),
        "original_id": str(original_id),
        "duplicate_id": str(duplicate_id),
        "slot": slot,
        "is_active": is_active,
    }
    response = await asyncio.to_thread(
        lambda: client.table("document_versions").insert(record).execute()
    )
    if not response.data or len(response.data) == 0:
        raise RuntimeError("Insert document_version returned no data")
    return str(response.data[0]["id"])


async def list_versions_for_exam_set(
    client: Client,
    exam_set_id: UUID,
    slot: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List document_versions for an exam set, optionally filtered by slot."""
    query = (
        client.table("document_versions")
        .select("*")
        .eq("exam_set_id", str(exam_set_id))
    )
    if slot is not None:
        query = query.eq("slot", slot)
    response = await asyncio.to_thread(
        lambda: query.order("uploaded_at", desc=True).execute()
    )
    return response.data or []


async def set_active_version(
    client: Client,
    document_version_id: UUID,
    is_active: bool,
) -> Optional[Dict[str, Any]]:
    """Set is_active for a document_version. Returns updated row or None."""
    response = await asyncio.to_thread(
        lambda: client.table("document_versions")
        .update({"is_active": is_active})
        .eq("id", str(document_version_id))
        .execute()
    )
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


async def get_version(
    client: Client,
    document_version_id: UUID,
) -> Optional[Dict[str, Any]]:
    """Get a document_version by id."""
    response = await asyncio.to_thread(
        lambda: client.table("document_versions")
        .select("*")
        .eq("id", str(document_version_id))
        .maybe_single()
        .execute()
    )
    if response.data:
        row = response.data[0] if isinstance(response.data, list) else response.data
        return row
    return None
