"""Pydantic model for document classification results.

Used by the document classifier to report whether a PDF is a
question paper or a marking guideline (memo).
"""

from typing import Any, Dict, Literal
from pydantic import BaseModel, Field


class ClassificationResult(BaseModel):
    """Result of auto-classifying a PDF document type."""

    doc_type: Literal["question_paper", "memo"] = Field(
        description="Classified document type"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Classification confidence (0.0 to 1.0)"
    )
    method: Literal["filename", "content_keywords", "gemini", "user_provided"] = Field(
        description="Which classification layer produced the result"
    )
    signals: Dict[str, Any] = Field(
        default_factory=dict,
        description="Debug info: matched patterns, keyword hits, etc."
    )
