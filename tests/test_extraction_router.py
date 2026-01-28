"""Tests for extraction API endpoints."""

import json
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
from app.models.extraction import (
    BoundingBox,
    ExtractedMetadata,
    ExtractionResult,
)


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

        # Make request
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        response = client.post("/api/extract", files=files)

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

        # Make request
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        response = client.post("/api/extract", files=files)

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

        # Make request
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        response = client.post("/api/extract", files=files)

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

        # Make request
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        response = client.post("/api/extract", files=files)

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

        # Make request
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        response = client.post("/api/extract", files=files)

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

        # Make request with webhook_url
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        data = {"webhook_url": "https://example.com/webhook"}
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

        # Make request
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        response = client.post("/api/extract", files=files)

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

        # Make request
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        response = client.post("/api/extract", files=files)

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

        # Make request
        files = {"file": ("test.pdf", BytesIO(sample_pdf_content), "application/pdf")}
        response = client.post("/api/extract", files=files)

        # Assertions - should still succeed
        assert response.status_code == status.HTTP_201_CREATED
        assert response.headers["X-Extraction-ID"] == "uuid-123"

        # Verify cleanup was attempted
        mock_remove.assert_called_once()
