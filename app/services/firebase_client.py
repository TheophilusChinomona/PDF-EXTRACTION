"""
Firebase Storage client for downloading PDFs (gs:// URLs) and rename operations.

Uses Google Cloud Storage client with service account auth. Supports streaming
download for large files. Copy + delete for rename.
"""

import io
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional, Tuple

from app.config import get_settings

logger = logging.getLogger(__name__)

# Lazy import to avoid requiring google-cloud-storage when Firebase is not configured
_storage_client: Optional[Any] = None


def _parse_gs_url(url: str) -> Tuple[str, str]:
    """Parse gs://bucket/path into (bucket, path). Path is without leading slash."""
    m = re.match(r"gs://([^/]+)/(.*)", url.strip())
    if not m:
        raise ValueError(f"Invalid gs:// URL: {url}")
    bucket_name, path = m.group(1), m.group(2) or ""
    return bucket_name, path.lstrip("/")


def _get_client():
    """Return google.cloud.storage Client; create with service account from config."""
    global _storage_client
    if _storage_client is not None:
        return _storage_client
    settings = get_settings()
    creds_json = getattr(settings, "firebase_service_account_json", None)
    if not creds_json or not creds_json.strip():
        raise ValueError(
            "Firebase client requires firebase_service_account_json to be set "
            "(JSON string or path to JSON file)."
        )
    try:
        from google.cloud import storage
        from google.oauth2 import service_account
    except ImportError:
        raise ImportError(
            "Firebase client requires google-cloud-storage. "
            "Install with: pip install google-cloud-storage"
        ) from None
    creds_json = creds_json.strip()
    if creds_json.startswith("{"):
        info = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(info)
    else:
        path = Path(creds_json)
        if not path.exists():
            raise FileNotFoundError(f"Service account file not found: {creds_json}")
        credentials = service_account.Credentials.from_service_account_file(str(path))
    _storage_client = storage.Client(credentials=credentials, project=credentials.project_id)
    return _storage_client


def download_to_path(storage_url: str, local_path: str) -> None:
    """
    Download object at gs:// URL to a local file path.
    Uses streaming for large files. Raises on missing file or permission error.
    """
    bucket_name, path = _parse_gs_url(storage_url)
    client = _get_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(path)
    blob.download_to_filename(local_path)


def download_as_bytes(storage_url: str) -> bytes:
    """Download object at gs:// URL into memory. Use for smaller files."""
    bucket_name, path = _parse_gs_url(storage_url)
    client = _get_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(path)
    return blob.download_as_bytes()


def download_to_file_obj(storage_url: str, file_obj: io.BinaryIO) -> None:
    """Stream download into an open binary file object."""
    bucket_name, path = _parse_gs_url(storage_url)
    client = _get_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(path)
    blob.download_to_file(file_obj)


def rename_blob(storage_url: str, new_name: str) -> str:
    """
    Rename object: copy to new path then delete original.
    new_name is the object name (path within bucket). Returns gs:// URL of new object.
    """
    bucket_name, path = _parse_gs_url(storage_url)
    client = _get_client()
    bucket = client.bucket(bucket_name)
    source_blob = bucket.blob(path)
    # Copy to new path (same bucket)
    new_path = new_name.lstrip("/")
    bucket.copy_blob(source_blob, bucket, new_path)
    source_blob.delete()
    return f"gs://{bucket_name}/{new_path}"


def blob_exists(storage_url: str) -> bool:
    """Return True if the object exists and is readable."""
    try:
        bucket_name, path = _parse_gs_url(storage_url)
        client = _get_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(path)
        return blob.exists()
    except Exception:
        return False


def list_blobs(bucket_name: str, prefix: str = "") -> list[str]:
    """
    List blob names (storage paths) in a bucket under the given prefix.

    Args:
        bucket_name: GCS/Firebase Storage bucket name (e.g. scrapperdb-f854d.firebasestorage.app).
        prefix: Optional prefix (e.g. "pdfs/"). Only blobs whose names start with this are returned.

    Returns:
        List of blob names (paths within the bucket).
    """
    client = _get_client()
    bucket = client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix)
    return [blob.name for blob in blobs]
