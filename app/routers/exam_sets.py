"""Exam sets API: list, detail, manual match."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.db.document_sections import get_section
from app.db.exam_sets import (
    create_exam_set,
    find_exam_set_by_match_key,
    get_exam_set,
    list_exam_sets,
    update_exam_set,
)
from app.db.supabase_client import get_supabase_client
from app.models.exam_sets import MatchRequest
from app.services.exam_matcher import calculate_match_confidence
from app.utils.normalizers import (
    normalize_grade,
    normalize_paper_number,
    normalize_session,
    normalize_subject,
)
from app.services.batch_matcher import run_batch_matcher

router = APIRouter(prefix="/api/exam-sets", tags=["exam-sets"])


def _row_to_list_item(row: dict) -> dict:
    """Convert DB row to list item shape (UUIDs as str for JSON)."""
    out = dict(row)
    for k in ("id", "question_paper_id", "memo_id"):
        if k in out and out[k] is not None:
            out[k] = str(out[k])
    return out


@router.get("", response_model=None)
async def list_exam_sets_endpoint(
    subject: str | None = Query(None),
    grade: int | None = Query(None),
    year: int | None = Query(None),
    session: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """List exam sets with optional filters. Pagination: limit, offset. Sort: year DESC, subject ASC."""
    client = get_supabase_client()
    items, total = await list_exam_sets(
        client,
        subject=subject,
        grade=grade,
        year=year,
        session=session,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [_row_to_list_item(r) for r in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{exam_set_id}", response_model=None)
async def get_exam_set_endpoint(exam_set_id: UUID) -> dict:
    """Get exam set by id with section availability flags."""
    client = get_supabase_client()
    row = await get_exam_set(client, exam_set_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam set not found")
    qp_id = row.get("question_paper_id")
    memo_id = row.get("memo_id")
    has_instructions = False
    has_marker_notes = False
    has_information_sheet = False
    if qp_id:
        uid = UUID(str(qp_id)) if isinstance(qp_id, str) else qp_id
        inst = await get_section(client, uid, "student_instructions")
        info = await get_section(client, uid, "information_sheet")
        has_instructions = inst is not None
        has_information_sheet = info is not None
    if memo_id:
        uid = UUID(str(memo_id)) if isinstance(memo_id, str) else memo_id
        mn = await get_section(client, uid, "marker_notes")
        has_marker_notes = mn is not None
    out = _row_to_list_item(row)
    out["has_instructions"] = has_instructions
    out["has_marker_notes"] = has_marker_notes
    out["has_information_sheet"] = has_information_sheet
    return out


@router.post("/batch-match", status_code=status.HTTP_200_OK, response_model=None)
async def batch_match_endpoint(limit: int = Query(500, ge=1, le=2000)) -> dict:
    """Trigger batch matching job: scan unlinked documents and link to exam sets. Idempotent."""
    client = get_supabase_client()
    stats = await run_batch_matcher(client=client, limit=limit)
    return {
        "scanned": stats["scanned"],
        "matched": stats["matched"],
        "created": stats["created"],
        "errors": stats["errors"],
    }


@router.post("/match", status_code=status.HTTP_200_OK, response_model=None)
async def manual_match_endpoint(body: MatchRequest) -> dict:
    """Create or update exam set by manually linking question_paper_id and memo_id."""
    client = get_supabase_client()
    # We need metadata from both documents to build match key and confidence. For manual match we can
    # look up validation_results or extractions for subject/grade/year/session/paper_number.
    # Simplified: create/update by fetching existing exam_set for either QP or Memo, or create new.
    from app.db.validation_results import get_validation_result
    v_qp = await get_validation_result(client, body.question_paper_id)
    v_memo = await get_validation_result(client, body.memo_id)
    meta_qp = {
        "subject": (v_qp or {}).get("subject"),
        "grade": (v_qp or {}).get("grade"),
        "year": (v_qp or {}).get("year"),
        "session": (v_qp or {}).get("session"),
        "paper_number": (v_qp or {}).get("paper_number"),
        "syllabus": (v_qp or {}).get("syllabus"),
    }
    meta_memo = {
        "subject": (v_memo or {}).get("subject"),
        "grade": (v_memo or {}).get("grade"),
        "year": (v_memo or {}).get("year"),
        "session": (v_memo or {}).get("session"),
        "paper_number": (v_memo or {}).get("paper_number"),
        "syllabus": (v_memo or {}).get("syllabus"),
    }
    subj = normalize_subject(meta_qp.get("subject") or meta_memo.get("subject") or "")
    gr = normalize_grade(meta_qp.get("grade") or meta_memo.get("grade"))
    pn = normalize_paper_number(meta_qp.get("paper_number") or meta_memo.get("paper_number"))
    yr = meta_qp.get("year") or meta_memo.get("year") or 0
    sess = normalize_session(meta_qp.get("session") or meta_memo.get("session") or "")
    syllabus = (meta_qp.get("syllabus") or meta_memo.get("syllabus") or "").strip() or None
    if not subj or gr is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not derive subject/grade from validation results for both documents",
        )
    confidence = calculate_match_confidence(subj, gr, pn, yr, sess)
    existing = await find_exam_set_by_match_key(client, subject=subj, grade=gr, paper_number=pn, year=yr, session=sess, syllabus=syllabus)
    if existing:
        exam_set_id = UUID(existing["id"])
        await update_exam_set(
            client,
            exam_set_id,
            question_paper_id=body.question_paper_id,
            memo_id=body.memo_id,
            status="matched",
            match_confidence=confidence,
            matched_by="manual",
        )
        row = await get_exam_set(client, exam_set_id)
    else:
        exam_set_id_str = await create_exam_set(
            client,
            subject=subj,
            grade=gr,
            paper_number=pn,
            year=yr,
            session=sess,
            syllabus=syllabus,
            question_paper_id=body.question_paper_id,
            memo_id=body.memo_id,
            match_method="manual",
            match_confidence=confidence,
        )
        row = await get_exam_set(client, UUID(exam_set_id_str))
    if not row:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create/update exam set")
    return _row_to_list_item(row)
