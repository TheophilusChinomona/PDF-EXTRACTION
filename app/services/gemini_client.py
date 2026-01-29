"""Gemini API client initialization with error handling.

This module provides a singleton Gemini client for the application.
Uses the modern google-genai SDK (not google.generativeai).
"""

from google import genai
from app.config import get_settings


def get_gemini_client() -> genai.Client:
    """Initialize and return a Gemini API client.

    The client reads the GEMINI_API_KEY from the application settings.
    Settings validation ensures the API key is present at startup.

    Returns:
        genai.Client: Initialized Gemini client ready for API calls.

    Raises:
        ValueError: If GEMINI_API_KEY is not set in environment.

    Example:
        >>> client = get_gemini_client()
        >>> response = client.models.generate_content(
        ...     model="gemini-3-flash-preview",
        ...     contents=["Hello world"]
        ... )
    """
    settings = get_settings()

    # Settings validation already ensures API key is present
    # This check is redundant but provides a clearer error message
    if not settings.gemini_api_key:
        raise ValueError(
            "GEMINI_API_KEY not set in environment. "
            "Please set this variable in your .env file or environment."
        )

    # Initialize client with API key from settings
    # The genai.Client() automatically uses GEMINI_API_KEY from environment
    return genai.Client(api_key=settings.gemini_api_key)
