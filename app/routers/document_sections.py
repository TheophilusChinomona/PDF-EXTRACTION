"""Document sections API: list sections, get one section by type."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.db.document_sections import get_section, list_sections_by_file
from app.db.supabase_client import get_supabase_client

router = APIRouter(prefix="/api/documents", tags=["document-sections"])

VALID_SECTION_TYPES = frozenset({
    "cover_page",
    "student_instructions",
    "marker_notes",
    "information_sheet",
    "mark_breakdown",
    "appendix",
})


@router.get("/{scraped_file_id}/sections", response_model=None)
async def list_document_sections(scraped_file_id: UUID) -> list:
    """Return all sections for a document. Includes extraction metadata (method, confidence, page range)."""
    client = get_supabase_client()
    sections = await list_sections_by_file(client, scraped_file_id)
    return [
        {
            "id": str(s.get("id")),
            "scraped_file_id": str(s.get("scraped_file_id")),
            "section_type": s.get("section_type"),
            "title": s.get("title"),
            "content": s.get("content"),
            "raw_text": s.get("raw_text"),
            "page_start": s.get("page_start"),
            "page_end": s.get("page_end"),
            "extraction_method": s.get("extraction_method"),
            "confidence_score": s.get("confidence_score"),
        }
        for s in sections
    ]


@router.get("/{scraped_file_id}/sections/{section_type}", response_model=None)
async def get_document_section(scraped_file_id: UUID, section_type: str) -> dict:
    """Return a specific section by type. 404 if section does not exist."""
    if section_type not in VALID_SECTION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid section_type. Must be one of: {sorted(VALID_SECTION_TYPES)}",
        )
    client = get_supabase_client()
    section = await get_section(client, scraped_file_id, section_type)
    if not section:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
    return {
        "id": str(section.get("id")),
        "scraped_file_id": str(section.get("scraped_file_id")),
        "section_type": section.get("section_type"),
        "title": section.get("title"),
        "content": section.get("content"),
        "raw_text": section.get("raw_text"),
        "page_start": section.get("page_start"),
        "page_end": section.get("page_end"),
        "extraction_method": section.get("extraction_method"),
        "confidence_score": section.get("confidence_score"),
    }
