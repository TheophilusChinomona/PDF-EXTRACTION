"""Pydantic models for paper reconstruction API responses."""

from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class QuestionPaperFull(BaseModel):
    """Full reconstructed question paper (cover + instructions + questions + information_sheet)."""
    exam_set_id: UUID
    cover_page: Optional[dict[str, Any]] = None
    instructions: Optional[dict[str, Any]] = None
    questions: List[Any] = Field(default_factory=list)
    information_sheet: Optional[dict[str, Any]] = None


class MemoFull(BaseModel):
    """Full reconstructed memo (cover + marker_notes + answers + mark_breakdown)."""
    exam_set_id: UUID
    cover_page: Optional[dict[str, Any]] = None
    marker_notes: Optional[dict[str, Any]] = None
    answers: List[Any] = Field(default_factory=list)
    mark_breakdown: Optional[dict[str, Any]] = None
