"""
Batch extraction via Gemini Batch API.

Submits extraction jobs for many PDFs (100+) and processes results when complete.
"""

import asyncio
import hashlib
import json
import logging
from typing import Any
from uuid import UUID

from supabase import Client

from app.config import get_settings
from app.db.batch_jobs import add_extraction_to_batch, get_batch_job
from app.db.extractions import create_extraction
from app.db.gemini_batch_jobs import (
    create_gemini_batch_job as db_create_gemini_batch_job,
    get_gemini_batch_job,
    update_gemini_batch_job_status,
)
from app.db.memo_extractions import create_memo_extraction
from app.db.supabase_client import get_supabase_client
from app.models.extraction import FullExamPaper
from app.models.memo_extraction import MarkingGuideline
from app.services.gemini_batch import (
    build_extraction_request,
    create_batch_job,
    download_batch_results,
    poll_batch_job,
)
from app.services.gemini_client import get_gemini_client
from app.services.pdf_extractor import (
    EXAM_EXTRACTION_SYSTEM_INSTRUCTION,
    _remove_additional_properties,
)
from app.services.memo_extractor import MEMO_EXTRACTION_SYSTEM_INSTRUCTION

logger = logging.getLogger(__name__)

EXAM_USER_PROMPT = """Analyze this examination paper PDF and extract ALL content. Return valid JSON matching the schema (metadata, question_groups, questions)."""
MEMO_USER_PROMPT = """Extract the Marking Guideline (Memorandum) from this PDF into structured JSON. Return valid JSON only."""


async def submit_extraction_batch(
    files: list[tuple[bytes, str, str]],
    batch_job_id: str,
    source_ids: list[str] | None = None,
) -> str:
    """
    Submit a Gemini Batch API job for extraction.

    files: list of (pdf_content, filename, doc_type) where doc_type is 'memo' or 'question_paper'.
    source_ids: optional list of scraped_file_id (one per file), same length as files.
    Returns our gemini_batch_job id (UUID).
    """
    settings = get_settings()
    supabase = get_supabase_client()
    gemini_client = get_gemini_client()
    model = getattr(settings, "batch_api_model", "models/gemini-2.5-flash") or "models/gemini-2.5-flash"

    from app.models.extraction import FullExamPaper
    from app.models.memo_extraction import MarkingGuideline

    exam_schema = _remove_additional_properties(FullExamPaper.model_json_schema())
    memo_schema = _remove_additional_properties(MarkingGuideline.model_json_schema())

    keyed_requests: list[dict] = []
    request_metadata: dict[str, dict[str, Any]] = {}

    for i, (content, filename, doc_type) in enumerate(files):
        key = str(i)
        request_metadata[key] = {
            "filename": filename,
            "doc_type": doc_type,
            "index": i,
        }
        if source_ids and i < len(source_ids):
            request_metadata[key]["scraped_file_id"] = source_ids[i]
        try:
            if doc_type == "memo":
                system_instruction = MEMO_EXTRACTION_SYSTEM_INSTRUCTION
                user_prompt = MEMO_USER_PROMPT
                response_schema = memo_schema
            else:
                system_instruction = EXAM_EXTRACTION_SYSTEM_INSTRUCTION
                user_prompt = EXAM_USER_PROMPT
                response_schema = exam_schema
            req, _ = await build_extraction_request(
                client=gemini_client,
                pdf_content=content,
                filename=filename,
                doc_type=doc_type,
                user_prompt=user_prompt,
                system_instruction=system_instruction,
                response_schema=response_schema,
            )
            keyed_requests.append({"key": key, "request": req})
        except Exception as e:
            logger.warning("Failed to build extraction request for %s: %s", filename, e)

    if not keyed_requests:
        raise ValueError("No valid extraction requests could be built")

    display_name = f"extraction-{batch_job_id[:8]}"
    job_name = await create_batch_job(
        client=gemini_client,
        keyed_requests=keyed_requests,
        model=model,
        display_name=display_name,
    )
    gemini_job_id = await db_create_gemini_batch_job(
        client=supabase,
        gemini_job_name=job_name,
        job_type="extraction",
        total_requests=len(keyed_requests),
        source_job_id=batch_job_id,
        request_metadata=request_metadata,
    )
    return gemini_job_id


async def process_extraction_batch_results(
    gemini_batch_job_id: str,
) -> dict[str, Any]:
    """
    Poll the batch job (if still pending), download results, create extractions, update batch_job.

    Returns summary: succeeded, failed, extraction_ids, error_message.
    """
    from datetime import datetime, timezone
    from pydantic import ValidationError as PydanticValidationError

    supabase = get_supabase_client()
    gemini_client = get_gemini_client()
    settings = get_settings()
    poll_interval = getattr(settings, "batch_api_poll_interval", 60) or 60

    row = await get_gemini_batch_job(supabase, gemini_batch_job_id)
    if not row:
        return {"error": "gemini_batch_job not found", "succeeded": 0, "failed": 0}
    gemini_job_name = row["gemini_job_name"]
    request_metadata = row.get("request_metadata") or {}
    source_batch_job_id = row.get("source_job_id")
    keys_in_order = list(request_metadata.keys()) if request_metadata else []

    batch_job_result = await poll_batch_job(
        client=gemini_client,
        job_name=gemini_job_name,
        poll_interval=poll_interval,
    )
    state = batch_job_result.state
    if state != "JOB_STATE_SUCCEEDED":
        await update_gemini_batch_job_status(
            supabase,
            gemini_batch_job_id,
            status="failed" if state == "JOB_STATE_FAILED" else state.lower().replace("job_state_", ""),
            error_message=str(batch_job_result.error) if batch_job_result.error else state,
        )
        return {"error": state, "succeeded": 0, "failed": 0}

    items = await download_batch_results(
        client=gemini_client,
        job=batch_job_result,
        keys_in_order=keys_in_order if batch_job_result.dest and getattr(batch_job_result.dest, "inlined_responses", None) else None,
    )

    succeeded = 0
    failed = 0
    extraction_ids: list[str] = []

    for item in items:
        meta = request_metadata.get(item.key, {})
        filename = meta.get("filename", "document.pdf")
        doc_type = meta.get("doc_type", "question_paper")
        scraped_file_id = meta.get("scraped_file_id")

        if item.error or not item.response_text:
            failed += 1
            continue
        try:
            data = json.loads(item.response_text)
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON for key %s: %s", item.key, e)
            failed += 1
            continue
        file_info = {
            "file_name": filename,
            "file_size_bytes": 0,
            "file_hash": hashlib.sha256(item.response_text.encode()).hexdigest()[:16],
            "webhook_url": None,
            "error_message": None,
            "retry_count": 0,
        }
        if scraped_file_id:
            file_info["scraped_file_id"] = scraped_file_id
        try:
            if doc_type == "memo":
                memo_result = MarkingGuideline.model_validate(data)
                memo_result.processing_metadata = memo_result.processing_metadata or {}
                memo_result.processing_metadata.setdefault("method", "batch_api")
                memo_result.processing_metadata.setdefault("cost_estimate_usd", 0.0)
                extraction_id = await create_memo_extraction(
                    supabase,
                    memo_result,
                    file_info,
                    status="completed",
                )
            else:
                exam_result = FullExamPaper.model_validate(data)
                exam_result.processing_metadata = exam_result.processing_metadata or {}
                exam_result.processing_metadata.setdefault("method", "batch_api")
                exam_result.processing_metadata.setdefault("cost_estimate_usd", 0.0)
                extraction_id = await create_extraction(
                    supabase,
                    exam_result,
                    file_info,
                    status="completed",
                )
            succeeded += 1
            extraction_ids.append(extraction_id)
            if source_batch_job_id:
                await add_extraction_to_batch(
                    supabase,
                    source_batch_job_id,
                    extraction_id=extraction_id,
                    processing_method="batch_api",
                    status="completed",
                    cost_estimate_usd=0.0,
                    cost_savings_usd=0.0,
                )
        except PydanticValidationError as e:
            logger.warning("Schema validation failed for key %s: %s", item.key, e)
            failed += 1
        except Exception as e:
            logger.warning("Failed to store extraction for key %s: %s", item.key, e)
            failed += 1

    await update_gemini_batch_job_status(
        supabase,
        gemini_batch_job_id,
        status="succeeded",
        completed_requests=succeeded + failed,
        failed_requests=failed,
        completed_at=datetime.now(timezone.utc).isoformat(),
    )

    return {
        "succeeded": succeeded,
        "failed": failed,
        "extraction_ids": extraction_ids,
    }
