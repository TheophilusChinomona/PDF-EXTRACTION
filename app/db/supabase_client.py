"""
Supabase client initialization module.

This module provides a thread-safe singleton Supabase client for database operations.
"""

import threading
from supabase import create_client, Client
from app.config import get_settings

_client: Client | None = None
_lock = threading.Lock()


def get_supabase_client() -> Client:
    """
    Return the shared Supabase client (singleton), initializing once in a thread-safe way.

    Loads credentials from Settings and creates a single client instance reused by all callers.

    Returns:
        Client: Shared Supabase client instance

    Raises:
        ValueError: If SUPABASE_URL or SUPABASE_KEY are missing or invalid
    """
    global _client
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:
            return _client
        settings = get_settings()
        url = settings.supabase_url
        key = settings.supabase_key
        try:
            _client = create_client(url, key)
            return _client
        except Exception as e:
            raise ValueError(f"Failed to create Supabase client: {str(e)}") from e
