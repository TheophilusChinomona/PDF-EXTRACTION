"""
Batch validation via Gemini Batch API.

Submits validation jobs for many scraped files (100+) and processes results when complete.
"""

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

from supabase import Client

from app.config import get_settings
from app.db.gemini_batch_jobs import (
    create_gemini_batch_job as db_create_gemini_batch_job,
    get_gemini_batch_job,
    update_gemini_batch_job_status,
)
from app.db.supabase_client import get_supabase_client
from app.db.validation_jobs import get_validation_job, update_validation_job
from app.db.validation_results import update_validation_result
from app.models.validation_schema import VALIDATION_SCHEMA, validate_result as validate_result_schema
from app.services.gemini_batch import (
    build_validation_request,
    create_batch_job,
    download_batch_results,
    poll_batch_job,
)
from app.services.gemini_client import get_gemini_client
from app.services.firebase_client import download_as_bytes

logger = logging.getLogger(__name__)

VALIDATION_SYSTEM_INSTRUCTION = """You are an expert at extracting metadata from South African exam document cover pages.
From the PDF (cover page and any visible metadata), extract: subject, grade, year, paper_number, session, syllabus.
Set confidence (0-1) based on how clearly the metadata is visible.
Return valid JSON only."""

VALIDATION_USER_PROMPT = """Extract document metadata (subject, grade, year, paper_number, session, syllabus, confidence) from this exam document. Return JSON only."""


async def _get_scraped_files_batch(
    client: Client,
    scraped_file_ids: list[str],
) -> list[dict[str, Any]]:
    """Fetch scraped_files rows by ids. Returns list of dicts with id, storage_bucket, storage_path, filename."""
    if not scraped_file_ids:
        return []
    response = await asyncio.to_thread(
        lambda: client.table("scraped_files")
        .select("id, storage_bucket, storage_path, filename")
        .in_("id", scraped_file_ids)
        .execute()
    )
    if not response.data:
        return []
    return list(response.data) if isinstance(response.data, list) else [response.data]


def _build_storage_url(row: dict[str, Any]) -> str:
    """Build gs:// URL from scraped_files row."""
    bucket = (row.get("storage_bucket") or "").strip() or "default"
    path = (row.get("storage_path") or "").strip().lstrip("/")
    return f"gs://{bucket}/{path}"


async def submit_validation_batch(
    scraped_file_ids: list[str],
    validation_job_id: str,
) -> str:
    """
    Submit a Gemini Batch API job for validation.

    1. Fetch scraped_files for each id (storage URL, filename).
    2. Download PDFs and upload to File API, build validation requests.
    3. Submit batch job, store in gemini_batch_jobs.
    4. Return our gemini_batch_job id (UUID).
    """
    settings = get_settings()
    supabase = get_supabase_client()
    gemini_client = get_gemini_client()
    model = getattr(settings, "batch_api_model", "models/gemini-2.5-flash") or "models/gemini-2.5-flash"

    rows = await _get_scraped_files_batch(supabase, scraped_file_ids)
    if len(rows) != len(scraped_file_ids):
        found_ids = {str(r["id"]) for r in rows}
        missing = [sid for sid in scraped_file_ids if sid not in found_ids]
        logger.warning("Some scraped_files not found or missing storage: %s", missing[:5])

    keyed_requests: list[dict] = []
    key_order: list[str] = []
    request_metadata: dict[str, dict[str, Any]] = {}

    for row in rows:
        sid = str(row["id"])
        key_order.append(sid)
        request_metadata[sid] = {"scraped_file_id": sid, "filename": row.get("filename") or "document.pdf"}
        try:
            storage_url = _build_storage_url(row)
            pdf_bytes = await asyncio.to_thread(download_as_bytes, storage_url)
        except Exception as e:
            logger.warning("Failed to download %s: %s", sid, e)
            continue
        filename = (row.get("filename") or "document.pdf").strip() or "document.pdf"
        try:
            req, _ = await build_validation_request(
                client=gemini_client,
                pdf_content=pdf_bytes,
                filename=filename,
                user_prompt=VALIDATION_USER_PROMPT,
                system_instruction=VALIDATION_SYSTEM_INSTRUCTION,
                response_schema=VALIDATION_SCHEMA,
            )
            keyed_requests.append({"key": sid, "request": req})
        except Exception as e:
            logger.warning("Failed to build validation request for %s: %s", sid, e)

    if not keyed_requests:
        raise ValueError("No valid validation requests could be built")

    display_name = f"validation-{validation_job_id[:8]}"
    job_name = await create_batch_job(
        client=gemini_client,
        keyed_requests=keyed_requests,
        model=model,
        display_name=display_name,
    )
    gemini_job_id = await db_create_gemini_batch_job(
        client=supabase,
        gemini_job_name=job_name,
        job_type="validation",
        total_requests=len(keyed_requests),
        source_job_id=validation_job_id,
        request_metadata=request_metadata,
    )
    return gemini_job_id


async def process_validation_batch_results(
    gemini_batch_job_id: str,
) -> dict[str, Any]:
    """
    Poll the batch job (if still pending), download results, update validation_results and validation_job.

    Call this when the batch job is in terminal state (e.g. from poller).
    Returns summary: succeeded, failed, updated_count, error_message.
    """
    supabase = get_supabase_client()
    gemini_client = get_gemini_client()
    settings = get_settings()
    poll_interval = getattr(settings, "batch_api_poll_interval", 60) or 60

    row = await get_gemini_batch_job(supabase, gemini_batch_job_id)
    if not row:
        return {"error": "gemini_batch_job not found", "succeeded": 0, "failed": 0, "updated_count": 0}
    gemini_job_name = row["gemini_job_name"]
    request_metadata = row.get("request_metadata") or {}
    source_job_id = row.get("source_job_id")
    keys_in_order = list(request_metadata.keys()) if request_metadata else []

    batch_job_result = await poll_batch_job(
        client=gemini_client,
        job_name=gemini_job_name,
        poll_interval=poll_interval,
    )
    state = batch_job_result.state
    if state == "JOB_STATE_SUCCEEDED":
        items = await download_batch_results(
            client=gemini_client,
            job=batch_job_result,
            keys_in_order=keys_in_order if batch_job_result.dest and getattr(batch_job_result.dest, "inlined_responses", None) else None,
        )
    else:
        await update_gemini_batch_job_status(
            supabase,
            gemini_batch_job_id,
            status="failed" if state == "JOB_STATE_FAILED" else state.lower().replace("job_state_", ""),
            error_message=str(batch_job_result.error) if batch_job_result.error else state,
        )
        return {
            "error": state,
            "succeeded": 0,
            "failed": 0,
            "updated_count": 0,
        }

    succeeded = 0
    failed = 0
    updated_count = 0
    failed_ids: list[str] = []

    for item in items:
        if item.error:
            failed += 1
            failed_ids.append(item.key)
            continue
        if not item.response_text:
            failed += 1
            failed_ids.append(item.key)
            continue
        try:
            data = json.loads(item.response_text)
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON for key %s: %s", item.key, e)
            failed += 1
            failed_ids.append(item.key)
            continue
        normalized = validate_result_schema(data)
        if not normalized:
            failed += 1
            failed_ids.append(item.key)
            continue
        try:
            await update_validation_result(
                supabase,
                UUID(item.key),
                **normalized,
            )
            succeeded += 1
            updated_count += 1
        except Exception as e:
            logger.warning("Failed to update validation_result %s: %s", item.key, e)
            failed += 1
            failed_ids.append(item.key)

    from datetime import datetime, timezone
    await update_gemini_batch_job_status(
        supabase,
        gemini_batch_job_id,
        status="succeeded",
        completed_requests=succeeded + failed,
        failed_requests=failed,
        completed_at=datetime.now(timezone.utc).isoformat(),
    )

    if source_job_id:
        try:
            job_row = await get_validation_job(supabase, UUID(source_job_id))
            if job_row:
                await update_validation_job(
                    supabase,
                    UUID(source_job_id),
                    processed_files=(job_row.get("processed_files") or 0) + succeeded + failed,
                    accepted_files=(job_row.get("accepted_files") or 0) + succeeded,
                    failed_files=(job_row.get("failed_files") or 0) + failed,
                )
        except Exception as e:
            logger.warning("Failed to update validation_job %s: %s", source_job_id, e)

    return {
        "succeeded": succeeded,
        "failed": failed,
        "updated_count": updated_count,
        "failed_ids": failed_ids[:100],
    }
