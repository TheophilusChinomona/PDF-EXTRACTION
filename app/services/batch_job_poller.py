"""
Poll pending Gemini Batch API jobs and process results when complete.

Run periodically (e.g. every 60s via CLI or scheduler).
"""

import asyncio
import logging
from typing import Any

from app.db.gemini_batch_jobs import get_pending_gemini_batch_jobs
from app.db.supabase_client import get_supabase_client
from app.services.extraction_batch import process_extraction_batch_results
from app.services.gemini_client import get_gemini_client
from app.services.validation_batch import process_validation_batch_results

logger = logging.getLogger(__name__)

TERMINAL_STATES = frozenset({
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
})


async def poll_single_job(job_id: str) -> dict[str, Any]:
    """
    Poll and process a single Gemini batch job by our DB id.

    Fetches job by id, then runs the appropriate processor (which polls Gemini and processes results).
    Returns summary dict from the processor (validation or extraction).
    """
    from app.db.gemini_batch_jobs import get_gemini_batch_job

    supabase = get_supabase_client()
    row = await get_gemini_batch_job(supabase, job_id)
    if not row:
        return {"error": "job not found"}
    if row.get("status") != "pending":
        return {"error": f"job status is {row.get('status')}, not pending"}

    job_type = row.get("job_type", "validation")
    if job_type == "validation":
        return await process_validation_batch_results(job_id)
    return await process_extraction_batch_results(job_id)


async def poll_pending_batch_jobs(job_type: str | None = None) -> list[dict[str, Any]]:
    """
    Poll all pending Gemini batch jobs, process those that have completed.

    job_type: optional filter 'validation' or 'extraction'.
    Returns list of result summaries (one per processed job).
    """
    supabase = get_supabase_client()
    gemini_client = get_gemini_client()

    pending = await get_pending_gemini_batch_jobs(supabase, job_type=job_type)
    if not pending:
        return []

    results: list[dict[str, Any]] = []
    for row in pending:
        job_id = row.get("id")
        gemini_job_name = row.get("gemini_job_name")
        row_job_type = row.get("job_type", "validation")
        if not job_id or not gemini_job_name:
            continue
        try:
            batch_job = await asyncio.to_thread(gemini_client.batches.get, name=gemini_job_name)
            state = getattr(batch_job, "state", None)
            if state is not None and hasattr(state, "name"):
                state_str = state.name
            else:
                state_str = str(state) if state else "UNKNOWN"
            if state_str not in TERMINAL_STATES:
                continue
            if state_str == "JOB_STATE_SUCCEEDED":
                if row_job_type == "validation":
                    summary = await process_validation_batch_results(str(job_id))
                else:
                    summary = await process_extraction_batch_results(str(job_id))
                results.append({"job_id": str(job_id), "status": state_str, "summary": summary})
            else:
                from datetime import datetime, timezone
                from app.db.gemini_batch_jobs import update_gemini_batch_job_status
                await update_gemini_batch_job_status(
                    supabase,
                    str(job_id),
                    status="failed" if state_str == "JOB_STATE_FAILED" else state_str.lower().replace("job_state_", ""),
                    error_message=str(getattr(batch_job, "error", None)) or state_str,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                results.append({"job_id": str(job_id), "status": state_str, "summary": {}})
        except Exception as e:
            logger.exception("Error polling job %s: %s", job_id, e)
            results.append({"job_id": str(job_id), "error": str(e)})
    return results
