"""Tests for extraction result Pydantic models."""

import pytest
from pydantic import ValidationError

from app.models.extraction import (
    BoundingBox,
    ExtractedMetadata,
    ExtractedSection,
    ExtractedTable,
    ExtractedReference,
    DocumentStructure,
    ExtractionResult,
)


class TestBoundingBox:
    """Tests for BoundingBox model."""

    def test_valid_bounding_box(self):
        """Test creating valid bounding box."""
        bbox = BoundingBox(x1=10.0, y1=20.0, x2=100.0, y2=200.0, page=1)
        assert bbox.x1 == 10.0
        assert bbox.y1 == 20.0
        assert bbox.x2 == 100.0
        assert bbox.y2 == 200.0
        assert bbox.page == 1

    def test_page_number_must_be_positive(self):
        """Test that page number must be >= 1."""
        with pytest.raises(ValidationError) as exc_info:
            BoundingBox(x1=10.0, y1=20.0, x2=100.0, y2=200.0, page=0)

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('page',) for e in errors)

    def test_negative_page_number_invalid(self):
        """Test that negative page numbers are invalid."""
        with pytest.raises(ValidationError):
            BoundingBox(x1=10.0, y1=20.0, x2=100.0, y2=200.0, page=-1)


class TestExtractedMetadata:
    """Tests for ExtractedMetadata model."""

    def test_minimal_metadata(self):
        """Test creating metadata with only required field (title)."""
        metadata = ExtractedMetadata(title="Test Paper")
        assert metadata.title == "Test Paper"
        assert metadata.authors == []
        assert metadata.journal is None
        assert metadata.year is None
        assert metadata.doi is None

    def test_complete_metadata(self):
        """Test creating metadata with all fields."""
        metadata = ExtractedMetadata(
            title="Machine Learning Paper",
            authors=["Alice Smith", "Bob Jones"],
            journal="Nature",
            year=2023,
            doi="10.1000/nature.2023.12345"
        )
        assert metadata.title == "Machine Learning Paper"
        assert len(metadata.authors) == 2
        assert metadata.journal == "Nature"
        assert metadata.year == 2023
        assert metadata.doi == "10.1000/nature.2023.12345"

    def test_year_validation_too_early(self):
        """Test that years before 1900 are invalid."""
        with pytest.raises(ValidationError) as exc_info:
            ExtractedMetadata(title="Test", year=1800)

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('year',) for e in errors)

    def test_year_validation_too_late(self):
        """Test that years after 2100 are invalid."""
        with pytest.raises(ValidationError):
            ExtractedMetadata(title="Test", year=2150)


class TestExtractedSection:
    """Tests for ExtractedSection model."""

    def test_section_without_bbox(self):
        """Test creating section without bounding box."""
        section = ExtractedSection(
            heading="Introduction",
            content="This is the introduction...",
            page_number=1
        )
        assert section.heading == "Introduction"
        assert section.content == "This is the introduction..."
        assert section.page_number == 1
        assert section.bbox is None

    def test_section_with_bbox(self):
        """Test creating section with bounding box."""
        bbox = BoundingBox(x1=50.0, y1=600.0, x2=500.0, y2=650.0, page=1)
        section = ExtractedSection(
            heading="Methods",
            content="Our methodology...",
            page_number=2,
            bbox=bbox
        )
        assert section.bbox is not None
        assert section.bbox.page == 1


class TestExtractedTable:
    """Tests for ExtractedTable model."""

    def test_minimal_table(self):
        """Test creating table with minimal data."""
        table = ExtractedTable(page_number=3)
        assert table.caption == ""
        assert table.page_number == 3
        assert table.data == []
        assert table.bbox is None

    def test_table_with_data(self):
        """Test creating table with data and caption."""
        table_data = [
            {"col1": "value1", "col2": "value2"},
            {"col1": "value3", "col2": "value4"}
        ]
        table = ExtractedTable(
            caption="Table 1: Experimental Results",
            page_number=5,
            data=table_data
        )
        assert table.caption == "Table 1: Experimental Results"
        assert len(table.data) == 2
        assert table.data[0]["col1"] == "value1"


class TestExtractedReference:
    """Tests for ExtractedReference model."""

    def test_minimal_reference(self):
        """Test creating reference with only citation text."""
        ref = ExtractedReference(citation_text="Smith et al. (2020). Nature.")
        assert ref.citation_text == "Smith et al. (2020). Nature."
        assert ref.authors == []
        assert ref.year is None
        assert ref.title is None

    def test_complete_reference(self):
        """Test creating reference with all fields parsed."""
        ref = ExtractedReference(
            citation_text="Smith, A., Jones, B. (2020). ML Paper. Nature, 123, 45-67.",
            authors=["Smith, A.", "Jones, B."],
            year=2020,
            title="ML Paper"
        )
        assert len(ref.authors) == 2
        assert ref.year == 2020
        assert ref.title == "ML Paper"


class TestDocumentStructure:
    """Tests for DocumentStructure model."""

    def test_minimal_document_structure(self):
        """Test creating minimal document structure."""
        doc = DocumentStructure(
            markdown="# Test\n\nContent",
            quality_score=0.85,
            element_count=10
        )
        assert doc.markdown == "# Test\n\nContent"
        assert doc.quality_score == 0.85
        assert doc.element_count == 10
        assert doc.tables == []
        assert doc.bounding_boxes == {}

    def test_quality_score_bounds(self):
        """Test that quality score is bounded between 0 and 1."""
        with pytest.raises(ValidationError):
            DocumentStructure(
                markdown="Test",
                quality_score=1.5,  # Too high
                element_count=10
            )

        with pytest.raises(ValidationError):
            DocumentStructure(
                markdown="Test",
                quality_score=-0.1,  # Too low
                element_count=10
            )

    def test_document_structure_with_data(self):
        """Test creating document structure with tables and bboxes."""
        bbox1 = BoundingBox(x1=10.0, y1=20.0, x2=100.0, y2=200.0, page=1)
        doc = DocumentStructure(
            markdown="# Paper\n\nContent...",
            tables=[{"caption": "Table 1", "data": []}],
            bounding_boxes={"heading_1": bbox1},
            quality_score=0.92,
            element_count=45
        )
        assert len(doc.tables) == 1
        assert len(doc.bounding_boxes) == 1
        assert "heading_1" in doc.bounding_boxes


class TestExtractionResult:
    """Tests for ExtractionResult model."""

    def test_minimal_extraction_result(self):
        """Test creating minimal extraction result."""
        metadata = ExtractedMetadata(title="Test Paper")
        result = ExtractionResult(
            metadata=metadata,
            confidence_score=0.9
        )
        assert result.metadata.title == "Test Paper"
        assert result.confidence_score == 0.9
        assert result.abstract is None
        assert result.sections == []
        assert result.tables == []
        assert result.references == []
        assert result.bounding_boxes == {}
        assert result.processing_metadata == {}

    def test_complete_extraction_result(self):
        """Test creating complete extraction result with all fields."""
        metadata = ExtractedMetadata(
            title="Complete Paper",
            authors=["Author One", "Author Two"],
            journal="Test Journal",
            year=2024
        )

        section = ExtractedSection(
            heading="Introduction",
            content="Introduction text...",
            page_number=1
        )

        table = ExtractedTable(
            caption="Table 1",
            page_number=3,
            data=[{"col": "val"}]
        )

        reference = ExtractedReference(
            citation_text="Test citation",
            authors=["Smith, J."],
            year=2023
        )

        bbox = BoundingBox(x1=10.0, y1=20.0, x2=100.0, y2=200.0, page=1)

        result = ExtractionResult(
            metadata=metadata,
            abstract="This is the abstract...",
            sections=[section],
            tables=[table],
            references=[reference],
            confidence_score=0.95,
            bounding_boxes={"title": bbox},
            processing_metadata={
                "method": "hybrid",
                "quality_score": 0.92,
                "cost_savings_percent": 80
            }
        )

        assert result.metadata.title == "Complete Paper"
        assert result.abstract == "This is the abstract..."
        assert len(result.sections) == 1
        assert len(result.tables) == 1
        assert len(result.references) == 1
        assert result.confidence_score == 0.95
        assert "title" in result.bounding_boxes
        assert result.processing_metadata["method"] == "hybrid"

    def test_confidence_score_validation(self):
        """Test that confidence score is bounded between 0 and 1."""
        metadata = ExtractedMetadata(title="Test")

        with pytest.raises(ValidationError):
            ExtractionResult(metadata=metadata, confidence_score=1.1)

        with pytest.raises(ValidationError):
            ExtractionResult(metadata=metadata, confidence_score=-0.5)

    def test_valid_confidence_scores(self):
        """Test that valid confidence scores are accepted."""
        metadata = ExtractedMetadata(title="Test")

        result_low = ExtractionResult(metadata=metadata, confidence_score=0.0)
        assert result_low.confidence_score == 0.0

        result_high = ExtractionResult(metadata=metadata, confidence_score=1.0)
        assert result_high.confidence_score == 1.0

        result_mid = ExtractionResult(metadata=metadata, confidence_score=0.75)
        assert result_mid.confidence_score == 0.75
