"""
POST /api/extract/from-storage: trigger extraction from a Firebase Storage URL.

Downloads PDF from gs:// URL, runs the same extraction pipeline as upload,
skips classification when doc_type is provided. Returns 202 and processes in background.
"""

import asyncio
import hashlib
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

import magic
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from app.db.extractions import (
    check_duplicate,
    check_duplicate_any,
    create_extraction,
    get_extraction,
    list_extractions,
    update_extraction_status,
    update_extraction,
)
from app.db.memo_extractions import (
    check_memo_duplicate,
    create_memo_extraction,
    get_memo_extraction,
    update_memo_extraction_status,
    update_memo_extraction,
)
from app.db.supabase_client import get_supabase_client
from app.db.validation_results import get_validation_result
from app.models.extraction import DocumentStructure, FullExamPaper
from app.models.memo_extraction import MarkingGuideline
from app.services.document_classifier import classify_document
from app.services.file_validator import sanitize_filename
from app.services.firebase_client import download_to_path
from app.services.gemini_client import get_gemini_client
from app.services.opendataloader_extractor import extract_pdf_structure
from app.services.pdf_extractor import extract_pdf_data_hybrid, PartialExtractionError
from app.services.memo_extractor import extract_memo_data_hybrid, PartialMemoExtractionError
from app.services.section_extractor import extract_and_store_sections
from app.services.exam_matcher import match_document_to_exam_set
from app.services.webhook_sender import send_extraction_completed_webhook

router = APIRouter(prefix="/api", tags=["extraction"])
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 200 * 1024 * 1024
ALLOWED_MIME_TYPE = "application/pdf"


class FromStorageRequest(BaseModel):
    """Request body for POST /api/extract/from-storage."""
    scraped_file_id: uuid.UUID = Field(..., description="Document UUID (scraped_files.id)")
    storage_url: str = Field(..., description="gs:// bucket/path to the PDF")
    doc_type: Optional[str] = Field(default=None, description="question_paper or memo; if set, classification is skipped")
    webhook_url: Optional[str] = Field(default=None, description="Webhook URL for completion/failure")


@router.post("/extract/from-storage", status_code=status.HTTP_202_ACCEPTED)
async def extract_from_storage(
    body: FromStorageRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Trigger extraction from a Firebase Storage URL. Returns 202 and processes in background.
    Skips classification when doc_type is provided. Webhook sent on completion/failure.
    """
    if not body.storage_url.strip().lower().startswith("gs://"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="storage_url must be a gs:// URL",
        )
    if body.doc_type is not None and body.doc_type not in ("question_paper", "memo"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="doc_type must be 'question_paper' or 'memo'",
        )
    tracking_id = str(uuid.uuid4())
    background_tasks.add_task(
        _run_extraction_from_storage,
        scraped_file_id=str(body.scraped_file_id),
        storage_url=body.storage_url.strip(),
        doc_type=body.doc_type,
        webhook_url=body.webhook_url,
        tracking_id=tracking_id,
    )
    return {
        "extraction_id": tracking_id,
        "status": "processing",
        "scraped_file_id": str(body.scraped_file_id),
    }


async def _run_extraction_from_storage(
    scraped_file_id: str,
    storage_url: str,
    doc_type: Optional[str],
    webhook_url: Optional[str],
    tracking_id: str,
) -> None:
    """Background task: download from storage, validate, classify (if needed), extract, save, webhook."""
    temp_file_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(prefix="pdf_from_storage_", delete=False, suffix=".pdf") as tmp:
            temp_file_path = tmp.name
        download_to_path(storage_url, temp_file_path)
        with open(temp_file_path, "rb") as f:
            content = f.read()
    except Exception as e:
        logger.exception("Download from storage failed: %s", e)
        if webhook_url:
            await send_extraction_completed_webhook(
                webhook_url, tracking_id, "failed", data={"error_message": str(e)}
            )
        if temp_file_path:
            try:
                Path(temp_file_path).unlink(missing_ok=True)
            except OSError:
                pass
        return

    if len(content) == 0:
        if webhook_url:
            await send_extraction_completed_webhook(
                webhook_url, tracking_id, "failed", data={"error_message": "File is empty"}
            )
        Path(temp_file_path).unlink(missing_ok=True)
        return
    if len(content) > MAX_FILE_SIZE:
        if webhook_url:
            await send_extraction_completed_webhook(
                webhook_url, tracking_id, "failed",
                data={"error_message": f"File too large (max {MAX_FILE_SIZE // (1024*1024)}MB)"},
            )
        Path(temp_file_path).unlink(missing_ok=True)
        return
    try:
        mime_type = magic.from_buffer(content, mime=True)
    except Exception:
        mime_type = None
    if mime_type != ALLOWED_MIME_TYPE:
        if webhook_url:
            await send_extraction_completed_webhook(
                webhook_url, tracking_id, "failed",
                data={"error_message": f"Invalid file type: expected {ALLOWED_MIME_TYPE}, got {mime_type}"},
            )
        Path(temp_file_path).unlink(missing_ok=True)
        return

    file_hash = hashlib.sha256(content).hexdigest()
    raw_name = Path(storage_url.rstrip("/")).name or "document.pdf"
    sanitized_filename = sanitize_filename(raw_name)

    supabase_client = get_supabase_client()
    scraped_file_uuid = UUID(scraped_file_id)

    # Match to exam set after validation (if validation result exists)
    try:
        validation_result = await get_validation_result(supabase_client, scraped_file_uuid)
        if validation_result:
            await match_document_to_exam_set(supabase_client, scraped_file_uuid, validation_result)
    except Exception as match_err:
        logger.warning("Exam set matching failed (continuing): %s", match_err)
    existing_any = await check_duplicate_any(supabase_client, file_hash)
    if existing_any:
        table_name, existing_id = existing_any
        if table_name == "extractions":
            existing_result = await get_extraction(supabase_client, existing_id)
        else:
            existing_result = await get_memo_extraction(supabase_client, existing_id)
        if existing_result and existing_result.get("status") == "completed":
            if webhook_url:
                await send_extraction_completed_webhook(
                    webhook_url, existing_id, "completed",
                    data=existing_result,
                )
            Path(temp_file_path).unlink(missing_ok=True)
            return

    classification_method: Optional[str] = "user_provided" if doc_type else None
    precomputed_doc_structure: Optional[DocumentStructure] = None

    if doc_type is None:
        precomputed_doc_structure = extract_pdf_structure(temp_file_path)
        gemini_client = get_gemini_client()
        classification = classify_document(
            filename=sanitized_filename,
            markdown_text=precomputed_doc_structure.markdown,
            gemini_client=gemini_client,
        )
        doc_type = classification.doc_type
        classification_method = classification.method
    else:
        precomputed_doc_structure = extract_pdf_structure(temp_file_path)

    if doc_type == "memo":
        existing_id = await check_memo_duplicate(supabase_client, file_hash)
    else:
        existing_id = await check_duplicate(supabase_client, file_hash)

    is_retry = False
    retry_count = 0
    if existing_id:
        existing_result = await (
            get_memo_extraction(supabase_client, existing_id)
            if doc_type == "memo"
            else get_extraction(supabase_client, existing_id)
        )
        if existing_result and existing_result.get("status") == "completed":
            if webhook_url:
                await send_extraction_completed_webhook(
                    webhook_url, existing_id, "completed",
                    data=existing_result,
                )
            Path(temp_file_path).unlink(missing_ok=True)
            return
        if existing_result and existing_result.get("status") in ("partial", "failed"):
            is_retry = True
            retry_count = existing_result.get("retry_count", 0) + 1

    file_info: dict[str, Any] = {
        "file_name": sanitized_filename,
        "file_size_bytes": len(content),
        "file_hash": file_hash,
        "webhook_url": webhook_url,
        "scraped_file_id": str(scraped_file_id),
        "retry_count": retry_count,
    }

    # Section extraction (cover, instructions, marker notes, information sheet) before questions/answers
    try:
        await extract_and_store_sections(
            scraped_file_uuid,
            temp_file_path,
            is_question_paper=(doc_type != "memo"),
            supabase_client=supabase_client,
        )
    except Exception as sec_err:
        logger.warning("Section extraction failed (continuing with question extraction): %s", sec_err)

    gemini_client = get_gemini_client()
    extraction_result: Optional[FullExamPaper | MarkingGuideline] = None
    extraction_status = "completed"
    error_message: Optional[str] = None

    try:
        if doc_type == "memo":
            extraction_result = await extract_memo_data_hybrid(
                client=gemini_client,
                file_path=temp_file_path,
                doc_structure=precomputed_doc_structure,
            )
        else:
            extraction_result = await extract_pdf_data_hybrid(
                client=gemini_client,
                file_path=temp_file_path,
                doc_structure=precomputed_doc_structure,
            )
    except (PartialExtractionError, PartialMemoExtractionError) as e:
        extraction_result = e.partial_result
        extraction_status = "partial"
        error_message = str(e.original_exception)
    except (PydanticValidationError, Exception) as e:
        extraction_status = "failed"
        error_message = str(e)
        if is_retry and existing_id:
            if doc_type == "memo":
                await update_memo_extraction_status(
                    supabase_client, existing_id, status="failed", error=error_message
                )
            else:
                await update_extraction_status(
                    supabase_client, existing_id, status="failed", error=error_message
                )
        if webhook_url:
            await send_extraction_completed_webhook(
                webhook_url, tracking_id, "failed", data={"error_message": error_message}
            )
        Path(temp_file_path).unlink(missing_ok=True)
        return

    if extraction_result and classification_method:
        extraction_result.processing_metadata["classification_method"] = classification_method
        extraction_result.processing_metadata["doc_type"] = doc_type

    try:
        if extraction_status == "failed" and extraction_result is None:
            pass
        elif existing_id and extraction_result:
            if doc_type == "memo":
                await update_memo_extraction(
                    supabase_client, existing_id, extraction_result,
                    status=extraction_status, error_message=error_message, retry_count=retry_count
                )
            else:
                await update_extraction(
                    supabase_client, existing_id, extraction_result,
                    status=extraction_status, error_message=error_message, retry_count=retry_count
                )
            extraction_id = existing_id
        elif extraction_result:
            if doc_type == "memo":
                extraction_id = await create_memo_extraction(
                    supabase_client, extraction_result, file_info, status=extraction_status
                )
            else:
                extraction_id = await create_extraction(
                    supabase_client, extraction_result, file_info, status=extraction_status
                )
            if webhook_url:
                await send_extraction_completed_webhook(
                    webhook_url, extraction_id, extraction_status,
                    data=extraction_result.model_dump() if extraction_result else None,
                )
        else:
            if webhook_url:
                await send_extraction_completed_webhook(
                    webhook_url, tracking_id, "failed", error_message=error_message
                )
    except Exception as e:
        logger.exception("Failed to save extraction: %s", e)
        if webhook_url:
            await send_extraction_completed_webhook(
                webhook_url, tracking_id, "failed", error_message=str(e)
            )
    finally:
        if temp_file_path:
            try:
                Path(temp_file_path).unlink(missing_ok=True)
            except OSError:
                pass
