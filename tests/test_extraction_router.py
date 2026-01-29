"""Tests for extraction API endpoints."""

import json
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
from app.middleware.rate_limit import get_limiter
from app.models.extraction import (
    BoundingBox,
    ExtractedMetadata,
    ExtractionResult,
)


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> None:
    """Reset the rate limiter before each test to avoid rate limit interference."""
    limiter = get_limiter()
    limiter.reset()


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def sample_pdf_content() -> bytes:
    """Create sample PDF content for testing."""
    # Minimal valid PDF structure
    return b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\nxref\n0 2\ntrailer\n<<\n/Size 2\n/Root 1 0 R\n>>\nstartxref\n50\n%%EOF"


@pytest.fixture
def sample_extraction_result() -> ExtractionResult:
    """Create a sample extraction result."""
    return ExtractionResult(
        metadata=ExtractedMetadata(
            title="Test Paper",
            authors=["Author One"],
            journal="Test Journal",
            year=2024,
        ),
        abstract="Test abstract",
        sections=[],
        tables=[],
        references=[],
        confidence_score=0.95,
        bounding_boxes={
            "title_1": BoundingBox(x1=100, y1=200, x2=300, y2=220, page=1)
        },
        processing_metadata={
            "method": "hybrid",
            "opendataloader_quality": 0.85,
            "cost_savings_percent": 80,
        },
    )


class TestExtractEndpoint:
    """Tests for POST /api/extract endpoint."""

    @patch("app.routers.extraction.validate_pdf")
    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.check_duplicate")
    @patch("app.routers.extraction.get_gemini_client")
    @patch("app.routers.extraction.extract_pdf_data_hybrid")
    @patch("app.routers.extraction.create_extraction")
    @patch("app.routers.extraction.os.path.exists")
    @patch("app.routers.extraction.os.remove")
    def test_extract_pdf_success(
        self,
        mock_remove: MagicMock,
        mock_exists: MagicMock,
        mock_create_extraction: AsyncMock,
        mock_extract_hybrid: AsyncMock,
        mock_gemini_client: MagicMock,
        mock_check_duplicate: AsyncMock,
        mock_supabase_client: MagicMock,
        mock_validate: AsyncMock,
        client: TestClient,
        sample_pdf_content: bytes,
        sample_extraction_result: ExtractionResult,
    ) -> None:
        """Test successful PDF extraction."""
        # Setup mocks
        mock_validate.return_value = (
            sample_pdf_content,
            "abc123hash",
            "test_file.pdf",
        )
        mock_supabase_client.return_value = MagicMock()
        mock_check_duplicate.return_value = None  # No duplicate
        mock_gemini_client.return_value = MagicMock()
        mock_extract_hybrid.return_value = sample_extraction_result
        mock_create_extraction.return_value = "extraction-uuid-123"
        mock_exists.return_value = True

        # Make request (explicit doc_type skips auto-classification)
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        data = {"doc_type": "question_paper"}
        response = client.post("/api/extract", files=files, data=data)

        # Assertions
        assert response.status_code == status.HTTP_201_CREATED
        assert response.headers["X-Extraction-ID"] == "extraction-uuid-123"

        # Verify result structure
        result = response.json()
        assert result["metadata"]["title"] == "Test Paper"
        assert result["confidence_score"] == 0.95
        assert result["processing_metadata"]["method"] == "hybrid"

        # Verify function calls
        mock_validate.assert_called_once()
        mock_check_duplicate.assert_called_once()
        mock_extract_hybrid.assert_called_once()
        mock_create_extraction.assert_called_once()
        mock_remove.assert_called_once()  # File cleanup

    @patch("app.routers.extraction.validate_pdf")
    def test_extract_pdf_validation_error(
        self,
        mock_validate: AsyncMock,
        client: TestClient,
    ) -> None:
        """Test extraction with invalid PDF (validation error)."""
        from fastapi import HTTPException

        # Setup mock to raise HTTPException
        mock_validate.side_effect = HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds maximum of 200MB",
        )

        # Make request
        files = {"file": ("large.pdf", BytesIO(b"content"), "application/pdf")}
        response = client.post("/api/extract", files=files)

        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "File size exceeds maximum" in response.json()["detail"]

    @patch("app.routers.extraction.validate_pdf")
    def test_extract_pdf_file_too_large(
        self,
        mock_validate: AsyncMock,
        client: TestClient,
    ) -> None:
        """Test extraction with file too large (413)."""
        from fastapi import HTTPException

        mock_validate.side_effect = HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds maximum",
        )

        files = {"file": ("huge.pdf", BytesIO(b"content"), "application/pdf")}
        response = client.post("/api/extract", files=files)

        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE

    @patch("app.routers.extraction.validate_pdf")
    def test_extract_pdf_corrupted_file(
        self,
        mock_validate: AsyncMock,
        client: TestClient,
    ) -> None:
        """Test extraction with corrupted PDF file."""
        # Setup mock to raise generic exception (not HTTPException)
        mock_validate.side_effect = Exception("Invalid PDF structure")

        files = {"file": ("corrupt.pdf", BytesIO(b"invalid"), "application/pdf")}
        response = client.post("/api/extract", files=files)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "Corrupted or invalid PDF" in response.json()["detail"]

    @patch("app.routers.extraction.validate_pdf")
    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.check_duplicate")
    @patch("app.routers.extraction.get_extraction")
    def test_extract_pdf_duplicate_found(
        self,
        mock_get_extraction: AsyncMock,
        mock_check_duplicate: AsyncMock,
        mock_supabase_client: MagicMock,
        mock_validate: AsyncMock,
        client: TestClient,
        sample_pdf_content: bytes,
    ) -> None:
        """Test extraction when duplicate PDF is found."""
        # Setup mocks
        mock_validate.return_value = (
            sample_pdf_content,
            "duplicate-hash",
            "test.pdf",
        )
        mock_supabase_client.return_value = MagicMock()
        mock_check_duplicate.return_value = "existing-uuid-456"

        # Mock existing extraction result
        existing_result = {
            "id": "existing-uuid-456",
            "file_name": "original.pdf",
            "status": "completed",
        }
        mock_get_extraction.return_value = existing_result

        # Make request (explicit doc_type skips auto-classification)
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        data = {"doc_type": "question_paper"}
        response = client.post("/api/extract", files=files, data=data)

        # Assertions - should return 200 (not 201) with existing result
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["X-Extraction-ID"] == "existing-uuid-456"

        # Verify we didn't run extraction again
        mock_check_duplicate.assert_called_once()
        mock_get_extraction.assert_called_once_with(
            mock_supabase_client.return_value, "existing-uuid-456"
        )

    @patch("app.routers.extraction.validate_pdf")
    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.check_duplicate")
    @patch("app.routers.extraction.get_gemini_client")
    @patch("app.routers.extraction.extract_pdf_data_hybrid")
    def test_extract_pdf_processing_error(
        self,
        mock_extract_hybrid: AsyncMock,
        mock_gemini_client: MagicMock,
        mock_check_duplicate: AsyncMock,
        mock_supabase_client: MagicMock,
        mock_validate: AsyncMock,
        client: TestClient,
        sample_pdf_content: bytes,
    ) -> None:
        """Test extraction with processing error."""
        # Setup mocks
        mock_validate.return_value = (
            sample_pdf_content,
            "hash123",
            "test.pdf",
        )
        mock_supabase_client.return_value = MagicMock()
        mock_check_duplicate.return_value = None
        mock_gemini_client.return_value = MagicMock()

        # Mock extraction failure
        mock_extract_hybrid.side_effect = Exception("Gemini API timeout")

        # Make request (explicit doc_type skips auto-classification)
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        data = {"doc_type": "question_paper"}
        response = client.post("/api/extract", files=files, data=data)

        # Assertions
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Processing error" in response.json()["detail"]

    @patch("app.routers.extraction.validate_pdf")
    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.check_duplicate")
    @patch("app.routers.extraction.get_gemini_client")
    @patch("app.routers.extraction.extract_pdf_data_hybrid")
    def test_extract_pdf_validation_error_from_extractor(
        self,
        mock_extract_hybrid: AsyncMock,
        mock_gemini_client: MagicMock,
        mock_check_duplicate: AsyncMock,
        mock_supabase_client: MagicMock,
        mock_validate: AsyncMock,
        client: TestClient,
        sample_pdf_content: bytes,
    ) -> None:
        """Test extraction when Pydantic validation fails."""
        from pydantic import ValidationError

        # Setup mocks
        mock_validate.return_value = (
            sample_pdf_content,
            "hash123",
            "test.pdf",
        )
        mock_supabase_client.return_value = MagicMock()
        mock_check_duplicate.return_value = None
        mock_gemini_client.return_value = MagicMock()

        # Mock validation error (malformed extraction result)
        mock_extract_hybrid.side_effect = ValidationError.from_exception_data(
            "ExtractionResult",
            [{"type": "missing", "loc": ("confidence_score",), "msg": "Field required"}],
        )

        # Make request (explicit doc_type skips auto-classification)
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        data = {"doc_type": "question_paper"}
        response = client.post("/api/extract", files=files, data=data)

        # Assertions
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "PDF extraction failed validation" in response.json()["detail"]

    @patch("app.routers.extraction.validate_pdf")
    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.check_duplicate")
    @patch("app.routers.extraction.get_gemini_client")
    @patch("app.routers.extraction.extract_pdf_data_hybrid")
    @patch("app.routers.extraction.create_extraction")
    def test_extract_pdf_database_error(
        self,
        mock_create_extraction: AsyncMock,
        mock_extract_hybrid: AsyncMock,
        mock_gemini_client: MagicMock,
        mock_check_duplicate: AsyncMock,
        mock_supabase_client: MagicMock,
        mock_validate: AsyncMock,
        client: TestClient,
        sample_pdf_content: bytes,
        sample_extraction_result: ExtractionResult,
    ) -> None:
        """Test extraction when database insert fails."""
        # Setup mocks
        mock_validate.return_value = (
            sample_pdf_content,
            "hash123",
            "test.pdf",
        )
        mock_supabase_client.return_value = MagicMock()
        mock_check_duplicate.return_value = None
        mock_gemini_client.return_value = MagicMock()
        mock_extract_hybrid.return_value = sample_extraction_result

        # Mock database error
        mock_create_extraction.side_effect = Exception("Database connection timeout")

        # Make request (explicit doc_type skips auto-classification)
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        data = {"doc_type": "question_paper"}
        response = client.post("/api/extract", files=files, data=data)

        # Assertions
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Database error" in response.json()["detail"]

    @patch("app.routers.extraction.validate_pdf")
    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.check_duplicate")
    @patch("app.routers.extraction.get_gemini_client")
    @patch("app.routers.extraction.extract_pdf_data_hybrid")
    @patch("app.routers.extraction.create_extraction")
    @patch("app.routers.extraction.os.path.exists")
    @patch("app.routers.extraction.os.remove")
    def test_extract_pdf_with_webhook_url(
        self,
        mock_remove: MagicMock,
        mock_exists: MagicMock,
        mock_create_extraction: AsyncMock,
        mock_extract_hybrid: AsyncMock,
        mock_gemini_client: MagicMock,
        mock_check_duplicate: AsyncMock,
        mock_supabase_client: MagicMock,
        mock_validate: AsyncMock,
        client: TestClient,
        sample_pdf_content: bytes,
        sample_extraction_result: ExtractionResult,
    ) -> None:
        """Test extraction with optional webhook URL."""
        # Setup mocks
        mock_validate.return_value = (
            sample_pdf_content,
            "hash123",
            "test.pdf",
        )
        mock_supabase_client.return_value = MagicMock()
        mock_check_duplicate.return_value = None
        mock_gemini_client.return_value = MagicMock()
        mock_extract_hybrid.return_value = sample_extraction_result
        mock_create_extraction.return_value = "uuid-with-webhook"
        mock_exists.return_value = True

        # Make request with webhook_url (explicit doc_type skips auto-classification)
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        data = {"webhook_url": "https://example.com/webhook", "doc_type": "question_paper"}
        response = client.post("/api/extract", files=files, data=data)

        # Assertions
        assert response.status_code == status.HTTP_201_CREATED
        assert response.headers["X-Extraction-ID"] == "uuid-with-webhook"

        # Verify webhook_url was passed to create_extraction
        call_args = mock_create_extraction.call_args
        assert call_args is not None
        file_info = call_args[0][2]  # Third argument
        assert file_info["webhook_url"] == "https://example.com/webhook"

    @patch("app.routers.extraction.validate_pdf")
    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.check_duplicate")
    @patch("app.routers.extraction.get_gemini_client")
    @patch("app.routers.extraction.extract_pdf_data_hybrid")
    @patch("app.routers.extraction.create_extraction")
    @patch("app.routers.extraction.os.path.exists")
    @patch("app.routers.extraction.os.remove")
    def test_extract_pdf_cleanup_on_success(
        self,
        mock_remove: MagicMock,
        mock_exists: MagicMock,
        mock_create_extraction: AsyncMock,
        mock_extract_hybrid: AsyncMock,
        mock_gemini_client: MagicMock,
        mock_check_duplicate: AsyncMock,
        mock_supabase_client: MagicMock,
        mock_validate: AsyncMock,
        client: TestClient,
        sample_pdf_content: bytes,
        sample_extraction_result: ExtractionResult,
    ) -> None:
        """Test that temporary file is cleaned up on success."""
        # Setup mocks
        mock_validate.return_value = (
            sample_pdf_content,
            "hash123",
            "test.pdf",
        )
        mock_supabase_client.return_value = MagicMock()
        mock_check_duplicate.return_value = None
        mock_gemini_client.return_value = MagicMock()
        mock_extract_hybrid.return_value = sample_extraction_result
        mock_create_extraction.return_value = "uuid-123"
        mock_exists.return_value = True

        # Make request (explicit doc_type skips auto-classification)
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        data = {"doc_type": "question_paper"}
        response = client.post("/api/extract", files=files, data=data)

        # Assertions
        assert response.status_code == status.HTTP_201_CREATED

        # Verify cleanup was called
        mock_exists.assert_called_once()
        mock_remove.assert_called_once()

    @patch("app.routers.extraction.validate_pdf")
    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.check_duplicate")
    @patch("app.routers.extraction.get_gemini_client")
    @patch("app.routers.extraction.extract_pdf_data_hybrid")
    @patch("app.routers.extraction.os.path.exists")
    @patch("app.routers.extraction.os.remove")
    def test_extract_pdf_cleanup_on_error(
        self,
        mock_remove: MagicMock,
        mock_exists: MagicMock,
        mock_extract_hybrid: AsyncMock,
        mock_gemini_client: MagicMock,
        mock_check_duplicate: AsyncMock,
        mock_supabase_client: MagicMock,
        mock_validate: AsyncMock,
        client: TestClient,
        sample_pdf_content: bytes,
    ) -> None:
        """Test that temporary file is cleaned up even on error."""
        # Setup mocks
        mock_validate.return_value = (
            sample_pdf_content,
            "hash123",
            "test.pdf",
        )
        mock_supabase_client.return_value = MagicMock()
        mock_check_duplicate.return_value = None
        mock_gemini_client.return_value = MagicMock()

        # Mock extraction error
        mock_extract_hybrid.side_effect = Exception("API failure")
        mock_exists.return_value = True

        # Make request (explicit doc_type skips auto-classification)
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        data = {"doc_type": "question_paper"}
        response = client.post("/api/extract", files=files, data=data)

        # Assertions
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        # Verify cleanup was still called
        mock_exists.assert_called_once()
        mock_remove.assert_called_once()

    @patch("app.routers.extraction.validate_pdf")
    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.check_duplicate")
    @patch("app.routers.extraction.get_gemini_client")
    @patch("app.routers.extraction.extract_pdf_data_hybrid")
    @patch("app.routers.extraction.create_extraction")
    @patch("app.routers.extraction.os.path.exists")
    @patch("app.routers.extraction.os.remove")
    def test_extract_pdf_silent_cleanup_failure(
        self,
        mock_remove: MagicMock,
        mock_exists: MagicMock,
        mock_create_extraction: AsyncMock,
        mock_extract_hybrid: AsyncMock,
        mock_gemini_client: MagicMock,
        mock_check_duplicate: AsyncMock,
        mock_supabase_client: MagicMock,
        mock_validate: AsyncMock,
        client: TestClient,
        sample_pdf_content: bytes,
        sample_extraction_result: ExtractionResult,
    ) -> None:
        """Test that cleanup failures don't affect response."""
        # Setup mocks
        mock_validate.return_value = (
            sample_pdf_content,
            "hash123",
            "test.pdf",
        )
        mock_supabase_client.return_value = MagicMock()
        mock_check_duplicate.return_value = None
        mock_gemini_client.return_value = MagicMock()
        mock_extract_hybrid.return_value = sample_extraction_result
        mock_create_extraction.return_value = "uuid-123"
        mock_exists.return_value = True

        # Mock cleanup error
        mock_remove.side_effect = PermissionError("File in use")

        # Make request (explicit doc_type skips auto-classification)
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        data = {"doc_type": "question_paper"}
        response = client.post("/api/extract", files=files, data=data)

        # Assertions - should still succeed
        assert response.status_code == status.HTTP_201_CREATED
        assert response.headers["X-Extraction-ID"] == "uuid-123"

        # Verify cleanup was attempted
        mock_remove.assert_called_once()


class TestGetExtractionByIdEndpoint:
    """Tests for GET /api/extractions/{extraction_id} endpoint."""

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.get_extraction")
    def test_get_extraction_success(
        self,
        mock_get_extraction: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test successful extraction retrieval by ID."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        extraction_data = {
            "id": "12345678-1234-5678-1234-567812345678",
            "file_name": "test.pdf",
            "status": "completed",
            "metadata": {"title": "Test Paper"},
            "confidence_score": 0.95,
            "bounding_boxes": {
                "title_1": {"x1": 100, "y1": 200, "x2": 300, "y2": 220, "page": 1}
            },
            "processing_metadata": {"method": "hybrid"},
        }
        mock_get_extraction.return_value = extraction_data

        # Make request
        response = client.get("/api/extractions/12345678-1234-5678-1234-567812345678")

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["id"] == "12345678-1234-5678-1234-567812345678"
        assert result["status"] == "completed"
        assert "bounding_boxes" in result
        assert "processing_metadata" in result

        # Verify function call
        mock_get_extraction.assert_called_once_with(
            mock_supabase_client.return_value,
            "12345678-1234-5678-1234-567812345678",
        )

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.get_extraction")
    def test_get_extraction_not_found(
        self,
        mock_get_extraction: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test extraction retrieval when ID not found."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        mock_get_extraction.return_value = None

        # Make request
        response = client.get("/api/extractions/12345678-1234-5678-1234-567812345678")

        # Assertions
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"]

    def test_get_extraction_invalid_uuid(
        self,
        client: TestClient,
    ) -> None:
        """Test extraction retrieval with invalid UUID format."""
        # Make request with invalid UUID
        response = client.get("/api/extractions/not-a-valid-uuid")

        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid UUID format" in response.json()["detail"]

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.get_extraction")
    def test_get_extraction_database_error(
        self,
        mock_get_extraction: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test extraction retrieval when database error occurs."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        mock_get_extraction.side_effect = Exception("Database connection failed")

        # Make request
        response = client.get("/api/extractions/12345678-1234-5678-1234-567812345678")

        # Assertions
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Database error" in response.json()["detail"]


class TestListExtractionsEndpoint:
    """Tests for GET /api/extractions endpoint."""

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.list_extractions")
    def test_list_extractions_success(
        self,
        mock_list_extractions: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test successful listing of extractions."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        extractions_data = [
            {
                "id": "uuid-1",
                "file_name": "doc1.pdf",
                "status": "completed",
                "created_at": "2024-01-01T00:00:00Z",
            },
            {
                "id": "uuid-2",
                "file_name": "doc2.pdf",
                "status": "completed",
                "created_at": "2024-01-02T00:00:00Z",
            },
        ]
        mock_list_extractions.return_value = extractions_data

        # Make request (default pagination)
        response = client.get("/api/extractions")

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert "data" in result
        assert "pagination" in result
        assert len(result["data"]) == 2
        assert result["pagination"]["limit"] == 50
        assert result["pagination"]["offset"] == 0
        assert result["pagination"]["count"] == 2
        assert result["pagination"]["has_more"] is False

        # Verify function call with defaults
        mock_list_extractions.assert_called_once_with(
            mock_supabase_client.return_value,
            limit=50,
            offset=0,
            status=None,
        )

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.list_extractions")
    def test_list_extractions_with_pagination(
        self,
        mock_list_extractions: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test listing extractions with custom pagination."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        # Return exactly 10 items (same as limit) to test has_more=True
        mock_list_extractions.return_value = [
            {"id": f"uuid-{i}", "file_name": f"doc{i}.pdf", "status": "completed"}
            for i in range(10)
        ]

        # Make request with custom pagination
        response = client.get("/api/extractions?limit=10&offset=20")

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["pagination"]["limit"] == 10
        assert result["pagination"]["offset"] == 20
        assert result["pagination"]["count"] == 10
        assert result["pagination"]["has_more"] is True  # count == limit

        # Verify function call
        mock_list_extractions.assert_called_once_with(
            mock_supabase_client.return_value,
            limit=10,
            offset=20,
            status=None,
        )

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.list_extractions")
    def test_list_extractions_with_status_filter(
        self,
        mock_list_extractions: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test listing extractions with status filter."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        failed_extractions = [
            {
                "id": "uuid-1",
                "file_name": "failed.pdf",
                "status": "failed",
                "error_message": "Processing timeout",
            }
        ]
        mock_list_extractions.return_value = failed_extractions

        # Make request with status filter
        response = client.get("/api/extractions?status_filter=failed")

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert len(result["data"]) == 1
        assert result["data"][0]["status"] == "failed"

        # Verify function call with status filter
        mock_list_extractions.assert_called_once_with(
            mock_supabase_client.return_value,
            limit=50,
            offset=0,
            status="failed",
        )

    def test_list_extractions_invalid_limit_too_small(
        self,
        client: TestClient,
    ) -> None:
        """Test listing extractions with invalid limit (too small)."""
        response = client.get("/api/extractions?limit=0")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Limit must be between 1 and 100" in response.json()["detail"]

    def test_list_extractions_invalid_limit_too_large(
        self,
        client: TestClient,
    ) -> None:
        """Test listing extractions with invalid limit (too large)."""
        response = client.get("/api/extractions?limit=101")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Limit must be between 1 and 100" in response.json()["detail"]

    def test_list_extractions_invalid_offset(
        self,
        client: TestClient,
    ) -> None:
        """Test listing extractions with negative offset."""
        response = client.get("/api/extractions?offset=-1")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Offset must be non-negative" in response.json()["detail"]

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.list_extractions")
    def test_list_extractions_invalid_status_filter(
        self,
        mock_list_extractions: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test listing extractions with invalid status filter."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        mock_list_extractions.side_effect = ValueError("Invalid status filter 'invalid'")

        # Make request with invalid status
        response = client.get("/api/extractions?status_filter=invalid")

        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid status filter" in response.json()["detail"]

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.list_extractions")
    def test_list_extractions_database_error(
        self,
        mock_list_extractions: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test listing extractions when database error occurs."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        mock_list_extractions.side_effect = Exception("Database connection failed")

        # Make request
        response = client.get("/api/extractions")

        # Assertions
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Database error" in response.json()["detail"]

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.list_extractions")
    def test_list_extractions_empty_result(
        self,
        mock_list_extractions: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test listing extractions with no results."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        mock_list_extractions.return_value = []

        # Make request
        response = client.get("/api/extractions")

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["data"] == []
        assert result["pagination"]["count"] == 0
        assert result["pagination"]["has_more"] is False


class TestGetBoundingBoxesEndpoint:
    """Tests for GET /api/extractions/{extraction_id}/bounding-boxes endpoint."""

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.get_extraction")
    def test_get_bounding_boxes_success(
        self,
        mock_get_extraction: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test successful retrieval of all bounding boxes."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        extraction_data = {
            "id": "12345678-1234-5678-1234-567812345678",
            "bounding_boxes": {
                "title_1": {"x1": 100, "y1": 200, "x2": 300, "y2": 220, "page": 1},
                "section_1": {"x1": 100, "y1": 250, "x2": 400, "y2": 270, "page": 1},
                "table_1": {"x1": 100, "y1": 300, "x2": 500, "y2": 400, "page": 2},
            },
        }
        mock_get_extraction.return_value = extraction_data

        # Make request
        response = client.get("/api/extractions/12345678-1234-5678-1234-567812345678/bounding-boxes")

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert len(result) == 3
        assert "title_1" in result
        assert "section_1" in result
        assert "table_1" in result
        assert result["title_1"]["page"] == 1
        assert result["table_1"]["page"] == 2

        # Verify function call
        mock_get_extraction.assert_called_once_with(
            mock_supabase_client.return_value,
            "12345678-1234-5678-1234-567812345678",
        )

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.get_extraction")
    def test_get_bounding_boxes_empty(
        self,
        mock_get_extraction: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test retrieval when no bounding boxes exist."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        extraction_data = {
            "id": "12345678-1234-5678-1234-567812345678",
            "bounding_boxes": {},
        }
        mock_get_extraction.return_value = extraction_data

        # Make request
        response = client.get("/api/extractions/12345678-1234-5678-1234-567812345678/bounding-boxes")

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result == {}

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.get_extraction")
    def test_get_bounding_boxes_not_found(
        self,
        mock_get_extraction: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test bounding boxes retrieval when extraction not found."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        mock_get_extraction.return_value = None

        # Make request
        response = client.get("/api/extractions/12345678-1234-5678-1234-567812345678/bounding-boxes")

        # Assertions
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"]

    def test_get_bounding_boxes_invalid_uuid(
        self,
        client: TestClient,
    ) -> None:
        """Test bounding boxes retrieval with invalid UUID format."""
        # Make request with invalid UUID
        response = client.get("/api/extractions/not-a-valid-uuid/bounding-boxes")

        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid UUID format" in response.json()["detail"]

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.get_extraction")
    def test_get_bounding_boxes_database_error(
        self,
        mock_get_extraction: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test bounding boxes retrieval when database error occurs."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        mock_get_extraction.side_effect = Exception("Database connection failed")

        # Make request
        response = client.get("/api/extractions/12345678-1234-5678-1234-567812345678/bounding-boxes")

        # Assertions
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Database error" in response.json()["detail"]


class TestGetElementEndpoint:
    """Tests for GET /api/extractions/{extraction_id}/elements/{element_id} endpoint."""

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.get_extraction")
    def test_get_element_success_section(
        self,
        mock_get_extraction: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test successful retrieval of a section element."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        bbox = {"x1": 100, "y1": 200, "x2": 300, "y2": 220, "page": 1}
        extraction_data = {
            "id": "12345678-1234-5678-1234-567812345678",
            "bounding_boxes": {
                "section_1": bbox,
            },
            "sections": [
                {
                    "heading": "Introduction",
                    "content": "This is the introduction section.",
                    "page_number": 1,
                    "bbox": bbox,
                }
            ],
        }
        mock_get_extraction.return_value = extraction_data

        # Make request
        response = client.get("/api/extractions/12345678-1234-5678-1234-567812345678/elements/section_1")

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["element_id"] == "section_1"
        assert result["element_type"] == "section"
        assert result["bounding_box"] == bbox
        assert result["content"]["heading"] == "Introduction"
        assert result["content"]["content"] == "This is the introduction section."
        assert result["content"]["page_number"] == 1

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.get_extraction")
    def test_get_element_success_table(
        self,
        mock_get_extraction: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test successful retrieval of a table element."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        bbox = {"x1": 100, "y1": 300, "x2": 500, "y2": 400, "page": 2}
        extraction_data = {
            "id": "12345678-1234-5678-1234-567812345678",
            "bounding_boxes": {
                "table_1": bbox,
            },
            "tables": [
                {
                    "caption": "Table 1: Results",
                    "page_number": 2,
                    "data": [{"col1": "value1", "col2": "value2"}],
                    "bbox": bbox,
                }
            ],
        }
        mock_get_extraction.return_value = extraction_data

        # Make request
        response = client.get("/api/extractions/12345678-1234-5678-1234-567812345678/elements/table_1")

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["element_id"] == "table_1"
        assert result["element_type"] == "table"
        assert result["bounding_box"] == bbox
        assert result["content"]["caption"] == "Table 1: Results"
        assert result["content"]["page_number"] == 2
        assert len(result["content"]["data"]) == 1

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.get_extraction")
    def test_get_element_no_content_match(
        self,
        mock_get_extraction: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test element retrieval when bbox exists but no content matches."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        bbox = {"x1": 100, "y1": 200, "x2": 300, "y2": 220, "page": 1}
        extraction_data = {
            "id": "12345678-1234-5678-1234-567812345678",
            "bounding_boxes": {
                "element_1": bbox,
            },
            "sections": [],
            "tables": [],
        }
        mock_get_extraction.return_value = extraction_data

        # Make request
        response = client.get("/api/extractions/12345678-1234-5678-1234-567812345678/elements/element_1")

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["element_id"] == "element_1"
        assert result["element_type"] == "element"
        assert result["bounding_box"] == bbox
        assert result["content"] == {}

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.get_extraction")
    def test_get_element_not_found(
        self,
        mock_get_extraction: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test element retrieval when element_id not found."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        extraction_data = {
            "id": "12345678-1234-5678-1234-567812345678",
            "bounding_boxes": {
                "other_element": {"x1": 100, "y1": 200, "x2": 300, "y2": 220, "page": 1},
            },
        }
        mock_get_extraction.return_value = extraction_data

        # Make request
        response = client.get("/api/extractions/12345678-1234-5678-1234-567812345678/elements/missing_element")

        # Assertions
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Element not found" in response.json()["detail"]

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.get_extraction")
    def test_get_element_extraction_not_found(
        self,
        mock_get_extraction: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test element retrieval when extraction not found."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        mock_get_extraction.return_value = None

        # Make request
        response = client.get("/api/extractions/12345678-1234-5678-1234-567812345678/elements/element_1")

        # Assertions
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Extraction not found" in response.json()["detail"]

    def test_get_element_invalid_uuid(
        self,
        client: TestClient,
    ) -> None:
        """Test element retrieval with invalid UUID format."""
        # Make request with invalid UUID
        response = client.get("/api/extractions/not-a-valid-uuid/elements/element_1")

        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid UUID format" in response.json()["detail"]

    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.get_extraction")
    def test_get_element_database_error(
        self,
        mock_get_extraction: AsyncMock,
        mock_supabase_client: MagicMock,
        client: TestClient,
    ) -> None:
        """Test element retrieval when database error occurs."""
        # Setup mocks
        mock_supabase_client.return_value = MagicMock()
        mock_get_extraction.side_effect = Exception("Database connection failed")

        # Make request
        response = client.get("/api/extractions/12345678-1234-5678-1234-567812345678/elements/element_1")

        # Assertions
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Database error" in response.json()["detail"]


class TestPartialExtractionAndRetry:
    """Tests for partial extraction and retry functionality."""

    @patch("app.routers.extraction.validate_pdf")
    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.check_duplicate")
    @patch("app.routers.extraction.get_gemini_client")
    @patch("app.routers.extraction.extract_pdf_data_hybrid")
    @patch("app.routers.extraction.create_extraction")
    @patch("app.routers.extraction.os.path.exists")
    @patch("app.routers.extraction.os.remove")
    def test_partial_extraction_on_gemini_failure(
        self,
        mock_remove: MagicMock,
        mock_exists: MagicMock,
        mock_create_extraction: AsyncMock,
        mock_extract_hybrid: AsyncMock,
        mock_gemini_client: MagicMock,
        mock_check_duplicate: AsyncMock,
        mock_supabase_client: MagicMock,
        mock_validate: AsyncMock,
        client: TestClient,
        sample_pdf_content: bytes,
    ) -> None:
        """Test that partial results are saved when Gemini extraction fails."""
        from app.services.pdf_extractor import PartialExtractionError
        from app.models.extraction import ExtractedMetadata, ExtractionResult

        # Setup mocks
        mock_validate.return_value = (sample_pdf_content, "hash123", "test.pdf")
        mock_supabase_client.return_value = MagicMock()
        mock_check_duplicate.return_value = None
        mock_gemini_client.return_value = MagicMock()
        mock_exists.return_value = True

        # Create partial result (OpenDataLoader succeeded, Gemini failed)
        partial_result = ExtractionResult(
            metadata=ExtractedMetadata(title="[Partial Extraction]"),
            abstract=None,
            sections=[],
            tables=[],
            references=[],
            confidence_score=0.0,
            bounding_boxes={},
            processing_metadata={
                "method": "partial",
                "error": "API timeout",
                "error_type": "TimeoutError"
            }
        )

        # Simulate PartialExtractionError
        mock_extract_hybrid.side_effect = PartialExtractionError(
            message="Gemini extraction failed: API timeout",
            partial_result=partial_result,
            original_exception=TimeoutError("API timeout")
        )

        mock_create_extraction.return_value = "partial-uuid-123"

        # Make request (explicit doc_type skips auto-classification)
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        data = {"doc_type": "question_paper"}
        response = client.post("/api/extract", files=files, data=data)

        # Assertions
        assert response.status_code == status.HTTP_206_PARTIAL_CONTENT
        assert response.headers["X-Extraction-ID"] == "partial-uuid-123"

        # Verify create_extraction was called with status='partial'
        call_args = mock_create_extraction.call_args
        assert call_args[1]["status"] == "partial"
        assert "error_message" in call_args[0][2]

    @patch("app.routers.extraction.validate_pdf")
    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.check_duplicate")
    @patch("app.routers.extraction.get_extraction")
    @patch("app.routers.extraction.get_gemini_client")
    @patch("app.routers.extraction.extract_pdf_data_hybrid")
    @patch("app.routers.extraction.update_extraction")
    @patch("app.routers.extraction.os.path.exists")
    @patch("app.routers.extraction.os.remove")
    def test_retry_partial_extraction_success(
        self,
        mock_remove: MagicMock,
        mock_exists: MagicMock,
        mock_update_extraction: AsyncMock,
        mock_extract_hybrid: AsyncMock,
        mock_gemini_client: MagicMock,
        mock_get_extraction: AsyncMock,
        mock_check_duplicate: AsyncMock,
        mock_supabase_client: MagicMock,
        mock_validate: AsyncMock,
        client: TestClient,
        sample_pdf_content: bytes,
        sample_extraction_result: ExtractionResult,
    ) -> None:
        """Test that re-uploading a partial extraction retries and updates the record."""
        # Setup mocks
        mock_validate.return_value = (sample_pdf_content, "hash123", "test.pdf")
        mock_supabase_client.return_value = MagicMock()

        # Existing partial extraction
        existing_id = "partial-uuid-123"
        mock_check_duplicate.return_value = existing_id
        mock_get_extraction.return_value = {
            "id": existing_id,
            "status": "partial",
            "retry_count": 0,
        }

        mock_gemini_client.return_value = MagicMock()
        mock_extract_hybrid.return_value = sample_extraction_result
        mock_exists.return_value = True

        # Make request (retry, explicit doc_type skips auto-classification)
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        data = {"doc_type": "question_paper"}
        response = client.post("/api/extract", files=files, data=data)

        # Assertions
        assert response.status_code == status.HTTP_201_CREATED  # Now completed
        assert response.headers["X-Extraction-ID"] == existing_id

        # Verify update_extraction was called (not create_extraction)
        assert mock_update_extraction.called
        call_args = mock_update_extraction.call_args
        assert call_args[0][1] == existing_id  # Same ID
        assert call_args[1]["status"] == "completed"
        assert call_args[1]["retry_count"] == 1

    @patch("app.routers.extraction.validate_pdf")
    @patch("app.routers.extraction.get_supabase_client")
    @patch("app.routers.extraction.check_duplicate")
    @patch("app.routers.extraction.get_extraction")
    def test_retry_completed_extraction_returns_existing(
        self,
        mock_get_extraction: AsyncMock,
        mock_check_duplicate: AsyncMock,
        mock_supabase_client: MagicMock,
        mock_validate: AsyncMock,
        client: TestClient,
        sample_pdf_content: bytes,
    ) -> None:
        """Test that re-uploading a completed extraction returns the existing result."""
        # Setup mocks
        mock_validate.return_value = (sample_pdf_content, "hash123", "test.pdf")
        mock_supabase_client.return_value = MagicMock()

        # Existing completed extraction
        existing_id = "completed-uuid-123"
        mock_check_duplicate.return_value = existing_id
        mock_get_extraction.return_value = {
            "id": existing_id,
            "status": "completed",
            "metadata": {"title": "Test Paper"},
        }

        # Make request (explicit doc_type skips auto-classification)
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        data = {"doc_type": "question_paper"}
        response = client.post("/api/extract", files=files, data=data)

        # Assertions
        assert response.status_code == status.HTTP_200_OK  # Not 201
        assert response.headers["X-Extraction-ID"] == existing_id

    def test_retry_endpoint_returns_instructions(
        self,
        client: TestClient,
    ) -> None:
        """Test that retry endpoint returns instructions to re-upload file."""
        # Make request
        response = client.post("/api/extractions/12345678-1234-5678-1234-567812345678/retry")

        # Assertions
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        detail = response.json()["detail"]
        assert "message" in detail
        assert "re-upload" in detail["message"]
        assert "instructions" in detail
        assert detail["extraction_id"] == "12345678-1234-5678-1234-567812345678"
