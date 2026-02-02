"""
Batch PDF processing API endpoints.

Provides endpoints for batch file uploads and job status tracking.
"""

import asyncio
import os
import tempfile
import uuid
from typing import List, Optional

BATCH_TIMEOUT_SECONDS = 3600  # 1 hour max for entire batch

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from pydantic import ValidationError

from app.db.batch_jobs import (
    create_batch_job,
    get_batch_job,
    add_extraction_to_batch,
    list_batch_jobs,
)
from app.db.extractions import create_extraction, check_duplicate, get_extraction
from app.db.supabase_client import get_supabase_client
from app.middleware.rate_limit import get_limiter
from app.models.batch import BatchJobCreate, BatchJobStatus, RoutingStats
from app.services.file_validator import validate_pdf
from app.services.gemini_client import get_gemini_client
from app.services.pdf_extractor import extract_pdf_data_hybrid, PartialExtractionError
from app.services.webhook_sender import send_batch_completed_webhook

router = APIRouter(prefix="/api/batch", tags=["batch"])
limiter = get_limiter()


@router.post("", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("2/minute")  # type: ignore[untyped-decorator]
async def create_batch_extraction(
    request: Request,
    files: List[UploadFile] = File(..., description="PDF files to extract (max 100)"),
    webhook_url: Optional[str] = Form(None, description="Optional webhook URL for completion notification"),
) -> dict[str, object]:
    """
    Create a batch job for processing multiple PDF files.

    This endpoint:
    1. Validates that file count is within limits (1-100)
    2. Creates a batch job record
    3. Processes each file through the extraction pipeline (synchronous for MVP)
    4. Updates batch job statistics as files complete
    5. Returns batch job ID and status URL

    Args:
        files: List of PDF files to process (max 100)
        webhook_url: Optional HTTPS URL to receive completion notification

    Returns:
        202 Accepted: Batch job created and processing
        {
            "batch_job_id": "uuid",
            "status_url": "/api/batch/{id}",
            "total_files": N,
            "status": "processing"
        }

    Raises:
        HTTPException: Various error conditions
    """
    # Validate file count
    if len(files) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file is required"
        )

    if len(files) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum 100 files allowed, got {len(files)}"
        )

    # Validate webhook URL if provided
    if webhook_url and not webhook_url.startswith('https://'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook URL must use HTTPS"
        )

    # Create batch job
    supabase_client = get_supabase_client()
    batch_job_id = await create_batch_job(
        supabase_client,
        total_files=len(files),
        webhook_url=webhook_url
    )

    # Process each file with overall timeout (Gap 7.1)
    gemini_client = get_gemini_client()

    async def _process_batch_files() -> None:
        for file in files:
            temp_file_path: Optional[str] = None

            try:
                # Validate PDF file
                try:
                    content, file_hash, sanitized_filename = await validate_pdf(file)
                except HTTPException as e:
                    # Skip invalid files, mark as failed
                    await add_extraction_to_batch(
                        supabase_client,
                        batch_job_id,
                        extraction_id=str(uuid.uuid4()),  # Placeholder ID
                        processing_method='hybrid',
                        status='failed',
                        cost_estimate_usd=0.0,
                        cost_savings_usd=0.0
                    )
                    continue

                # Check for duplicate
                existing_id = await check_duplicate(supabase_client, file_hash)
                if existing_id:
                    # Use existing extraction
                    existing_result = await get_extraction(supabase_client, existing_id)
                    if existing_result and existing_result.get("status") == "completed":
                        # Add existing extraction to batch
                        proc_method = existing_result.get("processing_method", "hybrid")
                        cost_est = existing_result.get("cost_estimate_usd", 0.0)

                        # Calculate savings (80% for hybrid, 0% for vision fallback)
                        if proc_method == 'hybrid':
                            cost_savings = cost_est * 4.0  # Saved 80% = cost is 20%, so savings = cost * 4
                        else:
                            cost_savings = 0.0

                        await add_extraction_to_batch(
                            supabase_client,
                            batch_job_id,
                            extraction_id=existing_id,
                            processing_method=proc_method,
                            status='completed',
                            cost_estimate_usd=cost_est,
                            cost_savings_usd=cost_savings
                        )
                        continue

                # Save file to temp location
                temp_file_path = os.path.join(
                    tempfile.gettempdir(),
                    f"batch_{batch_job_id}_{uuid.uuid4().hex}_{sanitized_filename}"
                )

                with open(temp_file_path, "wb") as f:
                    f.write(content)

                # Extract PDF data
                extraction_result = None
                extraction_status = 'completed'
                error_message = None

                try:
                    extraction_result = await extract_pdf_data_hybrid(
                        client=gemini_client,
                        file_path=temp_file_path,
                    )
                except PartialExtractionError as e:
                    extraction_result = e.partial_result
                    extraction_status = 'partial'
                    error_message = str(e.original_exception)
                except Exception as e:
                    extraction_status = 'failed'
                    error_message = str(e)

                # Store extraction result
                if extraction_result is not None:
                    file_info = {
                        "file_name": sanitized_filename,
                        "file_size_bytes": len(content),
                        "file_hash": file_hash,
                        "webhook_url": None,  # Batch-level webhook, not per-file
                        "error_message": error_message,
                        "retry_count": 0,
                    }

                    extraction_id = await create_extraction(
                        supabase_client,
                        extraction_result,
                        file_info,
                        status=extraction_status
                    )

                    # Calculate cost and savings
                    proc_meta = extraction_result.processing_metadata
                    processing_method = proc_meta.get('method', 'hybrid')
                    cost_estimate = proc_meta.get('cost_estimate_usd', 0.0)

                    if processing_method == 'hybrid':
                        cost_savings = cost_estimate * 4.0
                    else:
                        cost_savings = 0.0

                    # Update batch job
                    await add_extraction_to_batch(
                        supabase_client,
                        batch_job_id,
                        extraction_id=extraction_id,
                        processing_method=processing_method,
                        status=extraction_status,
                        cost_estimate_usd=cost_estimate,
                        cost_savings_usd=cost_savings
                    )
                else:
                    # Complete failure - add placeholder
                    placeholder_id = str(uuid.uuid4())
                    await add_extraction_to_batch(
                        supabase_client,
                        batch_job_id,
                        extraction_id=placeholder_id,
                        processing_method='hybrid',
                        status='failed',
                        cost_estimate_usd=0.0,
                        cost_savings_usd=0.0
                    )

            except Exception as e:
                # Log error and continue with next file
                print(f"Error processing file in batch: {str(e)}")
                # Mark as failed
                placeholder_id = str(uuid.uuid4())
                await add_extraction_to_batch(
                    supabase_client,
                    batch_job_id,
                    extraction_id=placeholder_id,
                    processing_method='hybrid',
                    status='failed',
                    cost_estimate_usd=0.0,
                    cost_savings_usd=0.0
                )

            finally:
                # Cleanup temp file
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.remove(temp_file_path)
                    except Exception:
                        pass  # Ignore cleanup errors

    try:
        await asyncio.wait_for(_process_batch_files(), timeout=BATCH_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        # Mark batch as partial and return completed extractions (Gap 7.1)
        await asyncio.to_thread(
            lambda: supabase_client.table("batch_jobs")
            .update({"status": "partial"})
            .eq("id", batch_job_id)
            .execute()
        )

    # Get final batch job status
    batch_job = await get_batch_job(supabase_client, batch_job_id)

    # Send webhook if configured and batch is complete
    if webhook_url and batch_job:
        batch_status = batch_job.get('status')
        if batch_status in ['completed', 'failed', 'partial']:
            summary = {
                'total_files': batch_job.get('total_files'),
                'completed_files': batch_job.get('completed_files'),
                'failed_files': batch_job.get('failed_files'),
                'routing_stats': batch_job.get('routing_stats'),
                'cost_estimate_usd': batch_job.get('cost_estimate_usd'),
                'cost_savings_usd': batch_job.get('cost_savings_usd')
            }
            # Fire and forget - don't wait for webhook
            import asyncio
            asyncio.create_task(
                send_batch_completed_webhook(webhook_url, batch_job_id, batch_status, summary)
            )

    # Return response
    return {
        "batch_job_id": batch_job_id,
        "status_url": f"/api/batch/{batch_job_id}",
        "total_files": len(files),
        "status": "processing" if batch_job else "unknown"
    }


@router.get("/{batch_job_id}", response_model=BatchJobStatus)
async def get_batch_status(
    batch_job_id: str,
) -> BatchJobStatus:
    """
    Get the status of a batch processing job.

    Args:
        batch_job_id: UUID of the batch job

    Returns:
        BatchJobStatus: Complete batch job status with statistics

    Raises:
        HTTPException: 404 if batch job not found
    """
    supabase_client = get_supabase_client()

    try:
        batch_job = await get_batch_job(supabase_client, batch_job_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

    if not batch_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch job {batch_job_id} not found"
        )

    # Convert routing_stats dict to RoutingStats model
    routing_stats_dict = batch_job.get('routing_stats', {})
    routing_stats = RoutingStats(
        hybrid=routing_stats_dict.get('hybrid', 0),
        vision_fallback=routing_stats_dict.get('vision_fallback', 0),
        pending=routing_stats_dict.get('pending', 0)
    )

    # Build response
    return BatchJobStatus(
        id=batch_job['id'],
        status=batch_job['status'],
        total_files=batch_job['total_files'],
        completed_files=batch_job['completed_files'],
        failed_files=batch_job['failed_files'],
        routing_stats=routing_stats,
        extraction_ids=batch_job['extraction_ids'],
        cost_estimate_usd=batch_job.get('cost_estimate_usd'),
        cost_savings_usd=batch_job.get('cost_savings_usd'),
        created_at=batch_job['created_at'],
        updated_at=batch_job['updated_at'],
        estimated_completion=batch_job.get('estimated_completion'),
        webhook_url=batch_job.get('webhook_url')
    )
