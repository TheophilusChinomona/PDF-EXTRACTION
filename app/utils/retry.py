"""Retry logic with exponential backoff for API calls.

This module provides a decorator for automatic retry of transient failures
with exponential backoff and jitter to prevent thundering herd problems.
"""

import functools
import logging
import random
import time
from typing import Any, Callable, Set, Type, TypeVar, cast

# Configure logging
logger = logging.getLogger(__name__)

# Type variable for generic function decoration
F = TypeVar("F", bound=Callable[..., Any])

# HTTP status codes that should trigger retry
RETRYABLE_STATUS_CODES: Set[int] = {
    429,  # Rate limit
    500,  # Server error
    503,  # Service unavailable
}

# HTTP status codes that should NOT trigger retry
NON_RETRYABLE_STATUS_CODES: Set[int] = {
    400,  # Bad request
    401,  # Unauthorized
    403,  # Forbidden
    404,  # Not found
    422,  # Unprocessable entity
}

# Retry configuration
MAX_RETRIES = 5
BASE_DELAY = 1.0  # seconds
MAX_JITTER = 1.0  # seconds


def retry_with_backoff(
    max_retries: int = MAX_RETRIES,
    base_delay: float = BASE_DELAY,
    max_jitter: float = MAX_JITTER,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """Decorator that retries a function with exponential backoff.

    Retries on:
    - 429 (rate limit)
    - 500 (server error)
    - 503 (service unavailable)
    - Network timeouts and connection errors

    Does NOT retry on:
    - 400 (bad request)
    - 401 (unauthorized)
    - 403 (forbidden)
    - 404 (not found)
    - 422 (unprocessable entity)

    Args:
        max_retries: Maximum number of retry attempts (default: 5)
        base_delay: Base delay in seconds for exponential backoff (default: 1.0)
        max_jitter: Maximum random jitter in seconds (default: 1.0)
        retryable_exceptions: Tuple of exception types to retry

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # Check if we should retry this exception
                    should_retry = _should_retry_exception(e, retryable_exceptions)

                    if not should_retry or attempt >= max_retries:
                        # Don't retry or max retries reached
                        if attempt >= max_retries:
                            logger.error(
                                f"{func.__name__} failed after {max_retries} retries: {e}"
                            )
                        raise

                    # Calculate exponential backoff with jitter
                    delay = (base_delay * (2**attempt)) + (random.random() * max_jitter)

                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    time.sleep(delay)

            # Should never reach here, but satisfy type checker
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry loop exit")

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # Check if we should retry this exception
                    should_retry = _should_retry_exception(e, retryable_exceptions)

                    if not should_retry or attempt >= max_retries:
                        # Don't retry or max retries reached
                        if attempt >= max_retries:
                            logger.error(
                                f"{func.__name__} failed after {max_retries} retries: {e}"
                            )
                        raise

                    # Calculate exponential backoff with jitter
                    delay = (base_delay * (2**attempt)) + (random.random() * max_jitter)

                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    time.sleep(delay)

            # Should never reach here, but satisfy type checker
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry loop exit")

        # Return appropriate wrapper based on whether function is async
        import inspect

        if inspect.iscoroutinefunction(func):
            return cast(F, async_wrapper)
        else:
            return cast(F, sync_wrapper)

    return decorator


def _should_retry_exception(
    exception: Exception, retryable_exceptions: tuple[Type[Exception], ...]
) -> bool:
    """Determine if an exception should trigger a retry.

    Args:
        exception: The exception that was raised
        retryable_exceptions: Tuple of exception types to retry

    Returns:
        True if the exception should trigger retry, False otherwise
    """
    # Check for HTTP status code in exception message or attributes
    status_code = _extract_status_code(exception)

    if status_code:
        # If we have a status code, check if it's retryable
        if status_code in NON_RETRYABLE_STATUS_CODES:
            return False
        if status_code in RETRYABLE_STATUS_CODES:
            return True

    # Check for common network errors
    exception_str = str(exception).lower()
    network_errors = [
        "timeout",
        "connection",
        "network",
        "timed out",
        "connection reset",
        "connection refused",
    ]

    for error in network_errors:
        if error in exception_str:
            return True

    # Check if exception type matches retryable types
    return isinstance(exception, retryable_exceptions)


def _extract_status_code(exception: Exception) -> int | None:
    """Extract HTTP status code from exception.

    Args:
        exception: Exception that may contain status code

    Returns:
        HTTP status code if found, None otherwise
    """
    # Check for status_code attribute (common in HTTP client libraries)
    if hasattr(exception, "status_code"):
        return int(getattr(exception, "status_code"))

    # Check for code attribute
    if hasattr(exception, "code"):
        code = getattr(exception, "code")
        if isinstance(code, int):
            return code

    # Check for response.status_code (requests/httpx pattern)
    if hasattr(exception, "response"):
        response = getattr(exception, "response")
        if hasattr(response, "status_code"):
            return int(getattr(response, "status_code"))

    return None
