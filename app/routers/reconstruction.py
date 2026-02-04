"""Paper reconstruction API: full QP and full memo from exam set."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.db.document_sections import get_section
from app.db.exam_sets import get_exam_set
from app.db.extractions import get_extraction_by_scraped_file_id
from app.db.memo_extractions import get_memo_extraction_by_scraped_file_id
from app.db.supabase_client import get_supabase_client
from app.models.reconstruction import MemoFull, QuestionPaperFull

router = APIRouter(prefix="/api/exam-sets", tags=["reconstruction"])


@router.get("/{exam_set_id}/question-paper/full", response_model=None)
async def get_question_paper_full(exam_set_id: UUID) -> dict:
    """Return full reconstructed question paper: cover_page, instructions, questions[], information_sheet. Missing sections as null."""
    client = get_supabase_client()
    row = await get_exam_set(client, exam_set_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam set not found")
    qp_id = row.get("question_paper_id")
    if not qp_id:
        return {
            "exam_set_id": str(exam_set_id),
            "cover_page": None,
            "instructions": None,
            "questions": [],
            "information_sheet": None,
        }
    qp_uuid = UUID(str(qp_id)) if isinstance(qp_id, str) else qp_id
    cover = await get_section(client, qp_uuid, "cover_page")
    instructions = await get_section(client, qp_uuid, "student_instructions")
    info_sheet = await get_section(client, qp_uuid, "information_sheet")
    extraction = await get_extraction_by_scraped_file_id(client, qp_uuid)
    questions = []
    if extraction and extraction.get("groups"):
        questions = extraction["groups"]
    return {
        "exam_set_id": str(exam_set_id),
        "cover_page": (cover.get("content") if isinstance(cover, dict) else None) if cover else None,
        "instructions": (instructions.get("content") if isinstance(instructions, dict) else None) if instructions else None,
        "questions": questions,
        "information_sheet": (info_sheet.get("content") if isinstance(info_sheet, dict) else None) if info_sheet else None,
    }


@router.get("/{exam_set_id}/memo/full", response_model=None)
async def get_memo_full(exam_set_id: UUID) -> dict:
    """Return full reconstructed memo: cover_page, marker_notes, answers[], mark_breakdown. Missing sections as null."""
    client = get_supabase_client()
    row = await get_exam_set(client, exam_set_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam set not found")
    memo_id = row.get("memo_id")
    if not memo_id:
        return {
            "exam_set_id": str(exam_set_id),
            "cover_page": None,
            "marker_notes": None,
            "answers": [],
            "mark_breakdown": None,
        }
    memo_uuid = UUID(str(memo_id)) if isinstance(memo_id, str) else memo_id
    cover = await get_section(client, memo_uuid, "cover_page")
    marker_notes = await get_section(client, memo_uuid, "marker_notes")
    mark_breakdown = await get_section(client, memo_uuid, "mark_breakdown")
    memo_extraction = await get_memo_extraction_by_scraped_file_id(client, memo_uuid)
    answers = []
    if memo_extraction and memo_extraction.get("sections"):
        answers = memo_extraction["sections"]
    return {
        "exam_set_id": str(exam_set_id),
        "cover_page": (cover.get("content") if isinstance(cover, dict) else None) if cover else None,
        "marker_notes": (marker_notes.get("content") if isinstance(marker_notes, dict) else None) if marker_notes else None,
        "answers": answers,
        "mark_breakdown": (mark_breakdown.get("content") if isinstance(mark_breakdown, dict) else None) if mark_breakdown else None,
    }
