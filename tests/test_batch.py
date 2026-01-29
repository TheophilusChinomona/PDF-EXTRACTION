"""Tests for batch processing operations."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

from app.db.batch_jobs import (
    create_batch_job,
    get_batch_job,
    add_extraction_to_batch,
    list_batch_jobs,
)


@pytest.mark.asyncio
async def test_create_batch_job():
    """Test batch job creation."""
    mock_client = MagicMock()
    mock_client.table.return_value.insert.return_value.execute.return_value.data = [
        {
            'id': str(uuid4()),
            'total_files': 5,
            'status': 'pending',
            'completed_files': 0,
            'failed_files': 0
        }
    ]

    batch_job_id = await create_batch_job(mock_client, total_files=5)

    assert batch_job_id is not None
    mock_client.table.assert_called_with('batch_jobs')


@pytest.mark.asyncio
async def test_create_batch_job_invalid_count():
    """Test batch job creation with invalid file count."""
    mock_client = MagicMock()

    # Test too few files
    with pytest.raises(ValueError, match="must be between 1 and 100"):
        await create_batch_job(mock_client, total_files=0)

    # Test too many files
    with pytest.raises(ValueError, match="must be between 1 and 100"):
        await create_batch_job(mock_client, total_files=101)


@pytest.mark.asyncio
async def test_get_batch_job():
    """Test batch job retrieval."""
    batch_id = str(uuid4())
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {
            'id': batch_id,
            'total_files': 5,
            'status': 'processing',
            'completed_files': 2,
            'failed_files': 1
        }
    ]

    batch_job = await get_batch_job(mock_client, batch_id)

    assert batch_job is not None
    assert batch_job['id'] == batch_id
    assert batch_job['completed_files'] == 2


@pytest.mark.asyncio
async def test_get_batch_job_not_found():
    """Test batch job retrieval when not found."""
    batch_id = str(uuid4())
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

    batch_job = await get_batch_job(mock_client, batch_id)

    assert batch_job is None


@pytest.mark.asyncio
async def test_get_batch_job_invalid_uuid():
    """Test batch job retrieval with invalid UUID."""
    mock_client = MagicMock()

    with pytest.raises(ValueError, match="Invalid UUID format"):
        await get_batch_job(mock_client, "not-a-uuid")


@pytest.mark.asyncio
async def test_add_extraction_to_batch():
    """Test adding extraction to batch job."""
    batch_id = str(uuid4())
    extraction_id = str(uuid4())

    mock_client = MagicMock()

    # Mock get_batch_job response
    initial_batch = {
        'id': batch_id,
        'total_files': 3,
        'status': 'processing',
        'completed_files': 1,
        'failed_files': 0,
        'routing_stats': {'hybrid': 1, 'vision_fallback': 0, 'pending': 2},
        'extraction_ids': [str(uuid4())],
        'cost_estimate_usd': 0.01,
        'cost_savings_usd': 0.04
    }

    # Mock the select query for get_batch_job
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        initial_batch
    ]

    # Mock the update query
    mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
        {'id': batch_id}
    ]

    await add_extraction_to_batch(
        mock_client,
        batch_id,
        extraction_id,
        processing_method='hybrid',
        status='completed',
        cost_estimate_usd=0.01,
        cost_savings_usd=0.04
    )

    # Verify update was called
    assert mock_client.table.return_value.update.called


@pytest.mark.asyncio
async def test_add_extraction_to_batch_invalid_method():
    """Test adding extraction with invalid processing method."""
    batch_id = str(uuid4())
    extraction_id = str(uuid4())
    mock_client = MagicMock()

    with pytest.raises(ValueError, match="Invalid processing_method"):
        await add_extraction_to_batch(
            mock_client,
            batch_id,
            extraction_id,
            processing_method='invalid_method',
            status='completed'
        )


@pytest.mark.asyncio
async def test_add_extraction_to_batch_invalid_status():
    """Test adding extraction with invalid status."""
    batch_id = str(uuid4())
    extraction_id = str(uuid4())
    mock_client = MagicMock()

    with pytest.raises(ValueError, match="Invalid status"):
        await add_extraction_to_batch(
            mock_client,
            batch_id,
            extraction_id,
            processing_method='hybrid',
            status='invalid_status'
        )


@pytest.mark.asyncio
async def test_list_batch_jobs():
    """Test listing batch jobs."""
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value.data = [
        {'id': str(uuid4()), 'status': 'completed'},
        {'id': str(uuid4()), 'status': 'processing'}
    ]

    batch_jobs = await list_batch_jobs(mock_client, limit=10, offset=0)

    assert len(batch_jobs) == 2
    mock_client.table.assert_called_with('batch_jobs')


@pytest.mark.asyncio
async def test_list_batch_jobs_with_status_filter():
    """Test listing batch jobs with status filter."""
    mock_client = MagicMock()
    query_mock = mock_client.table.return_value.select.return_value
    query_mock.eq.return_value.order.return_value.range.return_value.execute.return_value.data = [
        {'id': str(uuid4()), 'status': 'completed'}
    ]

    batch_jobs = await list_batch_jobs(mock_client, limit=10, offset=0, status='completed')

    assert len(batch_jobs) == 1


@pytest.mark.asyncio
async def test_list_batch_jobs_invalid_status():
    """Test listing batch jobs with invalid status filter."""
    mock_client = MagicMock()

    with pytest.raises(ValueError, match="Invalid status filter"):
        await list_batch_jobs(mock_client, status='invalid_status')
