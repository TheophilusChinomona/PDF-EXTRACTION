"""Three-layer cascade document classifier.

Determines whether a PDF is a question paper or a marking guideline (memo)
using a cascade of increasingly expensive methods:

1. Filename heuristics (instant, free)
2. Content keyword scan (needs markdown text, no API call)
3. Gemini lightweight call (fallback, ~200ms)
"""

import re
from typing import Optional

from google import genai

from app.models.classification import ClassificationResult


# ---------------------------------------------------------------------------
# Layer 1 – Filename heuristics
# ---------------------------------------------------------------------------

_MEMO_FILENAME_PATTERNS = [
    re.compile(r'\bMG\b', re.IGNORECASE),
    re.compile(r'\bmemo\b', re.IGNORECASE),
    re.compile(r'\bmarking\b', re.IGNORECASE),
    re.compile(r'\bmemorandum\b', re.IGNORECASE),
]

_QP_FILENAME_PATTERNS = [
    re.compile(r'\bQP\b', re.IGNORECASE),
    re.compile(r'\bquestion[_\s]?paper\b', re.IGNORECASE),
]


def _classify_by_filename(filename: str) -> Optional[ClassificationResult]:
    """Classify by scanning the filename for known indicators."""
    memo_hits = [p.pattern for p in _MEMO_FILENAME_PATTERNS if p.search(filename)]
    qp_hits = [p.pattern for p in _QP_FILENAME_PATTERNS if p.search(filename)]

    has_memo = len(memo_hits) > 0
    has_qp = len(qp_hits) > 0

    # Only return when one side matches and the other doesn't
    if has_memo and not has_qp:
        return ClassificationResult(
            doc_type="memo",
            confidence=0.9,
            method="filename",
            signals={"memo_patterns": memo_hits},
        )
    if has_qp and not has_memo:
        return ClassificationResult(
            doc_type="question_paper",
            confidence=0.9,
            method="filename",
            signals={"qp_patterns": qp_hits},
        )

    return None  # Ambiguous or no match


# ---------------------------------------------------------------------------
# Layer 2 – Content keyword scan
# ---------------------------------------------------------------------------

_MEMO_CONTENT_PHRASES = [
    "marking guideline",
    "memorandum",
    "notes to markers",
    "model answer",
    "mark allocation",
    "marks will be awarded",
]

_QP_CONTENT_PHRASES = [
    "instructions and information",
    "answer all",
    "write in the answer book",
    "this question paper consists of",
    "read the following",
    "answer book",
]


def _classify_by_content(markdown_text: str) -> Optional[ClassificationResult]:
    """Classify by scanning the first ~3000 chars for known phrases."""
    sample = markdown_text[:3000].lower()

    memo_hits = [p for p in _MEMO_CONTENT_PHRASES if p in sample]
    qp_hits = [p for p in _QP_CONTENT_PHRASES if p in sample]

    memo_score = len(memo_hits)
    qp_score = len(qp_hits)

    # Return if one side clearly dominates
    if memo_score > 0 and memo_score > qp_score:
        confidence = min(0.7 + 0.05 * memo_score, 0.95)
        return ClassificationResult(
            doc_type="memo",
            confidence=confidence,
            method="content_keywords",
            signals={"memo_phrases": memo_hits, "qp_phrases": qp_hits},
        )
    if qp_score > 0 and qp_score > memo_score:
        confidence = min(0.7 + 0.05 * qp_score, 0.95)
        return ClassificationResult(
            doc_type="question_paper",
            confidence=confidence,
            method="content_keywords",
            signals={"memo_phrases": memo_hits, "qp_phrases": qp_hits},
        )

    return None


# ---------------------------------------------------------------------------
# Layer 3 – Gemini lightweight call (fallback)
# ---------------------------------------------------------------------------

def _classify_by_gemini(
    markdown_text: str,
    gemini_client: genai.Client,
    model: str = "gemini-3-flash-preview",
) -> ClassificationResult:
    """Classify using a cheap one-word Gemini prompt."""
    from google.genai import types

    sample = markdown_text[:2000]
    prompt = (
        "You are a document classifier. Read the text below and reply with "
        "EXACTLY one word: either 'memo' or 'question_paper'.\n\n"
        f"---\n{sample}\n---"
    )

    response = gemini_client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0),
    )

    answer = (response.text or "").strip().lower()

    if "memo" in answer:
        doc_type = "memo"
    else:
        doc_type = "question_paper"

    return ClassificationResult(
        doc_type=doc_type,
        confidence=0.75,
        method="gemini",
        signals={"raw_answer": answer},
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def classify_document(
    filename: str,
    markdown_text: Optional[str] = None,
    gemini_client: Optional[genai.Client] = None,
) -> ClassificationResult:
    """Run the three-layer cascade and return as soon as a layer is confident.

    Args:
        filename: Original filename of the uploaded PDF.
        markdown_text: OpenDataLoader markdown (needed for layers 2-3).
        gemini_client: Gemini client (needed for layer 3 only).

    Returns:
        ClassificationResult with doc_type, confidence, method, and debug signals.
    """
    # Layer 1: filename
    result = _classify_by_filename(filename)
    if result is not None:
        return result

    # Layer 2: content keywords (requires markdown)
    if markdown_text:
        result = _classify_by_content(markdown_text)
        if result is not None:
            return result

    # Layer 3: Gemini (requires both markdown and client)
    if markdown_text and gemini_client is not None:
        try:
            return _classify_by_gemini(markdown_text, gemini_client)
        except Exception:
            pass  # Fall through to default

    # Default fallback: question paper
    return ClassificationResult(
        doc_type="question_paper",
        confidence=0.5,
        method="content_keywords",
        signals={"reason": "no_layer_matched"},
    )
