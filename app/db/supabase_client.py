"""
Supabase client initialization module.

This module provides a thread-safe singleton Supabase client for database operations.
When SUPABASE_SERVICE_ROLE_KEY is set, the client uses it to bypass RLS so that
batch scripts and backend services can see all rows.  Falls back to the anon key.
"""

import threading
from supabase import create_client, Client
from app.config import get_settings

_client: Client | None = None
_lock = threading.Lock()


def get_supabase_client() -> Client:
    """
    Return the shared Supabase client (singleton), initializing once in a thread-safe way.

    Prefers ``supabase_service_role_key`` (bypasses RLS) when available,
    otherwise falls back to ``supabase_key`` (anon key).

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
        # Prefer service role key (bypasses RLS) when available
        key = settings.supabase_service_role_key or settings.supabase_key
        try:
            _client = create_client(url, key)
            return _client
        except Exception as e:
            raise ValueError(f"Failed to create Supabase client: {str(e)}") from e
