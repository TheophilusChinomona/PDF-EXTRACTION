"""Configuration management for PDF-Extraction service.

This module uses Pydantic Settings to load configuration from environment
variables. All settings are validated at startup to catch configuration
errors early.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All sensitive values (API keys, database credentials) must be
    provided via environment variables or .env file.
    """

    # Gemini API Configuration
    gemini_api_key: str = Field(
        ...,
        description="Google Gemini API key for document processing"
    )

    # Supabase Configuration
    supabase_url: str = Field(
        ...,
        description="Supabase project URL"
    )
    supabase_key: str = Field(
        ...,
        description="Supabase anonymous/service role key"
    )

    # AI Model Configuration
    model_name: str = Field(
        default="gemini-3-flash-preview",
        description="Gemini model to use for extraction"
    )

    # Feature Flags
    enable_hybrid_mode: bool = Field(
        default=True,
        description="Enable hybrid extraction (OpenDataLoader + Gemini)"
    )

    # Model configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @field_validator("gemini_api_key")
    @classmethod
    def validate_gemini_api_key(cls, v: str) -> str:
        """Validate that GEMINI_API_KEY is present and non-empty."""
        if not v or not v.strip():
            raise ValueError(
                "GEMINI_API_KEY must be set in environment variables. "
                "Get your API key from https://ai.google.dev/"
            )
        return v.strip()

    @field_validator("supabase_url")
    @classmethod
    def validate_supabase_url(cls, v: str) -> str:
        """Validate that Supabase URL is present and properly formatted."""
        if not v or not v.strip():
            raise ValueError("SUPABASE_URL must be set in environment variables")

        url = v.strip()
        if not url.startswith("https://"):
            raise ValueError(
                "SUPABASE_URL must start with https:// "
                f"(got: {url[:20]}...)"
            )

        return url

    @field_validator("supabase_key")
    @classmethod
    def validate_supabase_key(cls, v: str) -> str:
        """Validate that Supabase key is present and non-empty."""
        if not v or not v.strip():
            raise ValueError("SUPABASE_KEY must be set in environment variables")
        return v.strip()


@lru_cache
def get_settings() -> Settings:
    """Get cached Settings instance.

    This function uses lru_cache to ensure settings are loaded only once
    and reused across the application lifetime.

    Returns:
        Settings: Validated application settings

    Raises:
        ValueError: If required environment variables are missing or invalid
    """
    return Settings()
