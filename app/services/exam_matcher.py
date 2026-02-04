"""
Match documents to exam sets (QP–Memo linking).

Runs after validation: build match key from metadata, find or create exam_set,
link document to QP or Memo slot. Handles duplicates via document_versions and
sets exam_set status to duplicate_review.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from supabase import Client

from app.db import document_versions, exam_sets as db_exam_sets
from app.utils.normalizers import (
    normalize_grade,
    normalize_paper_number,
    normalize_session,
    normalize_subject,
)


def calculate_match_confidence(
    subject: str,
    grade: Optional[int],
    paper_number: int,
    year: Optional[int],
    session: str,
) -> int:
    """Score 0–100: 25 subject + 20 grade + 20 paper + 20 year + 15 session."""
    score = 0
    if subject:
        score += 25
    if grade is not None:
        score += 20
    score += 20  # paper_number always set (default 1)
    if year is not None:
        score += 20
    if session:
        score += 15
    return score


async def match_document_to_exam_set(
    client: Client,
    scraped_file_id: UUID,
    metadata: Dict[str, Any],
) -> Optional[UUID]:
    """
    Match a document to an exam set by metadata; create exam_set if none exists.
    Returns exam_set_id or None if metadata insufficient (e.g. missing grade).
    """
    subject_raw = metadata.get("subject")
    grade_raw = metadata.get("grade")
    year = metadata.get("year")
    session_raw = metadata.get("session")
    syllabus = metadata.get("syllabus")
    paper_type = (metadata.get("paper_type") or "").strip().lower()
    paper_number_raw = metadata.get("paper_number")

    subject = normalize_subject(subject_raw or "")
    grade = normalize_grade(grade_raw) if grade_raw is not None else None
    paper_number = normalize_paper_number(paper_number_raw) if paper_number_raw is not None else 1
    session = normalize_session(session_raw or "")

    if not subject or grade is None or not session:
        return None

    if "memo" in paper_type or "marking" in paper_type or "mg" in paper_type:
        is_qp = False
    else:
        is_qp = True

    syllabus_val = (syllabus or "").strip() or None
    existing = await db_exam_sets.find_exam_set_by_match_key(
        client,
        subject=subject,
        grade=grade,
        paper_number=paper_number,
        year=year or 0,
        session=session,
        syllabus=syllabus_val,
    )

    now = datetime.now(timezone.utc).isoformat()

    if existing:
        exam_set_id = UUID(existing["id"])
        qp_id = existing.get("question_paper_id")
        memo_id = existing.get("memo_id")

        if is_qp:
            if qp_id:
                await _handle_duplicate(
                    client,
                    exam_set_id=exam_set_id,
                    original_id=UUID(qp_id),
                    duplicate_id=scraped_file_id,
                    slot="question_paper",
                )
                return exam_set_id
            await db_exam_sets.update_exam_set(
                client,
                exam_set_id,
                question_paper_id=scraped_file_id,
                status="matched" if memo_id else "incomplete",
                matched_at=now,
                matched_by="system",
                match_confidence=100,
            )
        else:
            if memo_id:
                await _handle_duplicate(
                    client,
                    exam_set_id=exam_set_id,
                    original_id=UUID(memo_id),
                    duplicate_id=scraped_file_id,
                    slot="memo",
                )
                return exam_set_id
            await db_exam_sets.update_exam_set(
                client,
                exam_set_id,
                memo_id=scraped_file_id,
                status="matched" if qp_id else "incomplete",
                matched_at=now,
                matched_by="system",
                match_confidence=100,
            )
        return exam_set_id

    exam_set_id_str = await db_exam_sets.create_exam_set(
        client,
        subject=subject,
        grade=grade,
        paper_number=paper_number,
        year=year or 0,
        session=session,
        syllabus=syllabus_val,
        question_paper_id=scraped_file_id if is_qp else None,
        memo_id=scraped_file_id if not is_qp else None,
        match_method="automatic",
        match_confidence=100,
    )
    return UUID(exam_set_id_str)


async def _handle_duplicate(
    client: Client,
    *,
    exam_set_id: UUID,
    original_id: UUID,
    duplicate_id: UUID,
    slot: str,
) -> None:
    """Create document_version and set exam_set status to duplicate_review."""
    await document_versions.create_document_version(
        client,
        exam_set_id=exam_set_id,
        original_id=original_id,
        duplicate_id=duplicate_id,
        slot=slot,
        is_active=False,
    )
    await db_exam_sets.update_exam_set(
        client,
        exam_set_id,
        status="duplicate_review",
    )
