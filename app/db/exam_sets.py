"""CRUD for exam_sets table (QP–Memo linking)."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from supabase import Client


async def find_exam_set_by_match_key(
    client: Client,
    subject: str,
    grade: int,
    paper_number: int,
    year: int,
    session: str,
    syllabus: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Find an exam_set by matching key. Returns None if not found."""
    q = (
        client.table("exam_sets")
        .select("*")
        .eq("subject", subject)
        .eq("grade", grade)
        .eq("paper_number", paper_number)
        .eq("year", year)
        .eq("session", session)
    )
    if syllabus is not None and syllabus != "":
        q = q.eq("syllabus", syllabus)
    else:
        # Match both NULL and empty string
        q = q.or_("syllabus.is.null,syllabus.eq.")
    response = await asyncio.to_thread(
        lambda: q.limit(1).execute()
    )
    if response.data and len(response.data) > 0:
        row = response.data[0] if isinstance(response.data, list) else response.data
        return row
    return None


async def get_exam_set(client: Client, exam_set_id: UUID) -> Optional[Dict[str, Any]]:
    """Get exam set by id."""
    response = await asyncio.to_thread(
        lambda: client.table("exam_sets")
        .select("*")
        .eq("id", str(exam_set_id))
        .maybe_single()
        .execute()
    )
    if response.data:
        row = response.data[0] if isinstance(response.data, list) else response.data
        return row
    return None


async def create_exam_set(
    client: Client,
    subject: str,
    grade: int,
    paper_number: int,
    year: int,
    session: str,
    syllabus: Optional[str] = None,
    question_paper_id: Optional[UUID] = None,
    memo_id: Optional[UUID] = None,
    match_method: str = "automatic",
    match_confidence: Optional[int] = None,
) -> str:
    """Create a new exam_set. Returns id."""
    record: Dict[str, Any] = {
        "subject": subject,
        "grade": grade,
        "paper_number": paper_number,
        "year": year,
        "session": session,
        "syllabus": syllabus or "",
        "match_method": match_method,
        "status": "incomplete",
    }
    if question_paper_id is not None:
        record["question_paper_id"] = str(question_paper_id)
    if memo_id is not None:
        record["memo_id"] = str(memo_id)
    if match_confidence is not None:
        record["match_confidence"] = match_confidence
    response = await asyncio.to_thread(
        lambda: client.table("exam_sets").insert(record).execute()
    )
    if not response.data or len(response.data) == 0:
        raise RuntimeError("Insert exam_set returned no data")
    return str(response.data[0]["id"])


async def update_exam_set(
    client: Client,
    exam_set_id: UUID,
    *,
    question_paper_id: Optional[UUID] = None,
    memo_id: Optional[UUID] = None,
    status: Optional[str] = None,
    match_confidence: Optional[int] = None,
    matched_at: Optional[str] = None,
    matched_by: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Update exam set fields. Returns updated row or None."""
    updates: Dict[str, Any] = {}
    if question_paper_id is not None:
        updates["question_paper_id"] = str(question_paper_id)
    if memo_id is not None:
        updates["memo_id"] = str(memo_id)
    if status is not None:
        updates["status"] = status
    if match_confidence is not None:
        updates["match_confidence"] = match_confidence
    if matched_at is not None:
        updates["matched_at"] = matched_at
    if matched_by is not None:
        updates["matched_by"] = matched_by
    if not updates:
        return await get_exam_set(client, exam_set_id)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    response = await asyncio.to_thread(
        lambda: client.table("exam_sets")
        .update(updates)
        .eq("id", str(exam_set_id))
        .execute()
    )
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


async def list_exam_sets(
    client: Client,
    subject: Optional[str] = None,
    grade: Optional[int] = None,
    year: Optional[int] = None,
    session: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[List[Dict[str, Any]], int]:
    """List exam sets with optional filters. Returns (items, total)."""
    query = client.table("exam_sets").select("*", count="exact")
    if subject is not None:
        query = query.eq("subject", subject)
    if grade is not None:
        query = query.eq("grade", grade)
    if year is not None:
        query = query.eq("year", year)
    if session is not None:
        query = query.eq("session", session)
    if status is not None:
        query = query.eq("status", status)
    query = query.order("year", desc=True).order("subject", desc=False)
    response = await asyncio.to_thread(
        lambda: query.range(offset, offset + limit - 1).execute()
    )
    total = response.count if hasattr(response, "count") and response.count is not None else 0
    items = response.data or []
    return items, total
