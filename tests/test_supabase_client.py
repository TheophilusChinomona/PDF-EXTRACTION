"""Tests for Supabase client initialization."""

import os
import pytest
from unittest.mock import patch, MagicMock
from pydantic import ValidationError

from app.db.supabase_client import get_supabase_client
from app.config import get_settings


@pytest.fixture(autouse=True)
def setup_env():
    """Set up test environment variables."""
    # Clear settings cache before each test
    get_settings.cache_clear()

    # Set required environment variables
    os.environ["GEMINI_API_KEY"] = "test-gemini-key"
    os.environ["SUPABASE_URL"] = "https://test-project.supabase.co"
    os.environ["SUPABASE_KEY"] = "test-supabase-key"

    yield

    # Clean up after test
    get_settings.cache_clear()


class TestGetSupabaseClient:
    """Tests for get_supabase_client function."""

    @patch("app.db.supabase_client.create_client")
    def test_successful_client_creation(self, mock_create_client):
        """Test successful Supabase client creation with valid credentials."""
        # Arrange
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        # Act
        client = get_supabase_client()

        # Assert
        assert client is mock_client
        mock_create_client.assert_called_once_with(
            "https://test-project.supabase.co",
            "test-supabase-key"
        )

    @patch("app.db.supabase_client.create_client")
    def test_client_creation_with_custom_url(self, mock_create_client):
        """Test client creation with custom Supabase URL."""
        # Arrange
        get_settings.cache_clear()
        os.environ["SUPABASE_URL"] = "https://custom-project.supabase.co"
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        # Act
        client = get_supabase_client()

        # Assert
        assert client is mock_client
        mock_create_client.assert_called_once_with(
            "https://custom-project.supabase.co",
            "test-supabase-key"
        )

    def test_missing_supabase_url(self):
        """Test that missing SUPABASE_URL raises ValidationError."""
        # Arrange
        get_settings.cache_clear()
        del os.environ["SUPABASE_URL"]

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            get_supabase_client()

        # Verify the error mentions SUPABASE_URL
        assert "supabase_url" in str(exc_info.value).lower()

    def test_missing_supabase_key(self):
        """Test that missing SUPABASE_KEY raises ValidationError."""
        # Arrange
        get_settings.cache_clear()
        del os.environ["SUPABASE_KEY"]

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            get_supabase_client()

        # Verify the error mentions SUPABASE_KEY
        assert "supabase_key" in str(exc_info.value).lower()

    def test_empty_supabase_url(self):
        """Test that empty SUPABASE_URL raises ValidationError."""
        # Arrange
        get_settings.cache_clear()
        os.environ["SUPABASE_URL"] = ""

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            get_supabase_client()

        assert "supabase_url" in str(exc_info.value).lower()

    def test_empty_supabase_key(self):
        """Test that empty SUPABASE_KEY raises ValidationError."""
        # Arrange
        get_settings.cache_clear()
        os.environ["SUPABASE_KEY"] = ""

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            get_supabase_client()

        assert "supabase_key" in str(exc_info.value).lower()

    def test_whitespace_only_supabase_url(self):
        """Test that whitespace-only SUPABASE_URL raises ValidationError."""
        # Arrange
        get_settings.cache_clear()
        os.environ["SUPABASE_URL"] = "   "

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            get_supabase_client()

        assert "supabase_url" in str(exc_info.value).lower()

    def test_whitespace_only_supabase_key(self):
        """Test that whitespace-only SUPABASE_KEY raises ValidationError."""
        # Arrange
        get_settings.cache_clear()
        os.environ["SUPABASE_KEY"] = "   "

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            get_supabase_client()

        assert "supabase_key" in str(exc_info.value).lower()

    def test_invalid_supabase_url_not_https(self):
        """Test that non-HTTPS SUPABASE_URL raises ValidationError."""
        # Arrange
        get_settings.cache_clear()
        os.environ["SUPABASE_URL"] = "http://test-project.supabase.co"

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            get_supabase_client()

        # Verify the error mentions HTTPS requirement
        error_str = str(exc_info.value).lower()
        assert "https" in error_str

    @patch("app.db.supabase_client.create_client")
    def test_create_client_raises_exception(self, mock_create_client):
        """Test that create_client exceptions are wrapped with clear message."""
        # Arrange
        mock_create_client.side_effect = Exception("Connection failed")

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            get_supabase_client()

        assert "Failed to create Supabase client" in str(exc_info.value)
        assert "Connection failed" in str(exc_info.value)

    @patch("app.db.supabase_client.create_client")
    def test_client_return_type(self, mock_create_client):
        """Test that get_supabase_client returns the client object."""
        # Arrange
        mock_client = MagicMock()
        mock_client.table = MagicMock()
        mock_create_client.return_value = mock_client

        # Act
        client = get_supabase_client()

        # Assert
        assert hasattr(client, "table")
        assert callable(client.table)
