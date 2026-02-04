"""
Extract document sections (cover, instructions, marker notes, information sheet)
and store in document_sections. Single pass over PDF; used before question/answer extraction.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from google import genai
from google.genai import types

from app.db.document_sections import upsert_document_section
from app.db.supabase_client import get_supabase_client
from app.services.opendataloader_extractor import extract_pdf_structure

logger = logging.getLogger(__name__)

SECTION_EXTRACTION_PROMPT_QP = """Extract the following sections from this exam QUESTION PAPER. Return JSON only.

1. cover_page (page 1): organization, certificate type, grade, subject, paper number, session/year, document_type ("Question Paper"), marks, time, page_count. Use keys: organization, country, certificate, grade, subject, session, document_type, marks, time, page_count, info_sheet_count.

2. student_instructions (usually page 2): header (e.g. "INSTRUCTIONS AND INFORMATION"), items as array of {number, text}, notes as array of strings.

3. information_sheet (last page if present): header "INFORMATION SHEET", formulae as array of {name, latex}, tables as array, constants as array. If no information sheet, set to null.

Return valid JSON: {"cover_page": {...}, "student_instructions": {...}, "information_sheet": {...} or null}"""

SECTION_EXTRACTION_PROMPT_MEMO = """Extract the following sections from this MARKING GUIDELINES / MEMO. Return JSON only.

1. cover_page (page 1): organization, certificate, grade, subject, paper number, session/year, document_type ("Marking Guidelines"), marks, page_count. Use keys: organization, country, certificate, grade, subject, session, document_type, marks, page_count.

2. marker_notes (pages 2-6 typically): header "NOTES TO MARKERS", preamble text, sections as array of {number, title, content or subsections}, cognitive_verbs as {simple: [], complex: []}, essay_marking as {max_content, max_insight, insight_components}. Extract marking colours, section-specific instructions.

Return valid JSON: {"cover_page": {...}, "marker_notes": {...}}"""


async def _extract_sections_with_gemini(
    client: genai.Client,
    file_path: str,
    is_question_paper: bool,
    model: str = "gemini-2.0-flash",
) -> Dict[str, Any]:
    """Call Gemini to extract sections; returns dict with cover_page, and student_instructions/marker_notes, and optionally information_sheet."""
    doc_structure = extract_pdf_structure(file_path)
    prompt = (
        SECTION_EXTRACTION_PROMPT_QP + "\n\nDocument content:\n" + (doc_structure.markdown or "")[:12000]
        if is_question_paper
        else SECTION_EXTRACTION_PROMPT_MEMO + "\n\nDocument content:\n" + (doc_structure.markdown or "")[:12000]
    )

    def _call() -> Any:
        return client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

    response = await asyncio.to_thread(_call)
    text = response.text if response else None
    if not text or not text.strip():
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("Section extraction JSON decode failed: %s", e)
        return {}


async def extract_and_store_sections(
    scraped_file_id: UUID,
    file_path: str,
    is_question_paper: bool,
    *,
    supabase_client=None,
    gemini_client: Optional[genai.Client] = None,
) -> None:
    """
    Extract cover, instructions/marker_notes, and (for QP) information_sheet;
    persist each to document_sections. Call before question/answer extraction.
    """
    from app.services.gemini_client import get_gemini_client

    client = supabase_client or get_supabase_client()
    gclient = gemini_client or get_gemini_client()
    data = await _extract_sections_with_gemini(gclient, file_path, is_question_paper)

    # Cover page
    cover = data.get("cover_page")
    if isinstance(cover, dict):
        await upsert_document_section(
            client,
            scraped_file_id,
            "cover_page",
            cover,
            page_start=1,
            page_end=1,
            extraction_method="gemini",
            confidence_score=85,
        )

    if is_question_paper:
        instructions = data.get("student_instructions")
        if isinstance(instructions, dict):
            await upsert_document_section(
                client,
                scraped_file_id,
                "student_instructions",
                instructions,
                page_start=2,
                page_end=2,
                extraction_method="gemini",
                confidence_score=80,
            )
        info_sheet = data.get("information_sheet")
        if isinstance(info_sheet, dict):
            await upsert_document_section(
                client,
                scraped_file_id,
                "information_sheet",
                info_sheet,
                extraction_method="gemini",
                confidence_score=75,
            )
    else:
        marker_notes = data.get("marker_notes")
        if isinstance(marker_notes, dict):
            await upsert_document_section(
                client,
                scraped_file_id,
                "marker_notes",
                marker_notes,
                page_start=2,
                page_end=6,
                extraction_method="gemini",
                confidence_score=80,
            )
