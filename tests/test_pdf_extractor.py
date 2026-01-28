"""
Tests for hybrid PDF extraction pipeline.

Tests the integration of OpenDataLoader structure extraction with Gemini semantic analysis.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from google import genai

from app.services.pdf_extractor import (
    extract_pdf_data_hybrid,
    extract_with_vision_fallback
)
from app.models.extraction import (
    ExtractionResult,
    ExtractedMetadata,
    DocumentStructure,
    ExtractedTable
)


@pytest.fixture
def mock_gemini_client():
    """Create a mock Gemini client for testing."""
    return MagicMock(spec=genai.Client)


@pytest.fixture
def mock_high_quality_structure():
    """Create a high-quality DocumentStructure (quality_score >= 0.7)."""
    return DocumentStructure(
        markdown="# Introduction\n\nThis is a test paper.\n\n## Methods\n\nWe used method X.",
        tables=[
            {
                "caption": "Table 1: Results",
                "page": 2,
                "data": [
                    {"col1": "row1", "col2": "val1"},
                    {"col1": "row2", "col2": "val2"},
                    {"col1": "row3", "col2": "val3"},
                    {"col1": "row4", "col2": "val4"}
                ],
                "bbox": {"x1": 10.0, "y1": 20.0, "x2": 100.0, "y2": 80.0, "page": 2}
            }
        ],
        bounding_boxes={
            "heading_1_0": {"x1": 10.0, "y1": 10.0, "x2": 50.0, "y2": 20.0, "page": 1}
        },
        quality_score=0.85,
        element_count=42
    )


@pytest.fixture
def mock_low_quality_structure():
    """Create a low-quality DocumentStructure (quality_score < 0.7)."""
    return DocumentStructure(
        markdown="Some text",
        tables=[],
        bounding_boxes={},
        quality_score=0.5,
        element_count=3
    )


@pytest.fixture
def mock_gemini_response():
    """Create a mock Gemini API response with structured data."""
    result = ExtractionResult(
        metadata=ExtractedMetadata(
            title="Test Paper Title",
            authors=["Author One", "Author Two"],
            journal="Test Journal",
            year=2023,
            doi="10.1234/test.doi"
        ),
        abstract="This is the abstract of the test paper.",
        sections=[
            {
                "heading": "Introduction",
                "content": "Introduction content here.",
                "page_number": 1
            },
            {
                "heading": "Methods",
                "content": "Methods content here.",
                "page_number": 2
            }
        ],
        tables=[],  # Will be replaced with OpenDataLoader tables
        references=[
            {
                "citation_text": "Author et al. (2020). Paper title.",
                "authors": ["Author"],
                "year": 2020,
                "title": "Paper title"
            }
        ],
        confidence_score=0.9,
        bounding_boxes={},  # Will be replaced with OpenDataLoader bboxes
        processing_metadata={}
    )

    mock_response = Mock()
    mock_response.parsed = result
    return mock_response


class TestVisionFallback:
    """Tests for Vision API fallback function."""

    def test_vision_fallback_successful_extraction(self, mock_gemini_client):
        """Test successful Vision API fallback extraction."""
        # Mock file upload
        mock_uploaded_file = Mock()
        mock_uploaded_file.name = "uploaded_file_123"
        mock_gemini_client.files.upload.return_value = mock_uploaded_file

        # Mock Gemini API response
        mock_result = ExtractionResult(
            metadata=ExtractedMetadata(
                title="Scanned Paper Title",
                authors=["Vision Author"],
                year=2024
            ),
            abstract="Abstract from vision analysis.",
            sections=[
                {
                    "heading": "Introduction",
                    "content": "Content extracted via Vision API.",
                    "page_number": 1
                }
            ],
            tables=[
                {
                    "caption": "Vision-extracted table",
                    "page_number": 2,
                    "data": [{"col": "val"}]
                }
            ],
            references=[],
            confidence_score=0.85,
            bounding_boxes={},
            processing_metadata={}
        )

        mock_response = Mock()
        mock_response.parsed = mock_result
        mock_gemini_client.models.generate_content.return_value = mock_response

        # Execute Vision fallback
        result = extract_with_vision_fallback(
            mock_gemini_client,
            "scanned.pdf",
            model="gemini-3-flash-preview"
        )

        # Verify file upload
        mock_gemini_client.files.upload.assert_called_once_with(file="scanned.pdf")

        # Verify Gemini API call with uploaded file
        mock_gemini_client.models.generate_content.assert_called_once()
        call_args = mock_gemini_client.models.generate_content.call_args
        assert mock_uploaded_file in call_args[1]["contents"]
        assert "academic research paper" in call_args[1]["contents"][1]

        # Verify file cleanup
        mock_gemini_client.files.delete.assert_called_once_with(name="uploaded_file_123")

        # Verify result
        assert result.metadata.title == "Scanned Paper Title"
        assert result.abstract == "Abstract from vision analysis."
        assert len(result.sections) == 1
        assert len(result.tables) == 1

        # Verify processing metadata
        assert result.processing_metadata["method"] == "vision_fallback"
        assert result.processing_metadata["reason"] == "Low OpenDataLoader quality score"
        assert result.processing_metadata["cost_savings_percent"] == 0
        assert result.processing_metadata["model"] == "gemini-3-flash-preview"

    def test_vision_fallback_cleanup_on_success(self, mock_gemini_client):
        """Test that uploaded files are cleaned up after successful extraction."""
        mock_uploaded_file = Mock()
        mock_uploaded_file.name = "temp_file_456"
        mock_gemini_client.files.upload.return_value = mock_uploaded_file

        mock_result = ExtractionResult(
            metadata=ExtractedMetadata(title="Test", authors=[]),
            sections=[],
            tables=[],
            references=[],
            confidence_score=0.8,
            bounding_boxes={},
            processing_metadata={}
        )
        mock_response = Mock()
        mock_response.parsed = mock_result
        mock_gemini_client.models.generate_content.return_value = mock_response

        # Execute
        extract_with_vision_fallback(mock_gemini_client, "test.pdf")

        # Verify cleanup
        mock_gemini_client.files.delete.assert_called_once_with(name="temp_file_456")

    def test_vision_fallback_cleanup_on_error(self, mock_gemini_client):
        """Test that uploaded files are cleaned up even when extraction fails.

        Note: With retry logic, the function retries 5 times (6 total attempts),
        so cleanup happens 6 times - once per attempt in the finally block.
        """
        mock_uploaded_file = Mock()
        mock_uploaded_file.name = "temp_file_789"
        mock_gemini_client.files.upload.return_value = mock_uploaded_file

        # Mock API error
        mock_gemini_client.models.generate_content.side_effect = Exception("API Error")

        # Execute and expect error
        with pytest.raises(Exception, match="API Error"):
            extract_with_vision_fallback(mock_gemini_client, "test.pdf")

        # Verify cleanup still happened (6 times: initial + 5 retries)
        assert mock_gemini_client.files.delete.call_count == 6
        mock_gemini_client.files.delete.assert_called_with(name="temp_file_789")

    def test_vision_fallback_no_cleanup_if_upload_fails(self, mock_gemini_client):
        """Test that cleanup isn't attempted if file upload fails."""
        # Mock upload failure
        mock_gemini_client.files.upload.side_effect = ValueError("Upload failed")

        # Execute and expect error
        with pytest.raises(ValueError, match="Upload failed"):
            extract_with_vision_fallback(mock_gemini_client, "test.pdf")

        # Verify no cleanup attempt (file was never uploaded)
        mock_gemini_client.files.delete.assert_not_called()

    def test_vision_fallback_silences_cleanup_errors(self, mock_gemini_client):
        """Test that cleanup errors don't prevent extraction result from being returned."""
        mock_uploaded_file = Mock()
        mock_uploaded_file.name = "file_with_cleanup_error"
        mock_gemini_client.files.upload.return_value = mock_uploaded_file

        mock_result = ExtractionResult(
            metadata=ExtractedMetadata(title="Test", authors=[]),
            sections=[],
            tables=[],
            references=[],
            confidence_score=0.8,
            bounding_boxes={},
            processing_metadata={}
        )
        mock_response = Mock()
        mock_response.parsed = mock_result
        mock_gemini_client.models.generate_content.return_value = mock_response

        # Mock cleanup failure
        mock_gemini_client.files.delete.side_effect = Exception("Delete failed")

        # Execute - should succeed despite cleanup error
        result = extract_with_vision_fallback(mock_gemini_client, "test.pdf")

        # Verify result was still returned
        assert result.metadata.title == "Test"
        # Cleanup was attempted (even though it failed)
        mock_gemini_client.files.delete.assert_called_once()

    def test_vision_fallback_custom_model(self, mock_gemini_client):
        """Test Vision fallback with custom model."""
        mock_uploaded_file = Mock()
        mock_uploaded_file.name = "file_123"
        mock_gemini_client.files.upload.return_value = mock_uploaded_file

        mock_result = ExtractionResult(
            metadata=ExtractedMetadata(title="Test", authors=[]),
            sections=[],
            tables=[],
            references=[],
            confidence_score=0.9,
            bounding_boxes={},
            processing_metadata={}
        )
        mock_response = Mock()
        mock_response.parsed = mock_result
        mock_gemini_client.models.generate_content.return_value = mock_response

        # Execute with custom model
        result = extract_with_vision_fallback(
            mock_gemini_client,
            "test.pdf",
            model="gemini-3-pro-vision"
        )

        # Verify custom model was used
        call_args = mock_gemini_client.models.generate_content.call_args
        assert call_args[1]["model"] == "gemini-3-pro-vision"
        assert result.processing_metadata["model"] == "gemini-3-pro-vision"


@pytest.mark.asyncio
class TestHybridExtraction:
    """Tests for hybrid extraction pipeline."""

    async def test_hybrid_extraction_high_quality(
        self,
        mock_gemini_client,
        mock_high_quality_structure,
        mock_gemini_response
    ):
        """Test hybrid extraction with high-quality PDF (quality_score >= 0.7)."""
        # Mock OpenDataLoader extraction
        with patch('app.services.pdf_extractor.extract_pdf_structure') as mock_extract:
            mock_extract.return_value = mock_high_quality_structure

            # Mock Gemini API call
            mock_gemini_client.models.generate_content.return_value = mock_gemini_response

            # Execute extraction
            result = await extract_pdf_data_hybrid(
                mock_gemini_client,
                "test.pdf",
                model="gemini-3-flash-preview"
            )

            # Verify OpenDataLoader was called
            mock_extract.assert_called_once_with("test.pdf")

            # Verify Gemini API was called
            mock_gemini_client.models.generate_content.assert_called_once()
            call_args = mock_gemini_client.models.generate_content.call_args

            # Verify prompt contains markdown
            prompt_content = call_args[1]["contents"]
            assert "# Introduction" in prompt_content
            assert "## Methods" in prompt_content

            # Verify result structure
            assert result.metadata.title == "Test Paper Title"
            assert len(result.metadata.authors) == 2
            assert result.abstract == "This is the abstract of the test paper."
            assert len(result.sections) == 2

            # Verify tables were replaced with OpenDataLoader tables
            assert len(result.tables) == 1
            assert result.tables[0].caption == "Table 1: Results"
            assert result.tables[0].page_number == 2
            assert len(result.tables[0].data) == 4

            # Verify bounding boxes from OpenDataLoader
            assert "heading_1_0" in result.bounding_boxes

            # Verify processing metadata
            assert result.processing_metadata["method"] == "hybrid"
            assert result.processing_metadata["opendataloader_quality"] == 0.85
            assert result.processing_metadata["cost_savings_percent"] == 80
            assert result.processing_metadata["element_count"] == 42
            assert result.processing_metadata["model"] == "gemini-3-flash-preview"

    async def test_hybrid_extraction_low_quality_triggers_fallback(
        self,
        mock_gemini_client,
        mock_low_quality_structure
    ):
        """Test that low quality PDFs trigger Vision API fallback."""
        # Mock OpenDataLoader extraction
        with patch('app.services.pdf_extractor.extract_pdf_structure') as mock_extract:
            mock_extract.return_value = mock_low_quality_structure

            # Mock file upload for Vision fallback
            mock_uploaded_file = Mock()
            mock_uploaded_file.name = "fallback_file_123"
            mock_gemini_client.files.upload.return_value = mock_uploaded_file

            # Mock Vision API response
            fallback_result = ExtractionResult(
                metadata=ExtractedMetadata(title="Fallback Title", authors=[]),
                sections=[],
                tables=[],
                references=[],
                confidence_score=0.75,
                bounding_boxes={},
                processing_metadata={}
            )
            mock_response = Mock()
            mock_response.parsed = fallback_result
            mock_gemini_client.models.generate_content.return_value = mock_response

            # Execute extraction - should trigger Vision fallback
            result = await extract_pdf_data_hybrid(mock_gemini_client, "test.pdf")

            # Verify OpenDataLoader was called
            mock_extract.assert_called_once_with("test.pdf")

            # Verify Vision fallback was triggered (file upload)
            mock_gemini_client.files.upload.assert_called_once_with(file="test.pdf")

            # Verify Gemini API was called via Vision mode
            mock_gemini_client.models.generate_content.assert_called_once()

            # Verify result has fallback metadata
            assert result.processing_metadata["method"] == "vision_fallback"
            assert result.processing_metadata["reason"] == "Low OpenDataLoader quality score"
            assert result.processing_metadata["cost_savings_percent"] == 0

    async def test_hybrid_extraction_threshold_boundary(
        self,
        mock_gemini_client,
        mock_gemini_response
    ):
        """Test behavior at quality score threshold (0.7)."""
        # Test at exactly 0.7 (should use hybrid mode)
        boundary_structure = DocumentStructure(
            markdown="Content",
            tables=[],
            bounding_boxes={},
            quality_score=0.7,
            element_count=10
        )

        with patch('app.services.pdf_extractor.extract_pdf_structure') as mock_extract:
            mock_extract.return_value = boundary_structure
            mock_gemini_client.models.generate_content.return_value = mock_gemini_response

            result = await extract_pdf_data_hybrid(mock_gemini_client, "test.pdf")

            # At 0.7, should use hybrid mode (not fallback)
            assert result.processing_metadata["method"] == "hybrid"
            mock_gemini_client.models.generate_content.assert_called_once()

        # Test just below 0.7 (should trigger fallback)
        below_threshold = DocumentStructure(
            markdown="Content",
            tables=[],
            bounding_boxes={},
            quality_score=0.69,
            element_count=10
        )

        with patch('app.services.pdf_extractor.extract_pdf_structure') as mock_extract:
            mock_extract.return_value = below_threshold

            # Mock Vision fallback
            mock_uploaded_file = Mock()
            mock_uploaded_file.name = "threshold_file"
            mock_gemini_client.files.upload.return_value = mock_uploaded_file

            fallback_result = ExtractionResult(
                metadata=ExtractedMetadata(title="Threshold Test", authors=[]),
                sections=[],
                tables=[],
                references=[],
                confidence_score=0.7,
                bounding_boxes={},
                processing_metadata={}
            )
            mock_response = Mock()
            mock_response.parsed = fallback_result
            mock_gemini_client.models.generate_content.return_value = mock_response

            result = await extract_pdf_data_hybrid(mock_gemini_client, "test.pdf")
            assert result.processing_metadata["method"] == "vision_fallback"

    async def test_hybrid_extraction_preserves_table_bboxes(
        self,
        mock_gemini_client,
        mock_gemini_response
    ):
        """Test that table bounding boxes from OpenDataLoader are preserved."""
        structure_with_bbox = DocumentStructure(
            markdown="Content",
            tables=[
                {
                    "caption": "Table with bbox",
                    "page": 3,
                    "data": [{"a": "1"}, {"a": "2"}, {"a": "3"}, {"a": "4"}],
                    "bbox": {"x1": 50.0, "y1": 100.0, "x2": 200.0, "y2": 300.0, "page": 3}
                }
            ],
            bounding_boxes={},
            quality_score=0.8,
            element_count=20
        )

        with patch('app.services.pdf_extractor.extract_pdf_structure') as mock_extract:
            mock_extract.return_value = structure_with_bbox
            mock_gemini_client.models.generate_content.return_value = mock_gemini_response

            result = await extract_pdf_data_hybrid(mock_gemini_client, "test.pdf")

            # Verify table bbox is preserved
            assert result.tables[0].bbox is not None
            assert result.tables[0].bbox.x1 == 50.0
            assert result.tables[0].bbox.y1 == 100.0
            assert result.tables[0].bbox.x2 == 200.0
            assert result.tables[0].bbox.y2 == 300.0
            assert result.tables[0].bbox.page == 3

    async def test_hybrid_extraction_no_tables(
        self,
        mock_gemini_client,
        mock_gemini_response
    ):
        """Test extraction when PDF has no tables."""
        no_tables_structure = DocumentStructure(
            markdown="# Paper\n\nContent without tables.",
            tables=[],
            bounding_boxes={},
            quality_score=0.75,
            element_count=15
        )

        with patch('app.services.pdf_extractor.extract_pdf_structure') as mock_extract:
            mock_extract.return_value = no_tables_structure
            mock_gemini_client.models.generate_content.return_value = mock_gemini_response

            result = await extract_pdf_data_hybrid(mock_gemini_client, "test.pdf")

            # Should complete successfully with empty tables list
            assert result.tables == []
            assert result.processing_metadata["method"] == "hybrid"

    async def test_hybrid_extraction_custom_model(
        self,
        mock_gemini_client,
        mock_high_quality_structure,
        mock_gemini_response
    ):
        """Test extraction with custom Gemini model."""
        with patch('app.services.pdf_extractor.extract_pdf_structure') as mock_extract:
            mock_extract.return_value = mock_high_quality_structure
            mock_gemini_client.models.generate_content.return_value = mock_gemini_response

            result = await extract_pdf_data_hybrid(
                mock_gemini_client,
                "test.pdf",
                model="gemini-3-pro-preview"
            )

            # Verify custom model was used
            call_args = mock_gemini_client.models.generate_content.call_args
            assert call_args[1]["model"] == "gemini-3-pro-preview"
            assert result.processing_metadata["model"] == "gemini-3-pro-preview"

    async def test_hybrid_extraction_file_not_found(self, mock_gemini_client):
        """Test that FileNotFoundError is propagated from OpenDataLoader."""
        with patch('app.services.pdf_extractor.extract_pdf_structure') as mock_extract:
            mock_extract.side_effect = FileNotFoundError("PDF file not found: nonexistent.pdf")

            with pytest.raises(FileNotFoundError, match="PDF file not found"):
                await extract_pdf_data_hybrid(mock_gemini_client, "nonexistent.pdf")

    async def test_hybrid_extraction_invalid_pdf(self, mock_gemini_client):
        """Test that ValueError is propagated for invalid PDFs."""
        with patch('app.services.pdf_extractor.extract_pdf_structure') as mock_extract:
            mock_extract.side_effect = ValueError("Failed to extract PDF structure")

            with pytest.raises(ValueError, match="Failed to extract PDF structure"):
                await extract_pdf_data_hybrid(mock_gemini_client, "invalid.pdf")
