"""Tests for database extraction functions."""

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.db.extractions import (
    create_extraction,
    get_extraction,
    check_duplicate,
    update_extraction_status,
    list_extractions
)
from app.models.extraction import (
    ExtractionResult,
    ExtractedMetadata,
    ExtractedSection,
    ExtractedTable,
    ExtractedReference,
    BoundingBox
)


@pytest.fixture
def mock_supabase_client():
    """Create a mock Supabase client."""
    return MagicMock()


@pytest.fixture
def sample_extraction_result():
    """Create a sample extraction result for testing."""
    return ExtractionResult(
        metadata=ExtractedMetadata(
            title="Test Paper",
            authors=["John Doe", "Jane Smith"],
            journal="Test Journal",
            year=2024
        ),
        abstract="This is a test abstract.",
        sections=[
            ExtractedSection(
                heading="Introduction",
                content="Test introduction content",
                page_number=1,
                bbox=BoundingBox(x1=50.0, y1=100.0, x2=550.0, y2=150.0, page=1)
            )
        ],
        tables=[
            ExtractedTable(
                caption="Test Table",
                page_number=2,
                data=[{"col1": "val1", "col2": "val2"}],
                bbox=BoundingBox(x1=50.0, y1=200.0, x2=550.0, y2=400.0, page=2)
            )
        ],
        references=[
            ExtractedReference(
                citation_text="Doe et al. (2023)",
                authors=["John Doe"],
                year=2023,
                title="Previous Work"
            )
        ],
        confidence_score=0.95,
        bounding_boxes={
            "elem_1": BoundingBox(x1=10.0, y1=20.0, x2=100.0, y2=50.0, page=1)
        },
        processing_metadata={
            "method": "hybrid",
            "opendataloader_quality": 0.85,
            "cost_estimate_usd": 0.005
        }
    )


@pytest.fixture
def sample_file_info():
    """Create sample file info for testing."""
    return {
        'file_name': 'test_paper.pdf',
        'file_size_bytes': 1024000,
        'file_hash': 'abc123def456',
        'processing_time_seconds': 5.5,
        'webhook_url': 'https://example.com/webhook'
    }


class TestCreateExtraction:
    """Tests for create_extraction function."""

    @pytest.mark.asyncio
    async def test_create_extraction_success(
        self, mock_supabase_client, sample_extraction_result, sample_file_info
    ):
        """Test successful extraction creation."""
        mock_response = MagicMock()
        mock_response.data = [{'id': str(uuid4())}]
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = mock_response

        extraction_id = await create_extraction(
            mock_supabase_client,
            sample_extraction_result,
            sample_file_info
        )

        assert extraction_id is not None
        assert len(extraction_id) == 36  # UUID string length
        mock_supabase_client.table.assert_called_once_with('extractions')

    @pytest.mark.asyncio
    async def test_create_extraction_missing_file_info(
        self, mock_supabase_client, sample_extraction_result
    ):
        """Test error when required file_info fields are missing."""
        incomplete_file_info = {'file_name': 'test.pdf'}

        with pytest.raises(ValueError) as exc_info:
            await create_extraction(
                mock_supabase_client,
                sample_extraction_result,
                incomplete_file_info
            )

        assert "Missing required file_info fields" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_extraction_database_error(
        self, mock_supabase_client, sample_extraction_result, sample_file_info
    ):
        """Test error handling when database insertion fails."""
        mock_supabase_client.table.return_value.insert.return_value.execute.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(Exception) as exc_info:
            await create_extraction(
                mock_supabase_client,
                sample_extraction_result,
                sample_file_info
            )

        assert "Failed to insert extraction" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_extraction_no_data_returned(
        self, mock_supabase_client, sample_extraction_result, sample_file_info
    ):
        """Test error when insert returns no data."""
        mock_response = MagicMock()
        mock_response.data = []
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            await create_extraction(
                mock_supabase_client,
                sample_extraction_result,
                sample_file_info
            )

        assert "Insert returned no data" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_extraction_minimal_file_info(
        self, mock_supabase_client, sample_extraction_result
    ):
        """Test creation with minimal required file_info fields."""
        minimal_file_info = {
            'file_name': 'test.pdf',
            'file_size_bytes': 1000,
            'file_hash': 'hash123'
        }
        mock_response = MagicMock()
        mock_response.data = [{'id': str(uuid4())}]
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = mock_response

        extraction_id = await create_extraction(
            mock_supabase_client,
            sample_extraction_result,
            minimal_file_info
        )

        assert extraction_id is not None


class TestGetExtraction:
    """Tests for get_extraction function."""

    @pytest.mark.asyncio
    async def test_get_extraction_success(self, mock_supabase_client):
        """Test successful extraction retrieval."""
        test_id = str(uuid4())
        mock_response = MagicMock()
        mock_response.data = [{'id': test_id, 'file_name': 'test.pdf'}]
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        result = await get_extraction(mock_supabase_client, test_id)

        assert result is not None
        assert result['id'] == test_id
        assert result['file_name'] == 'test.pdf'

    @pytest.mark.asyncio
    async def test_get_extraction_not_found(self, mock_supabase_client):
        """Test retrieval when extraction doesn't exist."""
        test_id = str(uuid4())
        mock_response = MagicMock()
        mock_response.data = []
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        result = await get_extraction(mock_supabase_client, test_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_extraction_invalid_uuid(self, mock_supabase_client):
        """Test error with invalid UUID format."""
        with pytest.raises(ValueError) as exc_info:
            await get_extraction(mock_supabase_client, "not-a-uuid")

        assert "Invalid UUID format" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_extraction_database_error(self, mock_supabase_client):
        """Test error handling when database query fails."""
        test_id = str(uuid4())
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(Exception) as exc_info:
            await get_extraction(mock_supabase_client, test_id)

        assert "Failed to retrieve extraction" in str(exc_info.value)


class TestCheckDuplicate:
    """Tests for check_duplicate function."""

    @pytest.mark.asyncio
    async def test_check_duplicate_found(self, mock_supabase_client):
        """Test duplicate detection when file hash exists."""
        test_hash = "abc123"
        test_id = str(uuid4())
        mock_response = MagicMock()
        mock_response.data = [{'id': test_id}]
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        result = await check_duplicate(mock_supabase_client, test_hash)

        assert result == test_id

    @pytest.mark.asyncio
    async def test_check_duplicate_not_found(self, mock_supabase_client):
        """Test when no duplicate exists."""
        test_hash = "unique123"
        mock_response = MagicMock()
        mock_response.data = []
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        result = await check_duplicate(mock_supabase_client, test_hash)

        assert result is None

    @pytest.mark.asyncio
    async def test_check_duplicate_database_error(self, mock_supabase_client):
        """Test error handling when database query fails."""
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(Exception) as exc_info:
            await check_duplicate(mock_supabase_client, "hash123")

        assert "Failed to check duplicate" in str(exc_info.value)


class TestUpdateExtractionStatus:
    """Tests for update_extraction_status function."""

    @pytest.mark.asyncio
    async def test_update_status_success(self, mock_supabase_client):
        """Test successful status update."""
        test_id = str(uuid4())
        mock_response = MagicMock()
        mock_response.data = [{'id': test_id, 'status': 'completed'}]
        mock_supabase_client.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_response

        await update_extraction_status(mock_supabase_client, test_id, 'completed')

        mock_supabase_client.table.assert_called_once_with('extractions')

    @pytest.mark.asyncio
    async def test_update_status_with_error_message(self, mock_supabase_client):
        """Test status update with error message."""
        test_id = str(uuid4())
        mock_response = MagicMock()
        mock_response.data = [{'id': test_id}]
        mock_supabase_client.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_response

        await update_extraction_status(
            mock_supabase_client,
            test_id,
            'failed',
            'Processing error occurred'
        )

        # Verify update was called with both status and error_message
        update_call = mock_supabase_client.table.return_value.update.call_args
        assert update_call[0][0]['status'] == 'failed'
        assert update_call[0][0]['error_message'] == 'Processing error occurred'

    @pytest.mark.asyncio
    async def test_update_status_invalid_uuid(self, mock_supabase_client):
        """Test error with invalid UUID format."""
        with pytest.raises(ValueError) as exc_info:
            await update_extraction_status(mock_supabase_client, "not-a-uuid", 'completed')

        assert "Invalid UUID format" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_status_invalid_status(self, mock_supabase_client):
        """Test error with invalid status value."""
        test_id = str(uuid4())

        with pytest.raises(ValueError) as exc_info:
            await update_extraction_status(mock_supabase_client, test_id, 'invalid_status')

        assert "Invalid status" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_status_not_found(self, mock_supabase_client):
        """Test error when extraction ID doesn't exist."""
        test_id = str(uuid4())
        mock_response = MagicMock()
        mock_response.data = []
        mock_supabase_client.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            await update_extraction_status(mock_supabase_client, test_id, 'completed')

        assert "No extraction found" in str(exc_info.value)


class TestListExtractions:
    """Tests for list_extractions function."""

    @pytest.mark.asyncio
    async def test_list_extractions_default_params(self, mock_supabase_client):
        """Test listing extractions with default parameters."""
        mock_response = MagicMock()
        mock_response.data = [
            {'id': str(uuid4()), 'file_name': 'test1.pdf'},
            {'id': str(uuid4()), 'file_name': 'test2.pdf'}
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value = mock_response

        result = await list_extractions(mock_supabase_client)

        assert len(result) == 2
        assert result[0]['file_name'] == 'test1.pdf'

    @pytest.mark.asyncio
    async def test_list_extractions_with_status_filter(self, mock_supabase_client):
        """Test listing with status filter."""
        mock_response = MagicMock()
        mock_response.data = [{'id': str(uuid4()), 'status': 'completed'}]

        # Create a proper mock chain
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq = MagicMock()
        mock_order = MagicMock()
        mock_range = MagicMock()

        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_eq
        mock_eq.order.return_value = mock_order
        mock_order.range.return_value = mock_range
        mock_range.execute.return_value = mock_response

        mock_supabase_client.table.return_value = mock_table

        result = await list_extractions(mock_supabase_client, status='completed')

        assert len(result) == 1
        mock_select.eq.assert_called_once_with('status', 'completed')

    @pytest.mark.asyncio
    async def test_list_extractions_with_pagination(self, mock_supabase_client):
        """Test listing with custom limit and offset."""
        mock_response = MagicMock()
        mock_response.data = [{'id': str(uuid4())}]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value = mock_response

        result = await list_extractions(mock_supabase_client, limit=10, offset=20)

        # Verify range was called with correct offset and limit
        range_call = mock_supabase_client.table.return_value.select.return_value.order.return_value.range
        range_call.assert_called_once_with(20, 29)  # offset to offset+limit-1

    @pytest.mark.asyncio
    async def test_list_extractions_empty_result(self, mock_supabase_client):
        """Test listing when no extractions exist."""
        mock_response = MagicMock()
        mock_response.data = []
        mock_supabase_client.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value = mock_response

        result = await list_extractions(mock_supabase_client)

        assert result == []

    @pytest.mark.asyncio
    async def test_list_extractions_invalid_status_filter(self, mock_supabase_client):
        """Test error with invalid status filter."""
        with pytest.raises(ValueError) as exc_info:
            await list_extractions(mock_supabase_client, status='invalid_status')

        assert "Invalid status filter" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_list_extractions_database_error(self, mock_supabase_client):
        """Test error handling when database query fails."""
        mock_supabase_client.table.return_value.select.return_value.order.return_value.range.return_value.execute.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(Exception) as exc_info:
            await list_extractions(mock_supabase_client)

        assert "Failed to list extractions" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_list_extractions_none_data_response(self, mock_supabase_client):
        """Test handling when response.data is None."""
        mock_response = MagicMock()
        mock_response.data = None
        mock_supabase_client.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value = mock_response

        result = await list_extractions(mock_supabase_client)

        assert result == []
