"""
Tests for OpenDataLoader PDF structure extraction service.
"""

import pytest
import json
from unittest.mock import patch, mock_open, MagicMock
from app.services.opendataloader_extractor import extract_pdf_structure
from app.models.extraction import DocumentStructure


class TestExtractPdfStructure:
    """Test suite for extract_pdf_structure function."""

    def _mock_opendataloader_files(self, json_data, markdown_content="# Test"):
        """Helper to mock file reads for JSON and Markdown outputs."""
        def open_side_effect(path, *args, **kwargs):
            mock_file = MagicMock()
            if path.endswith('.json'):
                mock_file.__enter__.return_value.read.return_value = json.dumps(json_data)
            elif path.endswith('.md'):
                mock_file.__enter__.return_value.read.return_value = markdown_content
            return mock_file
        return open_side_effect

    def test_extract_pdf_structure_success(self):
        """Test successful PDF structure extraction."""
        json_data = {
            "elements": [
                {
                    "type": "heading",
                    "page": 1,
                    "text": "Test Heading",
                    "bbox": {"x1": 10.0, "y1": 20.0, "x2": 100.0, "y2": 30.0}
                },
                {
                    "type": "paragraph",
                    "page": 1,
                    "text": "Some content",
                    "bbox": {"x1": 10.0, "y1": 35.0, "x2": 100.0, "y2": 50.0}
                },
                {
                    "type": "table",
                    "page": 1,
                    "text": "Table 1",
                    "table_data": [{"col1": "val1", "col2": "val2"}],
                    "bbox": {"x1": 10.0, "y1": 100.0, "x2": 200.0, "y2": 150.0}
                }
            ]
        }

        markdown_content = "# Test Document\n\nSome content."

        with patch('app.services.opendataloader_extractor.convert'), \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', side_effect=self._mock_opendataloader_files(json_data, markdown_content)):

            result = extract_pdf_structure("test.pdf")

        assert isinstance(result, DocumentStructure)
        assert result.markdown == markdown_content
        assert len(result.tables) == 1
        assert result.tables[0]["caption"] == "Table 1"
        assert result.tables[0]["page"] == 1
        assert len(result.tables[0]["data"]) == 1
        assert "bbox" in result.tables[0]
        assert result.element_count == 3
        assert len(result.bounding_boxes) == 3

    def test_extract_pdf_structure_with_tables(self):
        """Test extraction with multiple tables."""
        json_data = {
            "elements": [
                {
                    "type": "table",
                    "page": 1,
                    "text": "Table 1",
                    "table_data": [{"a": 1}, {"a": 2}],
                    "bbox": {"x1": 10.0, "y1": 10.0, "x2": 100.0, "y2": 50.0}
                },
                {
                    "type": "table",
                    "page": 2,
                    "text": "Table 2",
                    "table_data": [{"b": 3}, {"b": 4}, {"b": 5}],
                    "bbox": {"x1": 10.0, "y1": 10.0, "x2": 100.0, "y2": 60.0}
                }
            ]
        }

        markdown_content = "# Document\n\nContent with tables."

        with patch('app.services.opendataloader_extractor.convert'), \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', side_effect=self._mock_opendataloader_files(json_data, markdown_content)):

            result = extract_pdf_structure("test.pdf")

        assert len(result.tables) == 2
        assert result.tables[0]["caption"] == "Table 1"
        assert result.tables[1]["caption"] == "Table 2"
        assert len(result.tables[0]["data"]) == 2
        assert len(result.tables[1]["data"]) == 3

    def test_extract_pdf_structure_with_bounding_boxes(self):
        """Test extraction of bounding boxes for all elements."""
        json_data = {
            "elements": [
                {
                    "type": "heading",
                    "page": 1,
                    "text": "Heading",
                    "bbox": {"x1": 10.0, "y1": 20.0, "x2": 100.0, "y2": 30.0}
                },
                {
                    "type": "paragraph",
                    "page": 1,
                    "text": "Paragraph",
                    "bbox": {"x1": 10.0, "y1": 35.0, "x2": 100.0, "y2": 50.0}
                },
                {
                    "type": "table",
                    "page": 2,
                    "text": "Table",
                    "table_data": [],
                    "bbox": {"x1": 15.0, "y1": 40.0, "x2": 120.0, "y2": 80.0}
                }
            ]
        }

        with patch('app.services.opendataloader_extractor.convert'), \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', side_effect=self._mock_opendataloader_files(json_data)):

            result = extract_pdf_structure("test.pdf")

        assert len(result.bounding_boxes) == 3
        bbox_keys = list(result.bounding_boxes.keys())
        assert "heading_1_0" in bbox_keys
        assert "paragraph_1_1" in bbox_keys
        assert "table_2_2" in bbox_keys

        # BoundingBox is a Pydantic model, access via attributes
        heading_bbox = result.bounding_boxes["heading_1_0"]
        assert heading_bbox.x1 == 10.0
        assert heading_bbox.y1 == 20.0
        assert heading_bbox.x2 == 100.0
        assert heading_bbox.y2 == 30.0
        assert heading_bbox.page == 1

    def test_extract_pdf_structure_empty_document(self):
        """Test extraction from document with no elements."""
        json_data = {"elements": []}
        markdown_content = ""

        with patch('app.services.opendataloader_extractor.convert'), \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', side_effect=self._mock_opendataloader_files(json_data, markdown_content)):

            result = extract_pdf_structure("empty.pdf")

        assert result.markdown == ""
        assert len(result.tables) == 0
        assert len(result.bounding_boxes) == 0
        assert result.element_count == 0

    def test_extract_pdf_structure_elements_without_bbox(self):
        """Test extraction when elements don't have bounding boxes."""
        json_data = {
            "elements": [
                {
                    "type": "paragraph",
                    "page": 1,
                    "text": "Content"
                    # No bbox
                }
            ]
        }

        with patch('app.services.opendataloader_extractor.convert'), \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', side_effect=self._mock_opendataloader_files(json_data)):

            result = extract_pdf_structure("test.pdf")

        assert result.element_count == 1
        assert len(result.bounding_boxes) == 0

    def test_extract_pdf_structure_tables_without_bbox(self):
        """Test extraction of tables without bounding boxes."""
        json_data = {
            "elements": [
                {
                    "type": "table",
                    "page": 1,
                    "text": "No bbox table",
                    "table_data": [{"x": 1}]
                    # No bbox
                }
            ]
        }

        with patch('app.services.opendataloader_extractor.convert'), \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', side_effect=self._mock_opendataloader_files(json_data)):

            result = extract_pdf_structure("test.pdf")

        assert len(result.tables) == 1
        assert result.tables[0]["caption"] == "No bbox table"
        assert "bbox" not in result.tables[0]

    def test_extract_pdf_structure_file_not_found(self):
        """Test extraction raises FileNotFoundError for missing file."""
        with patch('os.path.exists', return_value=False):
            with pytest.raises(FileNotFoundError) as exc_info:
                extract_pdf_structure("nonexistent.pdf")

            assert "PDF file not found" in str(exc_info.value)

    def test_extract_pdf_structure_invalid_pdf(self):
        """Test extraction raises ValueError for invalid PDF."""
        with patch('os.path.exists', return_value=True), \
             patch('app.services.opendataloader_extractor.convert', side_effect=Exception("Invalid PDF")):

            with pytest.raises(ValueError) as exc_info:
                extract_pdf_structure("invalid.pdf")

            assert "Failed to extract PDF structure" in str(exc_info.value)
            assert "invalid.pdf" in str(exc_info.value)

    def test_extract_pdf_structure_processing_error(self):
        """Test extraction handles processing errors gracefully."""
        with patch('os.path.exists', return_value=True), \
             patch('app.services.opendataloader_extractor.convert', side_effect=RuntimeError("Processing error")):

            with pytest.raises(ValueError) as exc_info:
                extract_pdf_structure("error.pdf")

            assert "Failed to extract PDF structure" in str(exc_info.value)

    def test_extract_pdf_structure_quality_score_placeholder(self):
        """Test that quality_score is initialized to 0.0 (will be calculated separately)."""
        json_data = {"elements": []}

        with patch('app.services.opendataloader_extractor.convert'), \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', side_effect=self._mock_opendataloader_files(json_data)):

            result = extract_pdf_structure("test.pdf")

        assert result.quality_score == 0.0

    def test_extract_pdf_structure_table_defaults(self):
        """Test that tables have sensible defaults for missing fields."""
        json_data = {
            "elements": [
                {
                    "type": "table",
                    # Missing text (caption), missing page
                    "table_data": [{"col": "val"}]
                }
            ]
        }

        with patch('app.services.opendataloader_extractor.convert'), \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', side_effect=self._mock_opendataloader_files(json_data)):

            result = extract_pdf_structure("test.pdf")

        assert len(result.tables) == 1
        assert result.tables[0]["caption"] == ""
        assert result.tables[0]["page"] == 1
        assert len(result.tables[0]["data"]) == 1
