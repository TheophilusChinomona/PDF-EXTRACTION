"""Tests for Gemini API client initialization."""

import pytest
from unittest.mock import patch, MagicMock
from pydantic import ValidationError

from app.services.gemini_client import get_gemini_client


class TestGeminiClient:
    """Test suite for Gemini client initialization."""

    def test_get_gemini_client_success(self, mock_env_vars):
        """Test successful Gemini client initialization with valid API key."""
        with patch('app.services.gemini_client.genai.Client') as mock_client:
            mock_client_instance = MagicMock()
            mock_client.return_value = mock_client_instance

            client = get_gemini_client()

            # Verify Client was called with API key
            mock_client.assert_called_once_with(api_key='test-gemini-api-key')
            assert client == mock_client_instance

    def test_get_gemini_client_missing_api_key(self, monkeypatch):
        """Test that ValidationError is raised when GEMINI_API_KEY is not set."""
        # Clear the lru_cache from settings to force re-validation
        from app.config import get_settings
        get_settings.cache_clear()

        # Remove GEMINI_API_KEY
        monkeypatch.delenv('GEMINI_API_KEY', raising=False)
        monkeypatch.delenv('SUPABASE_URL', raising=False)
        monkeypatch.delenv('SUPABASE_KEY', raising=False)

        # Should raise ValidationError during settings validation (Pydantic v2)
        with pytest.raises(ValidationError) as exc_info:
            get_gemini_client()

        # Check that gemini_api_key is mentioned in the validation error
        assert 'gemini_api_key' in str(exc_info.value)

    def test_get_gemini_client_empty_api_key(self, monkeypatch):
        """Test that ValueError is raised when GEMINI_API_KEY is empty."""
        from app.config import get_settings
        get_settings.cache_clear()

        monkeypatch.setenv('GEMINI_API_KEY', '')
        monkeypatch.setenv('SUPABASE_URL', 'https://test.supabase.co')
        monkeypatch.setenv('SUPABASE_KEY', 'test-key')

        # Should raise ValueError during settings validation
        with pytest.raises(ValueError) as exc_info:
            get_gemini_client()

        assert 'GEMINI_API_KEY' in str(exc_info.value)

    def test_get_gemini_client_whitespace_only_api_key(self, monkeypatch):
        """Test that ValueError is raised when GEMINI_API_KEY is whitespace only."""
        from app.config import get_settings
        get_settings.cache_clear()

        monkeypatch.setenv('GEMINI_API_KEY', '   ')
        monkeypatch.setenv('SUPABASE_URL', 'https://test.supabase.co')
        monkeypatch.setenv('SUPABASE_KEY', 'test-key')

        # Should raise ValueError during settings validation
        with pytest.raises(ValueError) as exc_info:
            get_gemini_client()

        assert 'GEMINI_API_KEY' in str(exc_info.value)

    def test_get_gemini_client_returns_client_instance(self, mock_env_vars):
        """Test that get_gemini_client returns a genai.Client instance."""
        with patch('app.services.gemini_client.genai.Client') as mock_client:
            mock_client_instance = MagicMock()
            mock_client.return_value = mock_client_instance

            client = get_gemini_client()

            # Verify the returned client is what the mock returned
            assert client == mock_client_instance


# Pytest fixtures
@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up mock environment variables for testing."""
    from app.config import get_settings
    get_settings.cache_clear()

    monkeypatch.setenv('GEMINI_API_KEY', 'test-gemini-api-key')
    monkeypatch.setenv('SUPABASE_URL', 'https://test.supabase.co')
    monkeypatch.setenv('SUPABASE_KEY', 'test-supabase-key')
