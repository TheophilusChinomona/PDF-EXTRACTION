"""Validation response schema for Gemini (document metadata extraction)."""

from typing import Any

# JSON schema for Gemini structured output (validation: grade, subject, year, etc.)
VALIDATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "description": "Subject name"},
        "grade": {"type": "integer", "description": "Grade level"},
        "year": {"type": "integer", "description": "Exam year"},
        "paper_number": {"type": "integer", "description": "Paper number (1, 2, etc.)"},
        "session": {"type": "string", "description": "Session e.g. MAY/JUNE, NOV"},
        "syllabus": {"type": "string", "description": "Syllabus e.g. NSC, IEB"},
        "confidence": {"type": "number", "description": "Confidence score 0-1"},
    },
    "required": [],
}


def validate_result(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a validation result from Gemini.

    Returns a dict suitable for validation_results update (subject, grade, year, etc.).
    """
    out: dict[str, Any] = {}
    if "subject" in data and data["subject"] is not None:
        out["subject"] = str(data["subject"]).strip() or None
    if "grade" in data and data["grade"] is not None:
        try:
            out["grade"] = str(int(data["grade"]))
        except (TypeError, ValueError):
            out["grade"] = str(data["grade"]).strip() or None
    if "year" in data and data["year"] is not None:
        try:
            out["year"] = int(data["year"])
        except (TypeError, ValueError):
            out["year"] = None
    if "paper_number" in data and data["paper_number"] is not None:
        try:
            out["paper_number"] = int(data["paper_number"])
        except (TypeError, ValueError):
            out["paper_number"] = None
    if "session" in data and data["session"] is not None:
        out["session"] = str(data["session"]).strip() or None
    if "syllabus" in data and data["syllabus"] is not None:
        out["syllabus"] = str(data["syllabus"]).strip() or None
    if "confidence" in data and data["confidence"] is not None:
        try:
            c = float(data["confidence"])
            out["confidence_score"] = max(0.0, min(1.0, c))
        except (TypeError, ValueError):
            out["confidence_score"] = None
    return out
