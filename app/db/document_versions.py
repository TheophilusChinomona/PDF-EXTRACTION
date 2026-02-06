"""CRUD for document_versions table (duplicate QP/Memo tracking)."""

import asyncio
from typing import Any, Dict, List, Optional
from uuid import UUID

from supabase import Client


def _is_duplicate_key_error(exc: BaseException) -> bool:
    """True if exception is Postgres unique violation 23505."""
    msg = str(exc).lower()
    if "23505" in msg or "unique" in msg and "duplicate" in msg:
        return True
    if hasattr(exc, "code") and getattr(exc, "code") == "23505":
        return True
    if hasattr(exc, "details") and exc.details and "23505" in str(exc.details):
        return True
    return False


async def get_version_by_exam_set_and_duplicate(
    client: Client,
    exam_set_id: UUID,
    duplicate_id: UUID,
) -> Optional[Dict[str, Any]]:
    """Return document_version row if one exists for (exam_set_id, duplicate_id)."""
    response = await asyncio.to_thread(
        lambda: client.table("document_versions")
        .select("*")
        .eq("exam_set_id", str(exam_set_id))
        .eq("duplicate_id", str(duplicate_id))
        .maybe_single()
        .execute()
    )
    if response.data:
        row = response.data[0] if isinstance(response.data, list) else response.data
        return row
    return None


async def create_document_version(
    client: Client,
    exam_set_id: UUID,
    original_id: UUID,
    duplicate_id: UUID,
    slot: str,
    is_active: bool = False,
) -> str:
    """Create a document_versions record for a duplicate. Returns id. Idempotent: if (exam_set_id, duplicate_id) already exists, returns that row's id."""
    record: Dict[str, Any] = {
        "exam_set_id": str(exam_set_id),
        "original_id": str(original_id),
        "duplicate_id": str(duplicate_id),
        "slot": slot,
        "is_active": is_active,
    }
    try:
        response = await asyncio.to_thread(
            lambda: client.table("document_versions").insert(record).execute()
        )
        if not response.data or len(response.data) == 0:
            raise RuntimeError("Insert document_version returned no data")
        return str(response.data[0]["id"])
    except Exception as e:
        if _is_duplicate_key_error(e):
            existing = await get_version_by_exam_set_and_duplicate(
                client, exam_set_id, duplicate_id
            )
            if existing and existing.get("id"):
                return str(existing["id"])
        raise


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
