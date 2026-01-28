"""
Tests for OpenDataLoader PDF structure extraction service.
"""

import pytest
import json
from unittest.mock import patch, mock_open, MagicMock
from app.services.opendataloader_extractor import extract_pdf_structure, calculate_quality_score
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

    def test_extract_pdf_structure_quality_score_calculated(self):
        """Test that quality_score is calculated based on document structure."""
        json_data = {
            "elements": [
                {"type": "heading", "page": 1, "text": "Heading 1", "bbox": {"x1": 10, "y1": 20, "x2": 100, "y2": 30}},
                {"type": "heading", "page": 1, "text": "Heading 2", "bbox": {"x1": 10, "y1": 40, "x2": 100, "y2": 50}},
                {"type": "heading", "page": 1, "text": "Heading 3", "bbox": {"x1": 10, "y1": 60, "x2": 100, "y2": 70}},
                {"type": "heading", "page": 1, "text": "Heading 4", "bbox": {"x1": 10, "y1": 80, "x2": 100, "y2": 90}},
                {"type": "heading", "page": 1, "text": "Heading 5", "bbox": {"x1": 10, "y1": 100, "x2": 100, "y2": 110}},
                {"type": "paragraph", "page": 1, "text": "Some paragraph"},
                {"type": "table", "page": 1, "text": "Table", "table_data": [{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}]},
            ]
        }
        # Long markdown content >1000 chars
        markdown_content = "# Test Document\n\n" + "This is a long document with lots of content. " * 30

        with patch('app.services.opendataloader_extractor.convert'), \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', side_effect=self._mock_opendataloader_files(json_data, markdown_content)):

            result = extract_pdf_structure("test.pdf")

        # Should have high quality score: 0.4 (text) + 0.1 (elements) + 0.15 (headings) + 0.15 (table) = 0.8
        assert result.quality_score > 0.0
        assert result.quality_score <= 1.0

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


class TestCalculateQualityScore:
    """Test suite for calculate_quality_score function."""

    def test_perfect_score(self):
        """Test maximum quality score (1.0) with excellent document."""
        tables = [
            {"data": [{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}]},  # Valid table (>3 rows)
            {"data": [{"b": 5}, {"b": 6}, {"b": 7}, {"b": 8}]}   # Valid table
        ]

        score = calculate_quality_score(
            text_length=2000,    # >1000 = 0.4
            element_count=100,   # >50 = 0.3
            heading_count=10,    # >=5 = 0.15
            tables=tables        # valid tables = 0.15
        )

        assert score == 1.0

    def test_high_quality_score(self):
        """Test high quality score (0.8) with good document."""
        tables = [{"data": [{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}]}]

        score = calculate_quality_score(
            text_length=1500,   # >1000 = 0.4
            element_count=30,   # >20 = 0.2
            heading_count=5,    # >=5 = 0.15
            tables=tables       # valid table = 0.15
        )

        assert abs(score - 0.9) < 0.001  # 0.4 + 0.2 + 0.15 + 0.15

    def test_medium_quality_score(self):
        """Test medium quality score (0.5-0.6) with moderate document."""
        tables = [{"data": [{"a": 1}, {"a": 2}]}]  # Small table (<=3 rows)

        score = calculate_quality_score(
            text_length=700,    # >500 = 0.3
            element_count=15,   # >5 = 0.1
            heading_count=3,    # >=3 = 0.1
            tables=tables       # some tables = 0.1
        )

        assert score == 0.6  # 0.3 + 0.1 + 0.1 + 0.1

    def test_low_quality_score(self):
        """Test low quality score (<0.5) with poor document."""
        score = calculate_quality_score(
            text_length=200,    # >100 = 0.2
            element_count=8,    # >5 = 0.1
            heading_count=1,    # >=1 = 0.05
            tables=[]           # no tables = 0.0
        )

        assert abs(score - 0.35) < 0.001  # 0.2 + 0.1 + 0.05 + 0.0

    def test_minimum_score_empty_document(self):
        """Test minimum score (0.0) for empty document."""
        score = calculate_quality_score(
            text_length=0,
            element_count=0,
            heading_count=0,
            tables=[]
        )

        assert score == 0.0

    def test_text_length_thresholds(self):
        """Test text length scoring thresholds."""
        # >1000 chars = 0.4
        score_high = calculate_quality_score(1500, 0, 0, [])
        assert score_high == 0.4

        # >500 chars = 0.3
        score_mid = calculate_quality_score(700, 0, 0, [])
        assert score_mid == 0.3

        # >100 chars = 0.2
        score_low = calculate_quality_score(200, 0, 0, [])
        assert score_low == 0.2

        # <=100 chars = 0.0
        score_min = calculate_quality_score(50, 0, 0, [])
        assert score_min == 0.0

    def test_element_count_thresholds(self):
        """Test element count scoring thresholds."""
        # >50 elements = 0.3
        score_high = calculate_quality_score(0, 60, 0, [])
        assert score_high == 0.3

        # >20 elements = 0.2
        score_mid = calculate_quality_score(0, 30, 0, [])
        assert score_mid == 0.2

        # >5 elements = 0.1
        score_low = calculate_quality_score(0, 10, 0, [])
        assert score_low == 0.1

        # <=5 elements = 0.0
        score_min = calculate_quality_score(0, 3, 0, [])
        assert score_min == 0.0

    def test_heading_count_thresholds(self):
        """Test heading count scoring thresholds."""
        # >=5 headings = 0.15
        score_high = calculate_quality_score(0, 0, 5, [])
        assert score_high == 0.15

        # >=3 headings = 0.1
        score_mid = calculate_quality_score(0, 0, 3, [])
        assert score_mid == 0.1

        # >=1 heading = 0.05
        score_low = calculate_quality_score(0, 0, 1, [])
        assert score_low == 0.05

        # 0 headings = 0.0
        score_min = calculate_quality_score(0, 0, 0, [])
        assert score_min == 0.0

    def test_table_scoring_valid_tables(self):
        """Test table scoring with valid tables (>3 rows)."""
        valid_tables = [
            {"data": [{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}]},
            {"data": [{"b": 5}, {"b": 6}, {"b": 7}, {"b": 8}, {"b": 9}]}
        ]

        score = calculate_quality_score(0, 0, 0, valid_tables)
        assert score == 0.15

    def test_table_scoring_small_tables(self):
        """Test table scoring with small tables (<=3 rows)."""
        small_tables = [
            {"data": [{"a": 1}]},
            {"data": [{"b": 2}, {"b": 3}]}
        ]

        score = calculate_quality_score(0, 0, 0, small_tables)
        assert score == 0.1

    def test_table_scoring_no_tables(self):
        """Test table scoring with no tables."""
        score = calculate_quality_score(0, 0, 0, [])
        assert score == 0.0

    def test_table_scoring_mixed_tables(self):
        """Test table scoring with mix of valid and small tables."""
        mixed_tables = [
            {"data": [{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}]},  # Valid (>3 rows)
            {"data": [{"b": 1}, {"b": 2}]}                        # Small (<=3 rows)
        ]

        # Should get 0.15 because at least one valid table exists
        score = calculate_quality_score(0, 0, 0, mixed_tables)
        assert score == 0.15

    def test_score_capped_at_one(self):
        """Test that score is capped at 1.0 even with excessive values."""
        # Hypothetically exceed 1.0 if not capped
        score = calculate_quality_score(
            text_length=10000,
            element_count=1000,
            heading_count=100,
            tables=[{"data": [{"a": i} for i in range(10)]}] * 10
        )

        assert score == 1.0

    def test_boundary_values(self):
        """Test exact boundary values for all thresholds."""
        # Exactly at boundaries
        assert calculate_quality_score(1000, 0, 0, []) == 0.3  # Just below >1000
        assert calculate_quality_score(1001, 0, 0, []) == 0.4  # Just above >1000

        assert calculate_quality_score(0, 50, 0, []) == 0.2   # Just below >50
        assert calculate_quality_score(0, 51, 0, []) == 0.3   # Just above >50

        assert calculate_quality_score(0, 0, 4, []) == 0.1    # Just below >=5
        assert calculate_quality_score(0, 0, 5, []) == 0.15   # Exactly >=5

    def test_realistic_low_quality_pdf(self):
        """Test quality score for realistic low-quality scanned PDF."""
        # Simulates OCR extraction with poor structure
        score = calculate_quality_score(
            text_length=300,     # Some text extracted
            element_count=3,     # Very few elements
            heading_count=0,     # No headings detected
            tables=[]            # No tables
        )

        assert score == 0.2  # Only gets text score
        assert score < 0.7   # Should trigger Vision fallback

    def test_realistic_high_quality_pdf(self):
        """Test quality score for realistic high-quality academic PDF."""
        # Simulates well-structured academic paper
        tables = [
            {"data": [{"metric": f"value{i}"} for i in range(5)]}
            for _ in range(3)
        ]

        score = calculate_quality_score(
            text_length=5000,    # Substantial content
            element_count=120,   # Many elements
            heading_count=8,     # Good heading structure
            tables=tables        # Multiple valid tables
        )

        assert score == 1.0   # Maximum score
        assert score >= 0.7   # Should use hybrid mode
