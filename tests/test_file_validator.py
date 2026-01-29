"""
Tests for file validation service.

Covers:
- File size limits
- Empty file detection
- MIME type validation
- Filename sanitization
- SHA-256 hash calculation
- Security edge cases (path traversal, null bytes, etc.)
"""

import hashlib
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from app.services.file_validator import sanitize_filename, validate_pdf

# Test data
VALID_PDF_HEADER = b"%PDF-1.4\n"
VALID_PDF_CONTENT = VALID_PDF_HEADER + b"Some PDF content here" + b"\n%%EOF"


@pytest.fixture
def mock_upload_file():
    """Create a mock UploadFile instance."""
    def _create_file(content: bytes, filename: str = "test.pdf"):
        file = MagicMock(spec=UploadFile)
        file.filename = filename
        file.read = AsyncMock(return_value=content)
        return file
    return _create_file


@pytest.mark.asyncio
@patch('app.services.file_validator.magic.from_buffer')
async def test_validate_pdf_success(mock_magic, mock_upload_file):
    """Test successful PDF validation."""
    mock_magic.return_value = "application/pdf"

    file = mock_upload_file(VALID_PDF_CONTENT, "document.pdf")

    content, file_hash, sanitized_name = await validate_pdf(file)

    assert content == VALID_PDF_CONTENT
    assert file_hash == hashlib.sha256(VALID_PDF_CONTENT).hexdigest()
    assert sanitized_name == "document.pdf"
    mock_magic.assert_called_once_with(VALID_PDF_CONTENT, mime=True)


@pytest.mark.asyncio
@patch('app.services.file_validator.magic.from_buffer')
async def test_validate_pdf_empty_file(mock_magic, mock_upload_file):
    """Test validation fails for empty file."""
    file = mock_upload_file(b"", "empty.pdf")

    with pytest.raises(HTTPException) as exc_info:
        await validate_pdf(file)

    assert exc_info.value.status_code == 400
    assert "empty" in exc_info.value.detail.lower()


@pytest.mark.asyncio
@patch('app.services.file_validator.magic.from_buffer')
async def test_validate_pdf_file_too_large(mock_magic, mock_upload_file):
    """Test validation fails when file exceeds 200MB."""
    # Create content larger than 200MB
    large_content = b"x" * (201 * 1024 * 1024)
    file = mock_upload_file(large_content, "huge.pdf")

    with pytest.raises(HTTPException) as exc_info:
        await validate_pdf(file)

    assert exc_info.value.status_code == 413
    assert "too large" in exc_info.value.detail.lower()
    assert "200" in exc_info.value.detail


@pytest.mark.asyncio
@patch('app.services.file_validator.magic.from_buffer')
async def test_validate_pdf_invalid_mime_type(mock_magic, mock_upload_file):
    """Test validation fails for non-PDF MIME type."""
    mock_magic.return_value = "image/jpeg"

    file = mock_upload_file(b"fake image content", "image.pdf")

    with pytest.raises(HTTPException) as exc_info:
        await validate_pdf(file)

    assert exc_info.value.status_code == 400
    assert "invalid file type" in exc_info.value.detail.lower()
    assert "application/pdf" in exc_info.value.detail
    assert "image/jpeg" in exc_info.value.detail


@pytest.mark.asyncio
@patch('app.services.file_validator.magic.from_buffer')
async def test_validate_pdf_calculates_correct_hash(mock_magic, mock_upload_file):
    """Test SHA-256 hash is calculated correctly."""
    mock_magic.return_value = "application/pdf"

    content = b"unique content for hashing"
    expected_hash = hashlib.sha256(content).hexdigest()

    file = mock_upload_file(content, "test.pdf")
    _, file_hash, _ = await validate_pdf(file)

    assert file_hash == expected_hash


@pytest.mark.asyncio
@patch('app.services.file_validator.magic.from_buffer')
async def test_validate_pdf_sanitizes_filename(mock_magic, mock_upload_file):
    """Test filename is sanitized for security."""
    mock_magic.return_value = "application/pdf"

    file = mock_upload_file(VALID_PDF_CONTENT, "../../../etc/passwd")
    _, _, sanitized_name = await validate_pdf(file)

    # Should remove path traversal attempts
    assert ".." not in sanitized_name
    assert "/" not in sanitized_name
    assert "\\" not in sanitized_name


@pytest.mark.asyncio
@patch('app.services.file_validator.magic.from_buffer')
async def test_validate_pdf_missing_filename(mock_magic, mock_upload_file):
    """Test handles missing filename gracefully."""
    mock_magic.return_value = "application/pdf"

    file = mock_upload_file(VALID_PDF_CONTENT, "")
    file.filename = None

    _, _, sanitized_name = await validate_pdf(file)

    assert sanitized_name == "upload.pdf"


# Filename sanitization tests

def test_sanitize_filename_basic():
    """Test basic filename sanitization."""
    assert sanitize_filename("document.pdf") == "document.pdf"
    assert sanitize_filename("My Document.pdf") == "My_Document.pdf"
    assert sanitize_filename("file-name_123.pdf") == "file-name_123.pdf"


def test_sanitize_filename_path_traversal():
    """Test removal of path traversal attempts."""
    # Path(filename).name extracts base filename, removing directory components
    assert sanitize_filename("../../../etc/passwd") == "passwd.pdf"
    assert sanitize_filename("..\\..\\windows\\system32") == "system32.pdf"
    assert sanitize_filename("./secret.pdf") == "secret.pdf"


def test_sanitize_filename_removes_path_components():
    """Test removal of directory paths."""
    assert sanitize_filename("/var/www/document.pdf") == "document.pdf"
    assert sanitize_filename("C:\\Users\\admin\\secret.pdf") == "secret.pdf"
    assert sanitize_filename("folder/subfolder/file.pdf") == "file.pdf"


def test_sanitize_filename_removes_null_bytes():
    """Test removal of null bytes."""
    assert sanitize_filename("file\0name.pdf") == "filename.pdf"
    assert sanitize_filename("doc\x00ument.pdf") == "document.pdf"


def test_sanitize_filename_removes_special_chars():
    """Test removal of special characters."""
    # * is part of .pdf extension extraction, so it's already removed before regex
    assert sanitize_filename("file<>:?\"|*.pdf") == "file_______.pdf"
    assert sanitize_filename("document@#$%.pdf") == "document____.pdf"


def test_sanitize_filename_adds_pdf_extension():
    """Test .pdf extension is added if missing."""
    assert sanitize_filename("document") == "document.pdf"
    assert sanitize_filename("file.txt") == "file.txt.pdf"
    assert sanitize_filename("image.jpg") == "image.jpg.pdf"


def test_sanitize_filename_handles_empty():
    """Test handling of empty filename."""
    assert sanitize_filename("") == "upload.pdf"
    assert sanitize_filename(".pdf") == "upload.pdf"
    assert sanitize_filename("....") == "upload.pdf"


def test_sanitize_filename_limits_length():
    """Test filename length is limited to 255 characters."""
    long_name = "a" * 300 + ".pdf"
    result = sanitize_filename(long_name)

    assert len(result) <= 255
    assert result.endswith(".pdf")


def test_sanitize_filename_preserves_case():
    """Test filename case is preserved."""
    assert sanitize_filename("MyDocument.PDF") == "MyDocument.PDF"
    assert sanitize_filename("REPORT.pdf") == "REPORT.pdf"


def test_sanitize_filename_unicode_characters():
    """Test Unicode characters are replaced with underscores."""
    assert sanitize_filename("café.pdf") == "caf_.pdf"
    assert sanitize_filename("文档.pdf") == "__.pdf"
    assert sanitize_filename("naïve-résumé.pdf") == "na_ve-r_sum_.pdf"


def test_sanitize_filename_multiple_dots():
    """Test multiple dots are preserved."""
    assert sanitize_filename("document.backup.pdf") == "document.backup.pdf"
    assert sanitize_filename("file.v2.final.pdf") == "file.v2.final.pdf"


@pytest.mark.asyncio
@patch('app.services.file_validator.magic.from_buffer')
async def test_validate_pdf_exactly_200mb(mock_magic, mock_upload_file):
    """Test file at exactly 200MB limit is accepted."""
    mock_magic.return_value = "application/pdf"

    # Exactly 200MB
    content = b"x" * (200 * 1024 * 1024)
    file = mock_upload_file(content, "max_size.pdf")

    # Should not raise
    result = await validate_pdf(file)
    assert result is not None


@pytest.mark.asyncio
@patch('app.services.file_validator.magic.from_buffer')
async def test_validate_pdf_one_byte_over_limit(mock_magic, mock_upload_file):
    """Test file at 200MB + 1 byte is rejected."""
    # One byte over 200MB
    content = b"x" * (200 * 1024 * 1024 + 1)
    file = mock_upload_file(content, "too_big.pdf")

    with pytest.raises(HTTPException) as exc_info:
        await validate_pdf(file)

    assert exc_info.value.status_code == 413
