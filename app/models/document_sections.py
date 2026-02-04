"""Pydantic models for document sections (cover, instructions, marker notes, etc.)."""

from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SectionType(str, Enum):
    """Section type enum for document_sections."""
    cover_page = "cover_page"
    student_instructions = "student_instructions"
    marker_notes = "marker_notes"
    information_sheet = "information_sheet"
    mark_breakdown = "mark_breakdown"
    appendix = "appendix"


class DocumentSection(BaseModel):
    """Single document section."""
    id: UUID
    scraped_file_id: UUID
    section_type: str
    title: Optional[str] = None
    content: dict[str, Any] = Field(default_factory=dict)
    raw_text: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    extraction_method: Optional[str] = None
    confidence_score: Optional[int] = None

    model_config = {"from_attributes": True}
