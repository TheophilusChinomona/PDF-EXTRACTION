"""
Validation API: batch validation, job status, progress, single result, review queue, resolve.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.db.supabase_client import get_supabase_client
from app.db.validation_results import (
    get_validation_result,
    list_review_queue,
    update_validation_result,
)
from app.db.validation_jobs import (
    create_validation_job,
    get_validation_job,
    update_validation_job,
)
from app.models.validation import (
    ValidationBatchRequest,
    ValidationBatchResponse,
    ValidationJobProgressResponse,
    ValidationJobResponse,
    ValidationResultResponse,
    ReviewQueueItem,
    ReviewQueueResponse,
    ReviewResolveRequest,
    ReviewResolveResponse,
)

router = APIRouter(prefix="/api/validation", tags=["validation"])
logger = logging.getLogger(__name__)


@router.post("/batch", status_code=status.HTTP_202_ACCEPTED)
async def validation_batch(body: ValidationBatchRequest) -> ValidationBatchResponse:
    """Trigger batch validation for the given scraped_file_ids. Returns job_id and status."""
    from app.config import get_settings
    from app.services.validation_batch import submit_validation_batch

    client = get_supabase_client()
    job_id = await create_validation_job(client, total_files=len(body.scraped_file_ids), status="queued")
    scraped_file_id_strs = [str(sid) for sid in body.scraped_file_ids]
    settings = get_settings()
    threshold = getattr(settings, "batch_api_threshold", 100)
    if len(scraped_file_id_strs) >= threshold:
        try:
            gemini_batch_job_id = await submit_validation_batch(scraped_file_id_strs, job_id)
            return ValidationBatchResponse(
                job_id=UUID(job_id),
                status="batch_submitted",
                total_files=len(body.scraped_file_ids),
                gemini_batch_job_id=UUID(gemini_batch_job_id),
            )
        except Exception as e:
            logger.exception("Batch API submit failed: %s", e)
            # Fall through to queued (online path when worker runs)
    return ValidationBatchResponse(
        job_id=UUID(job_id),
        status="queued",
        total_files=len(body.scraped_file_ids),
    )


@router.get("/{job_id}", response_model=ValidationJobResponse)
async def get_validation_job_endpoint(job_id: UUID) -> ValidationJobResponse:
    """Get validation job status and progress counts."""
    client = get_supabase_client()
    row = await get_validation_job(client, job_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Validation job not found")
    return ValidationJobResponse(
        id=UUID(row["id"]),
        status=row["status"],
        total_files=row["total_files"],
        processed_files=row["processed_files"],
        accepted_files=row["accepted_files"],
        rejected_files=row["rejected_files"],
        review_required_files=row["review_required_files"],
        failed_files=row["failed_files"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        completed_at=row.get("completed_at"),
    )


@router.get("/{job_id}/progress", response_model=ValidationJobProgressResponse)
async def get_validation_job_progress(job_id: UUID) -> ValidationJobProgressResponse:
    """Lightweight progress for polling; includes ETA placeholder."""
    client = get_supabase_client()
    row = await get_validation_job(client, job_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Validation job not found")
    total = row["total_files"] or 0
    processed = row["processed_files"] or 0
    pct = (100.0 * processed / total) if total else 0.0
    return ValidationJobProgressResponse(
        job_id=UUID(row["id"]),
        status=row["status"],
        processed_files=processed,
        total_files=total,
        progress_pct=round(pct, 2),
        estimated_seconds_remaining=None,
    )


@router.get("/result/{scraped_file_id}", response_model=ValidationResultResponse)
async def get_validation_result_endpoint(scraped_file_id: UUID) -> ValidationResultResponse:
    """Get validation result for a single document."""
    client = get_supabase_client()
    row = await get_validation_result(client, scraped_file_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Validation result not found")
    return ValidationResultResponse(
        scraped_file_id=UUID(row["scraped_file_id"]),
        status=row["status"],
        confidence_score=row.get("confidence_score"),
        subject=row.get("subject"),
        grade=row.get("grade"),
        year=row.get("year"),
        paper_type=row.get("paper_type"),
        paper_number=row.get("paper_number"),
        session=row.get("session"),
        syllabus=row.get("syllabus"),
        metadata=row.get("metadata") or {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("/review-queue", response_model=ReviewQueueResponse)
async def get_review_queue(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ReviewQueueResponse:
    """List documents pending manual review with pagination."""
    client = get_supabase_client()
    items, total = await list_review_queue(client, page=page, page_size=page_size)
    return ReviewQueueResponse(
        items=[
            ReviewQueueItem(
                scraped_file_id=UUID(r["scraped_file_id"]),
                status=r["status"],
                confidence_score=r.get("confidence_score"),
                subject=r.get("subject"),
                grade=r.get("grade"),
                year=r.get("year"),
                session=r.get("session"),
                syllabus=r.get("syllabus"),
                metadata=r.get("metadata") or {},
                created_at=r["created_at"],
            )
            for r in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/review/{scraped_file_id}/resolve", response_model=ReviewResolveResponse)
async def resolve_review(scraped_file_id: UUID, body: ReviewResolveRequest) -> ReviewResolveResponse:
    """Approve or reject a document in review queue. If approved, extraction is triggered (via DB trigger when status -> correct)."""
    if body.action not in ("approve", "reject"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="action must be 'approve' or 'reject'",
        )
    client = get_supabase_client()
    row = await get_validation_result(client, scraped_file_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Validation result not found")
    if row["status"] != "review_required":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document is not in review (status={row['status']})",
        )
    new_status = "correct" if body.action == "approve" else "rejected"
    metadata = dict(row.get("metadata") or {})
    if body.notes:
        metadata["resolve_notes"] = body.notes
    if body.metadata_override:
        metadata.update(body.metadata_override)
    await update_validation_result(
        client,
        scraped_file_id,
        status=new_status,
        metadata_override=metadata if (body.notes or body.metadata_override) else None,
    )
    extraction_triggered = body.action == "approve"
    return ReviewResolveResponse(
        scraped_file_id=scraped_file_id,
        status=new_status,
        extraction_triggered=extraction_triggered,
    )
