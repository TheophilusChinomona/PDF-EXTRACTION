"""Pydantic models for memo/marking guideline extraction.

This module defines the data structures for extracting marking guidelines
(memos) from South African matric examination papers. It extends the base
GeminiCompatibleModel to ensure compatibility with Gemini's JSON schema requirements.
"""

from typing import List, Optional, Dict, Any, Union
from pydantic import Field

from app.models.extraction import GeminiCompatibleModel


class EssayStructure(GeminiCompatibleModel):
    """Essay structure for Section C essay questions.

    Captures the hierarchical structure of essay answers including
    introduction, body sections with sub-topics, and conclusion.

    Body sections use flexible Dict[str, Any] to handle various structures:
    - Simple lists: {"sub_topic": "...", "points": [...]}
    - Positive/negative splits: {"sub_topic": "...", "positives": [...], "negatives": [...]}
    - Rights lists: {"sub_topic": "...", "rights": [...]}
    """
    introduction: List[str] = Field(
        default_factory=list,
        description="List of valid introduction points"
    )
    body_sections: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of sub-topics. Each dict must have 'sub_topic' key plus keys like 'points', 'positives', 'negatives', 'rights' containing lists of valid facts"
    )
    conclusion: List[str] = Field(
        default_factory=list,
        description="List of valid conclusion points"
    )


class MemoQuestion(GeminiCompatibleModel):
    """Represents the correct answer block for a specific question.

    Handles various answer types including:
    - Multiple choice
    - Fill-in-blank (with sub-questions)
    - Match columns
    - Essay questions with structured answers
    - Questions with model answers (list of valid facts)
    """
    id: str = Field(description="The question number, e.g., '1.1', '2.3', '5'")
    text: Optional[str] = Field(
        default=None,
        description="The topic/heading of the answer, e.g., 'Advantages of TQM'"
    )
    type: Optional[str] = Field(
        default=None,
        description="Question type: 'Multiple Choice', 'Essay', 'Match Columns', 'Complete the statements', etc."
    )

    # Answer data - supports multiple formats
    model_answers: Optional[Union[List[str], Dict[str, List[str]]]] = Field(
        default=None,
        description="List of ALL valid facts listed in the memo. For questions with positive/negative aspects, use dict with 'positives'/'negatives' keys"
    )
    answers: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="For sub-questions like 1.2.1, 1.2.2. Format: [{'sub_id': '1.2.1', 'value': 'Answer'}]"
    )
    structured_answer: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="For questions requiring paired answers. Format: [{'strategy': '...', 'motivation': '...'}] or [{'function': '...', 'motivation': '...'}]"
    )

    # Grading information
    marks: Optional[int] = Field(
        default=None,
        description="Total marks allocated to this question"
    )
    max_marks: Optional[int] = Field(
        default=None,
        description="Maximum marks (used when more facts are given than marks available)"
    )
    marker_instruction: Optional[str] = Field(
        default=None,
        description="CRITICAL instructions for the AI grader, e.g., 'Mark the first TWO only' or 'Do not award marks for motivations if strategies are incorrect'"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Additional notes or clarifications about the answer"
    )
    topic: Optional[str] = Field(
        default=None,
        description="Main topic for essay questions (Section C)"
    )

    # Essay-specific structure
    essay_structure: Optional[EssayStructure] = Field(
        default=None,
        description="Only populated for Essay questions (Section C)"
    )


class MemoSection(GeminiCompatibleModel):
    """Represents a section in the marking guideline.

    Sections typically include:
    - SECTION A: Multiple choice, fill-in-blank, matching
    - SECTION B: Short answer and application questions
    - SECTION C: Essay questions
    """
    section_id: str = Field(
        description="Section identifier: 'SECTION A', 'SECTION B', 'SECTION C'"
    )
    questions: List[MemoQuestion] = Field(
        default_factory=list,
        description="List of questions in this section"
    )


class MarkingGuideline(GeminiCompatibleModel):
    """Complete marking guideline (memorandum) extraction result.

    This is the primary output model for memo extraction, containing all
    correct answers and marking instructions for an examination paper.
    """
    meta: Dict[str, Union[str, int]] = Field(
        description="Document metadata: subject, type, year, session, grade, total_marks"
    )
    sections: List[MemoSection] = Field(
        default_factory=list,
        description="List of sections with questions and answers"
    )
    processing_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about processing method, quality scores, cost savings, cache stats"
    )

    def build_canonical_filename(self, document_id: str, suffix: str = "mg") -> str:
        """Build a canonical filename from extracted metadata and document ID.

        Format: {document_id}_{subject}-gr{grade}-{session}-{year}-{suffix}
        Example: a1b2c3d4_business-studies-p1-gr12-may-june-2025-mg

        Args:
            document_id: UUID or unique identifier for this document.
            suffix: File suffix label (default: "mg" for marking guideline).

        Returns:
            Canonical filename stem (no extension).
        """
        import re

        subject = str(self.meta.get("subject") or "unknown").strip()
        grade = str(self.meta.get("grade") or "0").strip().lower().replace("grade ", "")
        year = str(self.meta.get("year") or "0").strip()
        session = str(self.meta.get("session") or "unknown").strip()

        # Normalise: lowercase, replace spaces/slashes with hyphens, strip non-alnum
        def _slug(text: str) -> str:
            text = text.lower()
            text = re.sub(r'[/\\]+', '-', text)
            text = re.sub(r'[^a-z0-9\-]+', '-', text)
            text = re.sub(r'-+', '-', text)
            return text.strip('-')

        parts = [
            document_id,
            _slug(subject),
            f"gr{_slug(grade)}",
            _slug(session),
            year,
            suffix,
        ]
        return "-".join(parts)
