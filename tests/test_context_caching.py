"""Tests for context caching functionality."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from google import genai
from google.genai import types

from app.services import pdf_extractor
from app.models.extraction import ExtractionResult, ExtractedMetadata


class TestContextCaching:
    """Test context caching implementation."""

    def test_get_or_create_cache_creates_new_cache(self) -> None:
        """Test that get_or_create_cache creates a new cache on first call."""
        # Reset global cache
        pdf_extractor._EXTRACTION_CACHE_NAME = None

        # Mock Gemini client
        mock_client = MagicMock(spec=genai.Client)
        mock_cache = MagicMock()
        mock_cache.name = "cache_12345"
        mock_client.caches.create.return_value = mock_cache

        # Call function
        cache_name = pdf_extractor.get_or_create_cache(mock_client, "gemini-3-flash-preview")

        # Verify cache was created
        assert cache_name == "cache_12345"
        mock_client.caches.create.assert_called_once()

        # Verify cache config
        call_args = mock_client.caches.create.call_args
        assert call_args[1]["model"] == "gemini-3-flash-preview"
        config = call_args[1]["config"]
        assert isinstance(config, types.CreateCachedContentConfig)
        assert config.display_name == "academic_pdf_extraction"
        assert config.ttl == "3600s"
        assert pdf_extractor.ACADEMIC_EXTRACTION_SYSTEM_INSTRUCTION in config.system_instruction

    def test_get_or_create_cache_reuses_existing_cache(self) -> None:
        """Test that get_or_create_cache reuses existing cache when available."""
        # Set global cache
        pdf_extractor._EXTRACTION_CACHE_NAME = "cache_existing"

        # Mock Gemini client
        mock_client = MagicMock(spec=genai.Client)
        mock_client.caches.get.return_value = MagicMock()  # Cache exists

        # Call function
        cache_name = pdf_extractor.get_or_create_cache(mock_client)

        # Verify existing cache was reused
        assert cache_name == "cache_existing"
        mock_client.caches.get.assert_called_once_with(name="cache_existing")
        mock_client.caches.create.assert_not_called()

    def test_get_or_create_cache_recreates_expired_cache(self) -> None:
        """Test that get_or_create_cache recreates cache if it expired."""
        # Set global cache
        pdf_extractor._EXTRACTION_CACHE_NAME = "cache_expired"

        # Mock Gemini client
        mock_client = MagicMock(spec=genai.Client)
        mock_client.caches.get.side_effect = Exception("Cache not found")

        mock_cache = MagicMock()
        mock_cache.name = "cache_new"
        mock_client.caches.create.return_value = mock_cache

        # Call function
        cache_name = pdf_extractor.get_or_create_cache(mock_client)

        # Verify cache was recreated
        assert cache_name == "cache_new"
        mock_client.caches.get.assert_called_once()
        mock_client.caches.create.assert_called_once()

    def test_extract_with_vision_fallback_uses_cache(self) -> None:
        """Test that extract_with_vision_fallback uses context caching."""
        # Reset global cache
        pdf_extractor._EXTRACTION_CACHE_NAME = None

        # Mock Gemini client
        mock_client = MagicMock(spec=genai.Client)

        # Mock cache creation
        mock_cache = MagicMock()
        mock_cache.name = "cache_vision"
        mock_client.caches.create.return_value = mock_cache

        # Mock file upload
        mock_uploaded_file = MagicMock()
        mock_uploaded_file.name = "file_123"
        mock_client.files.upload.return_value = mock_uploaded_file

        # Mock generate_content response
        mock_response = MagicMock()
        mock_result = ExtractionResult(
            metadata=ExtractedMetadata(title="Test Paper"),
            confidence_score=0.9
        )
        mock_response.parsed = mock_result

        # Mock usage metadata with cache statistics
        mock_usage = MagicMock()
        mock_usage.cached_content_token_count = 500
        mock_usage.total_token_count = 1000
        type(mock_response).usage_metadata = PropertyMock(return_value=mock_usage)

        mock_client.models.generate_content.return_value = mock_response

        # Call function
        with patch('os.path.exists', return_value=True):
            result = pdf_extractor.extract_with_vision_fallback(
                mock_client,
                "test.pdf"
            )

        # Verify cache was created
        mock_client.caches.create.assert_called_once()

        # Verify generate_content was called with cache
        call_args = mock_client.models.generate_content.call_args
        config = call_args[1]["config"]
        assert config.cached_content == "cache_vision"

        # Verify result includes cache statistics
        assert result.processing_metadata["cache_hit"] is True
        assert result.processing_metadata["cached_tokens"] == 500
        assert result.processing_metadata["cached_tokens_saved"] == 500

    @pytest.mark.asyncio
    async def test_extract_pdf_data_hybrid_uses_cache(self) -> None:
        """Test that extract_pdf_data_hybrid uses context caching."""
        # Reset global cache
        pdf_extractor._EXTRACTION_CACHE_NAME = None

        # Mock Gemini client
        mock_client = MagicMock(spec=genai.Client)

        # Mock cache creation
        mock_cache = MagicMock()
        mock_cache.name = "cache_hybrid"
        mock_client.caches.create.return_value = mock_cache

        # Mock OpenDataLoader extraction
        from app.models.extraction import DocumentStructure
        mock_doc_structure = DocumentStructure(
            markdown="# Test Paper\n\nContent here.",
            tables=[],
            bounding_boxes={},
            quality_score=0.85,  # Above 0.7 threshold
            element_count=10
        )

        # Mock generate_content response
        mock_response = MagicMock()
        mock_result = ExtractionResult(
            metadata=ExtractedMetadata(title="Test Paper"),
            confidence_score=0.9
        )
        mock_response.parsed = mock_result

        # Mock usage metadata with cache statistics
        mock_usage = MagicMock()
        mock_usage.cached_content_token_count = 300
        mock_usage.total_token_count = 800
        type(mock_response).usage_metadata = PropertyMock(return_value=mock_usage)

        mock_client.models.generate_content.return_value = mock_response

        # Mock extract_pdf_structure
        with patch('app.services.pdf_extractor.extract_pdf_structure', return_value=mock_doc_structure):
            result = await pdf_extractor.extract_pdf_data_hybrid(
                mock_client,
                "test.pdf"
            )

        # Verify cache was created
        mock_client.caches.create.assert_called_once()

        # Verify generate_content was called with cache
        call_args = mock_client.models.generate_content.call_args
        config = call_args[1]["config"]
        assert config.cached_content == "cache_hybrid"

        # Verify result includes cache statistics
        assert result.processing_metadata["method"] == "hybrid"
        assert result.processing_metadata["cache_hit"] is True
        assert result.processing_metadata["cached_tokens"] == 300
        assert result.processing_metadata["cached_tokens_saved"] == 300
        assert result.processing_metadata["total_tokens"] == 800

    @pytest.mark.asyncio
    async def test_extract_pdf_data_hybrid_cache_miss(self) -> None:
        """Test cache statistics when cache is not hit."""
        # Reset global cache
        pdf_extractor._EXTRACTION_CACHE_NAME = None

        # Mock Gemini client
        mock_client = MagicMock(spec=genai.Client)

        # Mock cache creation
        mock_cache = MagicMock()
        mock_cache.name = "cache_hybrid"
        mock_client.caches.create.return_value = mock_cache

        # Mock OpenDataLoader extraction
        from app.models.extraction import DocumentStructure
        mock_doc_structure = DocumentStructure(
            markdown="# Test Paper\n\nContent here.",
            tables=[],
            bounding_boxes={},
            quality_score=0.85,
            element_count=10
        )

        # Mock generate_content response WITHOUT cache hit
        mock_response = MagicMock()
        mock_result = ExtractionResult(
            metadata=ExtractedMetadata(title="Test Paper"),
            confidence_score=0.9
        )
        mock_response.parsed = mock_result

        # Mock usage metadata WITHOUT cached tokens
        mock_usage = MagicMock()
        mock_usage.cached_content_token_count = 0  # No cache hit
        mock_usage.total_token_count = 800
        type(mock_response).usage_metadata = PropertyMock(return_value=mock_usage)

        mock_client.models.generate_content.return_value = mock_response

        # Mock extract_pdf_structure
        with patch('app.services.pdf_extractor.extract_pdf_structure', return_value=mock_doc_structure):
            result = await pdf_extractor.extract_pdf_data_hybrid(
                mock_client,
                "test.pdf"
            )

        # Verify result shows cache miss
        assert result.processing_metadata["cache_hit"] is False
        assert result.processing_metadata["cached_tokens"] == 0
        assert result.processing_metadata["cached_tokens_saved"] == 0
        assert result.processing_metadata["total_tokens"] == 800
