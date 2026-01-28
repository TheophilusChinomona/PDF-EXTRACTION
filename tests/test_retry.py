"""Tests for retry logic with exponential backoff."""

import logging
import time
from unittest.mock import MagicMock, patch

import pytest

from app.utils.retry import (
    retry_with_backoff,
    _should_retry_exception,
    _extract_status_code,
    RETRYABLE_STATUS_CODES,
    NON_RETRYABLE_STATUS_CODES,
)


class MockHTTPException(Exception):
    """Mock HTTP exception with status code."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class MockNetworkException(Exception):
    """Mock network exception."""

    pass


# Tests for _extract_status_code


def test_extract_status_code_from_attribute():
    """Test extracting status code from status_code attribute."""
    exception = MockHTTPException("Server error", 500)
    assert _extract_status_code(exception) == 500


def test_extract_status_code_from_code_attribute():
    """Test extracting status code from code attribute."""
    exception = Exception("Error")
    exception.code = 429  # type: ignore
    assert _extract_status_code(exception) == 429


def test_extract_status_code_from_response():
    """Test extracting status code from response.status_code."""
    exception = Exception("Error")
    exception.response = MagicMock()  # type: ignore
    exception.response.status_code = 503  # type: ignore
    assert _extract_status_code(exception) == 503


def test_extract_status_code_none():
    """Test returning None when no status code found."""
    exception = Exception("Generic error")
    assert _extract_status_code(exception) is None


# Tests for _should_retry_exception


def test_should_retry_non_retryable_status():
    """Test that non-retryable status codes return False."""
    for status_code in NON_RETRYABLE_STATUS_CODES:
        exception = MockHTTPException(f"Error {status_code}", status_code)
        assert _should_retry_exception(exception, (Exception,)) is False


def test_should_retry_retryable_status():
    """Test that retryable status codes return True."""
    for status_code in RETRYABLE_STATUS_CODES:
        exception = MockHTTPException(f"Error {status_code}", status_code)
        assert _should_retry_exception(exception, (Exception,)) is True


def test_should_retry_network_timeout():
    """Test that timeout errors are retryable."""
    exception = MockNetworkException("Connection timeout")
    assert _should_retry_exception(exception, (Exception,)) is True


def test_should_retry_connection_reset():
    """Test that connection reset errors are retryable."""
    exception = MockNetworkException("Connection reset by peer")
    assert _should_retry_exception(exception, (Exception,)) is True


def test_should_retry_generic_exception():
    """Test that generic exceptions matching retryable types are retryable."""
    exception = ValueError("Some error")
    assert _should_retry_exception(exception, (ValueError,)) is True


def test_should_not_retry_non_matching_exception():
    """Test that exceptions not matching retryable types are not retryable."""
    exception = ValueError("Some error")
    assert _should_retry_exception(exception, (TypeError,)) is False


# Tests for retry_with_backoff decorator (sync functions)


def test_retry_successful_on_first_attempt():
    """Test that successful function call doesn't retry."""
    call_count = 0

    @retry_with_backoff(max_retries=3)
    def succeeds():
        nonlocal call_count
        call_count += 1
        return "success"

    result = succeeds()
    assert result == "success"
    assert call_count == 1


def test_retry_eventually_succeeds():
    """Test that function succeeds after retries."""
    call_count = 0

    @retry_with_backoff(max_retries=3, base_delay=0.01, max_jitter=0.01)
    def succeeds_on_third_attempt():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise MockHTTPException("Server error", 500)
        return "success"

    result = succeeds_on_third_attempt()
    assert result == "success"
    assert call_count == 3


def test_retry_max_retries_exceeded():
    """Test that exception is raised after max retries."""
    call_count = 0

    @retry_with_backoff(max_retries=2, base_delay=0.01, max_jitter=0.01)
    def always_fails():
        nonlocal call_count
        call_count += 1
        raise MockHTTPException("Server error", 500)

    with pytest.raises(MockHTTPException):
        always_fails()

    assert call_count == 3  # Initial attempt + 2 retries


def test_retry_non_retryable_error():
    """Test that non-retryable errors don't trigger retry."""
    call_count = 0

    @retry_with_backoff(max_retries=3)
    def bad_request():
        nonlocal call_count
        call_count += 1
        raise MockHTTPException("Bad request", 400)

    with pytest.raises(MockHTTPException):
        bad_request()

    assert call_count == 1  # No retries for 400 error


def test_retry_exponential_backoff():
    """Test that retry delays increase exponentially."""
    delays = []

    @retry_with_backoff(max_retries=3, base_delay=1.0, max_jitter=0.0)
    def always_fails():
        raise MockHTTPException("Server error", 500)

    with patch("time.sleep") as mock_sleep:
        with pytest.raises(MockHTTPException):
            always_fails()

        # Collect all sleep delays
        delays = [call[0][0] for call in mock_sleep.call_args_list]

    # Verify exponential backoff: 1s, 2s, 4s
    assert len(delays) == 3
    assert delays[0] == 1.0  # 2^0 * 1.0 + 0
    assert delays[1] == 2.0  # 2^1 * 1.0 + 0
    assert delays[2] == 4.0  # 2^2 * 1.0 + 0


def test_retry_jitter_added():
    """Test that random jitter is added to delays."""
    @retry_with_backoff(max_retries=2, base_delay=1.0, max_jitter=1.0)
    def always_fails():
        raise MockHTTPException("Server error", 500)

    with patch("time.sleep") as mock_sleep:
        with pytest.raises(MockHTTPException):
            always_fails()

        # Collect all sleep delays
        delays = [call[0][0] for call in mock_sleep.call_args_list]

    # Verify jitter: delays should be >= base_delay and < base_delay + max_jitter
    assert len(delays) == 2
    assert 1.0 <= delays[0] < 2.0  # 1.0 base + [0, 1.0) jitter
    assert 2.0 <= delays[1] < 3.0  # 2.0 base + [0, 1.0) jitter


def test_retry_logs_attempts(caplog):
    """Test that retry attempts are logged."""
    caplog.set_level(logging.WARNING)

    @retry_with_backoff(max_retries=2, base_delay=0.01, max_jitter=0.01)
    def always_fails():
        raise MockHTTPException("Server error", 500)

    with pytest.raises(MockHTTPException):
        always_fails()

    # Check that warning logs were created for retries
    assert len(caplog.records) >= 2
    assert "attempt 1/2" in caplog.text
    assert "attempt 2/2" in caplog.text
    assert "Retrying in" in caplog.text


def test_retry_logs_final_failure(caplog):
    """Test that final failure is logged as error."""
    caplog.set_level(logging.ERROR)

    @retry_with_backoff(max_retries=1, base_delay=0.01, max_jitter=0.01)
    def always_fails():
        raise MockHTTPException("Server error", 500)

    with pytest.raises(MockHTTPException):
        always_fails()

    # Check that error log was created for final failure
    assert "failed after 1 retries" in caplog.text


# Tests for retry_with_backoff decorator (async functions)


@pytest.mark.asyncio
async def test_retry_async_successful_on_first_attempt():
    """Test that successful async function call doesn't retry."""
    call_count = 0

    @retry_with_backoff(max_retries=3)
    async def async_succeeds():
        nonlocal call_count
        call_count += 1
        return "success"

    result = await async_succeeds()
    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_async_eventually_succeeds():
    """Test that async function succeeds after retries."""
    call_count = 0

    @retry_with_backoff(max_retries=3, base_delay=0.01, max_jitter=0.01)
    async def async_succeeds_on_third_attempt():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise MockHTTPException("Server error", 500)
        return "success"

    result = await async_succeeds_on_third_attempt()
    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_async_max_retries_exceeded():
    """Test that exception is raised after max retries for async function."""
    call_count = 0

    @retry_with_backoff(max_retries=2, base_delay=0.01, max_jitter=0.01)
    async def async_always_fails():
        nonlocal call_count
        call_count += 1
        raise MockHTTPException("Server error", 503)

    with pytest.raises(MockHTTPException):
        await async_always_fails()

    assert call_count == 3  # Initial attempt + 2 retries


@pytest.mark.asyncio
async def test_retry_async_non_retryable_error():
    """Test that non-retryable errors don't trigger retry for async functions."""
    call_count = 0

    @retry_with_backoff(max_retries=3)
    async def async_bad_request():
        nonlocal call_count
        call_count += 1
        raise MockHTTPException("Unauthorized", 401)

    with pytest.raises(MockHTTPException):
        await async_bad_request()

    assert call_count == 1  # No retries for 401 error


@pytest.mark.asyncio
async def test_retry_async_exponential_backoff():
    """Test that async retry delays increase exponentially."""
    @retry_with_backoff(max_retries=3, base_delay=1.0, max_jitter=0.0)
    async def async_always_fails():
        raise MockHTTPException("Rate limit", 429)

    with patch("time.sleep") as mock_sleep:
        with pytest.raises(MockHTTPException):
            await async_always_fails()

        # Collect all sleep delays
        delays = [call[0][0] for call in mock_sleep.call_args_list]

    # Verify exponential backoff: 1s, 2s, 4s
    assert len(delays) == 3
    assert delays[0] == 1.0  # 2^0 * 1.0 + 0
    assert delays[1] == 2.0  # 2^1 * 1.0 + 0
    assert delays[2] == 4.0  # 2^2 * 1.0 + 0
