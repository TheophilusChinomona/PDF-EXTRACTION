"""Pydantic models for validation API (validation_results, validation_jobs, review)."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Validation result (single document)
# ---------------------------------------------------------------------------

class ValidationResultResponse(BaseModel):
    """Validation result for a single document."""
    scraped_file_id: UUID = Field(description="Document UUID")
    status: str = Field(description="correct, rejected, review_required, pending, error")
    confidence_score: Optional[float] = Field(default=None, ge=0, le=1)
    subject: Optional[str] = None
    grade: Optional[str] = None
    year: Optional[int] = None
    paper_type: Optional[str] = None
    paper_number: Optional[int] = None
    session: Optional[str] = None
    syllabus: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(description="When result was created")
    updated_at: datetime = Field(description="When result was last updated")


# ---------------------------------------------------------------------------
# Validation job (batch)
# ---------------------------------------------------------------------------

class ValidationBatchRequest(BaseModel):
    """Request to trigger batch validation for given files."""
    scraped_file_ids: List[UUID] = Field(..., min_length=1, description="List of scraped_file_id UUIDs to validate")


class ValidationJobResponse(BaseModel):
    """Validation job status and progress."""
    id: UUID = Field(description="Validation job ID")
    status: str = Field(description="pending, queued, running, completed, failed, paused, cancelled")
    total_files: int = Field(ge=0)
    processed_files: int = Field(ge=0)
    accepted_files: int = Field(ge=0)
    rejected_files: int = Field(ge=0)
    review_required_files: int = Field(ge=0)
    failed_files: int = Field(ge=0)
    created_at: datetime = Field(description="When job was created")
    updated_at: datetime = Field(description="Last update")
    completed_at: Optional[datetime] = Field(default=None, description="When job completed")


class ValidationJobProgressResponse(BaseModel):
    """Lightweight progress for polling (with ETA)."""
    job_id: UUID = Field(description="Validation job ID")
    status: str = Field(description="Job status")
    processed_files: int = Field(ge=0)
    total_files: int = Field(ge=0)
    progress_pct: float = Field(ge=0, le=100, description="Progress percentage")
    estimated_seconds_remaining: Optional[float] = Field(default=None, description="ETA in seconds")


class ValidationBatchResponse(BaseModel):
    """Response when starting a batch validation job."""
    job_id: UUID = Field(description="Validation job ID")
    status: str = Field(default="queued", description="Initial status")
    total_files: int = Field(description="Number of files in batch")


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------

class ReviewQueueItem(BaseModel):
    """Single item in the review queue (documents needing manual review)."""
    scraped_file_id: UUID = Field(description="Document UUID")
    status: str = Field(description="review_required")
    confidence_score: Optional[float] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    year: Optional[int] = None
    session: Optional[str] = None
    syllabus: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(description="When result was created")


class ReviewQueueResponse(BaseModel):
    """Paginated list of documents in review queue."""
    items: List[ReviewQueueItem] = Field(default_factory=list)
    total: int = Field(ge=0, description="Total count matching filter")
    page: int = Field(ge=1, description="Current page")
    page_size: int = Field(ge=1, le=100, description="Page size")


class ReviewResolveRequest(BaseModel):
    """Request to resolve a review-required document (approve or reject)."""
    action: str = Field(..., description="approve or reject")
    notes: Optional[str] = Field(default=None, description="Optional notes")
    metadata_override: Optional[Dict[str, Any]] = Field(default=None, description="Override metadata before extraction")


class ReviewResolveResponse(BaseModel):
    """Response after resolving a review item."""
    scraped_file_id: UUID = Field(description="Document UUID")
    status: str = Field(description="Updated status: correct (if approved) or rejected")
    extraction_triggered: bool = Field(description="True if extraction was queued (approved)")
