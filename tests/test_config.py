"""Tests for configuration management."""

import os
import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


class TestSettings:
    """Test Settings class validation and loading."""

    def test_settings_with_valid_env_vars(self, monkeypatch):
        """Test that Settings loads successfully with valid environment variables."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key-123")
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-supabase-key")

        settings = Settings()

        assert settings.gemini_api_key == "test-api-key-123"
        assert settings.supabase_url == "https://test.supabase.co"
        assert settings.supabase_key == "test-supabase-key"
        assert settings.model_name == "gemini-3-flash-preview"  # default
        assert settings.enable_hybrid_mode is True  # default

    def test_settings_with_custom_model_name(self, monkeypatch):
        """Test that custom model name can be set."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")
        monkeypatch.setenv("MODEL_NAME", "gemini-3-pro-preview")

        settings = Settings()

        assert settings.model_name == "gemini-3-pro-preview"

    def test_settings_with_hybrid_mode_disabled(self, monkeypatch):
        """Test that hybrid mode can be disabled."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")
        monkeypatch.setenv("ENABLE_HYBRID_MODE", "false")

        settings = Settings()

        assert settings.enable_hybrid_mode is False

    def test_missing_gemini_api_key_raises_error(self, monkeypatch):
        """Test that missing GEMINI_API_KEY raises ValidationError."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "gemini_api_key" in str(exc_info.value).lower()

    def test_empty_gemini_api_key_raises_error(self, monkeypatch):
        """Test that empty GEMINI_API_KEY raises ValidationError."""
        monkeypatch.setenv("GEMINI_API_KEY", "")
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "GEMINI_API_KEY must be set" in str(exc_info.value)

    def test_whitespace_only_gemini_api_key_raises_error(self, monkeypatch):
        """Test that whitespace-only GEMINI_API_KEY raises ValidationError."""
        monkeypatch.setenv("GEMINI_API_KEY", "   ")
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "GEMINI_API_KEY must be set" in str(exc_info.value)

    def test_missing_supabase_url_raises_error(self, monkeypatch):
        """Test that missing SUPABASE_URL raises ValidationError."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.setenv("SUPABASE_KEY", "test-key")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "supabase_url" in str(exc_info.value).lower()

    def test_invalid_supabase_url_raises_error(self, monkeypatch):
        """Test that non-HTTPS SUPABASE_URL raises ValidationError."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        monkeypatch.setenv("SUPABASE_URL", "http://test.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "must start with https://" in str(exc_info.value)

    def test_missing_supabase_key_raises_error(self, monkeypatch):
        """Test that missing SUPABASE_KEY raises ValidationError."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.delenv("SUPABASE_KEY", raising=False)

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "supabase_key" in str(exc_info.value).lower()

    def test_settings_strips_whitespace_from_keys(self, monkeypatch):
        """Test that Settings strips leading/trailing whitespace from keys."""
        monkeypatch.setenv("GEMINI_API_KEY", "  test-api-key  ")
        monkeypatch.setenv("SUPABASE_URL", "  https://test.supabase.co  ")
        monkeypatch.setenv("SUPABASE_KEY", "  test-key  ")

        settings = Settings()

        assert settings.gemini_api_key == "test-api-key"
        assert settings.supabase_url == "https://test.supabase.co"
        assert settings.supabase_key == "test-key"


class TestGetSettings:
    """Test get_settings() function caching behavior."""

    def test_get_settings_returns_settings_instance(self, monkeypatch):
        """Test that get_settings() returns a Settings instance."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")

        # Clear the cache before testing
        get_settings.cache_clear()

        settings = get_settings()

        assert isinstance(settings, Settings)
        assert settings.gemini_api_key == "test-api-key"

    def test_get_settings_caches_result(self, monkeypatch):
        """Test that get_settings() caches the Settings instance."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")

        # Clear the cache before testing
        get_settings.cache_clear()

        settings1 = get_settings()
        settings2 = get_settings()

        # Should be the exact same object due to caching
        assert settings1 is settings2

    def test_get_settings_raises_error_on_invalid_config(self, monkeypatch):
        """Test that get_settings() raises ValidationError on invalid config."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")

        # Clear the cache before testing
        get_settings.cache_clear()

        with pytest.raises(ValidationError):
            get_settings()
