"""Pydantic models for exam sets (QP–Memo linking)."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ExamSetListItem(BaseModel):
    """Exam set summary for list endpoint."""
    id: UUID
    subject: str
    grade: int
    paper_number: int
    year: int
    session: str
    syllabus: Optional[str] = None
    question_paper_id: Optional[UUID] = None
    memo_id: Optional[UUID] = None
    match_method: Optional[str] = None
    match_confidence: Optional[int] = None
    status: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ExamSetDetail(ExamSetListItem):
    """Full exam set with optional section availability flags."""
    matched_at: Optional[datetime] = None
    matched_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    has_instructions: Optional[bool] = None
    has_marker_notes: Optional[bool] = None
    has_information_sheet: Optional[bool] = None


class MatchRequest(BaseModel):
    """Request body for POST /api/exam-sets/match."""
    question_paper_id: UUID = Field(..., description="scraped_files.id of the question paper")
    memo_id: UUID = Field(..., description="scraped_files.id of the memo")
