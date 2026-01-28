"""
File validation service for PDF uploads.

Provides security checks including:
- File size limits
- MIME type validation
- Filename sanitization
- Content hash calculation for deduplication
"""

import hashlib
import re
from pathlib import Path
from typing import Tuple

import magic
from fastapi import HTTPException, UploadFile

# Constants
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB in bytes
ALLOWED_MIME_TYPE = "application/pdf"


async def validate_pdf(file: UploadFile) -> Tuple[bytes, str, str]:
    """
    Validate uploaded PDF file and return content, hash, and sanitized filename.

    Args:
        file: FastAPI UploadFile instance from multipart/form-data

    Returns:
        Tuple of (file_content, sha256_hash, sanitized_filename)

    Raises:
        HTTPException: 400 for validation errors, 413 for file too large

    Security checks:
        - File size <= 200MB
        - File not empty
        - MIME type is application/pdf
        - Filename sanitized (no path traversal)
        - SHA-256 hash calculated for deduplication
    """
    # Read file content
    content = await file.read()

    # Check file not empty
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")

    # Check file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)}MB"
        )

    # Validate MIME type using python-magic
    mime_type = magic.from_buffer(content, mime=True)
    if mime_type != ALLOWED_MIME_TYPE:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Expected {ALLOWED_MIME_TYPE}, got {mime_type}"
        )

    # Sanitize filename (remove path traversal attempts)
    original_filename = file.filename or "upload.pdf"
    sanitized_filename = sanitize_filename(original_filename)

    # Calculate SHA-256 hash for deduplication
    file_hash = hashlib.sha256(content).hexdigest()

    return content, file_hash, sanitized_filename


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal attacks.

    Args:
        filename: Original filename from upload

    Returns:
        Sanitized filename safe for storage

    Security:
        - Removes directory separators (/, \\)
        - Removes parent directory references (..)
        - Removes null bytes
        - Limits to alphanumeric, dash, underscore, dot
        - Ensures .pdf extension
    """
    # Get base filename (remove any path components)
    filename = Path(filename).name

    # Remove any path traversal attempts
    filename = filename.replace("..", "").replace("/", "").replace("\\", "")

    # Remove null bytes
    filename = filename.replace("\0", "")

    # Keep only safe characters: alphanumeric, dash, underscore, dot
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)

    # Ensure filename is not empty after sanitization
    if not filename or filename == ".pdf":
        filename = "upload.pdf"

    # Ensure .pdf extension
    if not filename.lower().endswith('.pdf'):
        filename = filename + '.pdf'

    # Limit length (max 255 chars for most filesystems)
    if len(filename) > 255:
        # Keep extension, truncate base name
        name_part = filename[:-4]  # Remove .pdf
        name_part = name_part[:250]  # Truncate to 250 chars
        filename = name_part + '.pdf'

    return filename
