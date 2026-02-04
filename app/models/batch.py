"""Pydantic models for batch processing jobs.

This module defines the data structures for batch PDF processing operations,
including job creation, status tracking, and routing statistics.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class RoutingStats(BaseModel):
    """Statistics about routing decisions in a batch job."""
    hybrid: int = Field(ge=0, default=0, description="Number of files processed via hybrid mode")
    vision_fallback: int = Field(ge=0, default=0, description="Number of files processed via vision fallback")
    pending: int = Field(ge=0, default=0, description="Number of files not yet processed")


class BatchJobCreate(BaseModel):
    """Request model for creating a batch job."""
    webhook_url: Optional[str] = Field(default=None, description="Optional webhook URL for completion notifications")


class BatchJobStatus(BaseModel):
    """Response model for batch job status."""
    id: UUID = Field(description="Batch job ID")
    status: str = Field(description="Job status: pending, processing, completed, failed, or partial")
    total_files: int = Field(ge=1, le=100, description="Total number of files in batch")
    completed_files: int = Field(ge=0, description="Number of successfully completed extractions")
    failed_files: int = Field(ge=0, description="Number of failed extractions")
    routing_stats: RoutingStats = Field(description="Routing method distribution")
    extraction_ids: List[UUID] = Field(description="List of extraction UUIDs")
    cost_estimate_usd: Optional[float] = Field(default=None, description="Total estimated API cost")
    cost_savings_usd: Optional[float] = Field(default=None, description="Total cost savings")
    created_at: datetime = Field(description="Timestamp when batch job created")
    updated_at: datetime = Field(description="Timestamp of last update")
    estimated_completion: Optional[datetime] = Field(default=None, description="Estimated completion time")
    webhook_url: Optional[str] = Field(default=None, description="Webhook URL if configured")
    gemini_batch_job_id: Optional[UUID] = Field(default=None, description="Gemini Batch API job ID when using batch path")


class BatchJobSummary(BaseModel):
    """Summary model for batch job list responses."""
    id: UUID = Field(description="Batch job ID")
    status: str = Field(description="Job status")
    total_files: int = Field(description="Total number of files")
    completed_files: int = Field(description="Number completed")
    failed_files: int = Field(description="Number failed")
    created_at: datetime = Field(description="Creation timestamp")
