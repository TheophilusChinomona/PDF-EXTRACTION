"""Pydantic models for PDF extraction results.

This module defines the data structures used throughout the extraction pipeline,
from bounding boxes to complete extraction results with validation.

Includes both academic paper models (legacy) and exam paper models (current).
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class GeminiCompatibleModel(BaseModel):
    """Base model with Gemini API-compatible JSON schema.

    Gemini's API doesn't support additionalProperties in JSON schemas.
    This base class configures Pydantic to generate compatible schemas.
    """
    model_config = ConfigDict(
        # Remove additionalProperties from JSON schema for Gemini compatibility
        json_schema_extra={
            "additionalProperties": False
        }
    )


# =============================================================================
# EXAM PAPER MODELS (Primary use case)
# =============================================================================

class MultipleChoiceOption(GeminiCompatibleModel):
    """A single option for a multiple choice question."""
    label: str = Field(description="Option label: A, B, C, or D")
    text: str = Field(description="The content/text of the option")


class Question(GeminiCompatibleModel):
    """A single question from an exam paper."""
    id: str = Field(description="The full question number, e.g., 1.1.1, 2.3.2")
    text: str = Field(description="The actual question text (transcribed exactly)")
    marks: Optional[int] = Field(default=None, description="Marks allocated to this question")
    options: Optional[List[MultipleChoiceOption]] = Field(
        default=None,
        description="For MCQs only: list of A/B/C/D options"
    )
    scenario: Optional[str] = Field(
        default=None,
        description="The case study/scenario text if question references one"
    )
    guide_table: Optional[List[Any]] = Field(
        default=None,
        description="For fill-in or matching tables (flexible format)"
    )


class QuestionGroup(GeminiCompatibleModel):
    """A group of related questions (Section or Main Question)."""
    group_id: str = Field(description="e.g., 'QUESTION 1' or 'SECTION A'")
    title: str = Field(description="The group heading text")
    instructions: Optional[str] = Field(
        default=None,
        description="Specific instructions for this section/group"
    )
    questions: List[Question] = Field(
        default_factory=list,
        description="List of questions in this group"
    )


class FullExamPaper(GeminiCompatibleModel):
    """Complete extraction result for an examination paper.

    This is the primary output model for exam paper extraction.
    """
    subject: str = Field(description="Subject name, e.g., 'Business Studies P1'")
    syllabus: str = Field(description="Syllabus type, e.g., 'SC' or 'NSC'")
    year: int = Field(description="Examination year, e.g., 2025")
    session: str = Field(description="Examination session, e.g., 'MAY/JUNE' or 'NOV'")
    grade: str = Field(description="Grade level, e.g., '12'")
    total_marks: int = Field(default=150, description="Total marks for the paper")
    groups: List[QuestionGroup] = Field(
        default_factory=list,
        description="Question groups (Sections or Main Questions)"
    )
    processing_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about processing method, quality scores, etc."
    )


# =============================================================================
# ACADEMIC PAPER MODELS (Legacy - kept for backward compatibility)
# =============================================================================


class BoundingBox(GeminiCompatibleModel):
    """Bounding box coordinates for an element in the PDF.

    Coordinates are in PDF coordinate space (points, 72 DPI).
    Origin (0,0) is typically bottom-left of the page.

    Note: Used primarily by academic paper extraction (legacy).
    """
    x1: float = Field(description="Left coordinate")
    y1: float = Field(description="Bottom coordinate")
    x2: float = Field(description="Right coordinate")
    y2: float = Field(description="Top coordinate")
    page: int = Field(ge=1, description="Page number (1-indexed)")


class ExtractedMetadata(GeminiCompatibleModel):
    """Metadata extracted from the academic paper.

    Includes bibliographic information typically found in paper headers.
    """
    title: str = Field(description="Paper title")
    authors: List[str] = Field(default_factory=list, description="List of author names")
    journal: Optional[str] = Field(default=None, description="Journal or publication venue")
    year: Optional[int] = Field(default=None, ge=1900, le=2100, description="Publication year")
    doi: Optional[str] = Field(default=None, description="Digital Object Identifier")


class ExtractedSection(GeminiCompatibleModel):
    """A section of the document with its content and location.

    Represents hierarchical document structure (e.g., Introduction, Methods).
    """
    heading: str = Field(description="Section heading text")
    content: str = Field(description="Section content")
    page_number: int = Field(ge=1, description="Starting page number (1-indexed)")
    bbox: Optional[BoundingBox] = Field(default=None, description="Bounding box of section heading")


class ExtractedTable(GeminiCompatibleModel):
    """Table extracted from the document with structure and location.

    Data format preserves table structure for downstream processing.
    """
    caption: str = Field(default="", description="Table caption or title")
    page_number: int = Field(ge=1, description="Page number where table appears (1-indexed)")
    data: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Table data as list of row dictionaries"
    )
    bbox: Optional[BoundingBox] = Field(default=None, description="Bounding box of entire table")


class ExtractedReference(GeminiCompatibleModel):
    """A bibliographic reference from the paper.

    Parsed from the references/bibliography section.
    """
    citation_text: str = Field(description="Full citation text as it appears")
    authors: List[str] = Field(default_factory=list, description="Parsed author names")
    year: Optional[int] = Field(default=None, description="Publication year")
    title: Optional[str] = Field(default=None, description="Referenced work title")


class DocumentStructure(GeminiCompatibleModel):
    """Intermediate representation of PDF structure from OpenDataLoader.

    This is the output of local preprocessing before Gemini semantic analysis.
    """
    markdown: str = Field(description="Document exported as Markdown")
    tables: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Raw table data from OpenDataLoader"
    )
    bounding_boxes: Dict[str, BoundingBox] = Field(
        default_factory=dict,
        description="Bounding boxes keyed by element_id"
    )
    quality_score: float = Field(
        ge=0.0, le=1.0,
        description="Quality score for routing decision (0.0 to 1.0)"
    )
    element_count: int = Field(ge=0, description="Number of structural elements detected")


class ExtractionResult(GeminiCompatibleModel):
    """Complete extraction result combining structural and semantic data.

    This is the final output of the hybrid extraction pipeline,
    merging OpenDataLoader structure with Gemini semantic understanding.
    """
    metadata: ExtractedMetadata = Field(description="Document metadata")
    abstract: Optional[str] = Field(default=None, description="Paper abstract")
    sections: List[ExtractedSection] = Field(
        default_factory=list,
        description="Document sections with hierarchy"
    )
    tables: List[ExtractedTable] = Field(
        default_factory=list,
        description="Extracted tables with structure"
    )
    references: List[ExtractedReference] = Field(
        default_factory=list,
        description="Bibliographic references"
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in extraction quality (0.0 to 1.0)"
    )
    bounding_boxes: Dict[str, BoundingBox] = Field(
        default_factory=dict,
        description="Bounding boxes for all elements (enables citations)"
    )
    processing_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about processing method, quality scores, cost savings"
    )
