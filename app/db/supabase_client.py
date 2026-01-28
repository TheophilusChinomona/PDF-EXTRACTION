"""
Supabase client initialization module.

This module provides a function to initialize and return a Supabase client
for database operations.
"""

from supabase import create_client, Client
from app.config import get_settings


def get_supabase_client() -> Client:
    """
    Initialize and return a Supabase client.

    Loads credentials from Settings and creates a client instance.

    Returns:
        Client: Initialized Supabase client

    Raises:
        ValueError: If SUPABASE_URL or SUPABASE_KEY are missing or invalid
    """
    settings = get_settings()

    # Credentials are validated by Settings model
    # If we reach here, they are present and valid
    url = settings.supabase_url
    key = settings.supabase_key

    try:
        client = create_client(url, key)
        return client
    except Exception as e:
        raise ValueError(f"Failed to create Supabase client: {str(e)}") from e
