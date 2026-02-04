"""CRUD for document_sections table (cover, instructions, marker notes, etc.)."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from supabase import Client


async def upsert_document_section(
    client: Client,
    scraped_file_id: UUID,
    section_type: str,
    content: Dict[str, Any],
    *,
    title: Optional[str] = None,
    raw_text: Optional[str] = None,
    page_start: Optional[int] = None,
    page_end: Optional[int] = None,
    extraction_method: Optional[str] = None,
    confidence_score: Optional[int] = None,
) -> str:
    """Insert or update a document section. Returns id."""
    record: Dict[str, Any] = {
        "scraped_file_id": str(scraped_file_id),
        "section_type": section_type,
        "content": content,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if title is not None:
        record["title"] = title
    if raw_text is not None:
        record["raw_text"] = raw_text
    if page_start is not None:
        record["page_start"] = page_start
    if page_end is not None:
        record["page_end"] = page_end
    if extraction_method is not None:
        record["extraction_method"] = extraction_method
    if confidence_score is not None:
        record["confidence_score"] = confidence_score
    response = await asyncio.to_thread(
        lambda: client.table("document_sections")
        .upsert(record, on_conflict="scraped_file_id,section_type")
        .execute()
    )
    if not response.data or len(response.data) == 0:
        raise RuntimeError("Upsert document_section returned no data")
    return str(response.data[0]["id"])


async def get_section(
    client: Client,
    scraped_file_id: UUID,
    section_type: str,
) -> Optional[Dict[str, Any]]:
    """Get a single section by file and type. Returns None if not found."""
    response = await asyncio.to_thread(
        lambda: client.table("document_sections")
        .select("*")
        .eq("scraped_file_id", str(scraped_file_id))
        .eq("section_type", section_type)
        .maybe_single()
        .execute()
    )
    if response.data:
        row = response.data[0] if isinstance(response.data, list) else response.data
        return row
    return None


async def list_sections_by_file(
    client: Client,
    scraped_file_id: UUID,
) -> List[Dict[str, Any]]:
    """List all sections for a document."""
    response = await asyncio.to_thread(
        lambda: client.table("document_sections")
        .select("*")
        .eq("scraped_file_id", str(scraped_file_id))
        .order("page_start", desc=False)
        .execute()
    )
    return response.data or []
