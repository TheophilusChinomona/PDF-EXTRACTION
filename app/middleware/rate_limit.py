"""Rate limiting middleware using slowapi for abuse prevention."""

from typing import Any, Callable

from fastapi import Request, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


def get_client_ip(request: Request) -> str:
    """
    Get the client IP address from the request.

    Only trusts X-Forwarded-For header from configured trusted proxies
    to prevent IP spoofing attacks.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address string
    """
    from app.config import get_settings

    direct_ip: str = get_remote_address(request)

    # Check trusted proxies
    settings = get_settings()
    if not settings.trusted_proxies:
        return direct_ip  # Prevent spoofing

    # Parse trusted proxy list
    trusted_proxy_list = [
        ip.strip() for ip in settings.trusted_proxies.split(",")
        if ip.strip()
    ]

    # Only trust X-Forwarded-For if from trusted proxy
    if direct_ip in trusted_proxy_list:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

    return direct_ip


# Create the limiter with in-memory storage (MVP)
# Uses client IP as the key for rate limiting
limiter = Limiter(key_func=get_client_ip, default_limits=["200/minute"])


# Rate limit configurations for specific endpoints
RATE_LIMITS = {
    "extract": "10/minute",      # POST /api/extract - CPU/API intensive
    "batch": "2/minute",         # POST /api/batch - Very resource intensive
    "extractions": "100/minute", # GET /api/extractions/* - Read operations
}


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """
    Custom handler for rate limit exceeded errors.

    Returns 429 Too Many Requests with appropriate headers:
    - Retry-After: Seconds until the rate limit resets
    - X-RateLimit-Limit: The rate limit that was exceeded
    - X-RateLimit-Remaining: Always 0 when exceeded

    Args:
        request: FastAPI request object
        exc: RateLimitExceeded exception with limit details

    Returns:
        Response with 429 status code and rate limit headers
    """
    import json

    # Parse the retry-after from the exception detail
    # slowapi provides this in the detail string
    retry_after = getattr(exc, "retry_after", 60)  # Default to 60 seconds

    # Build error response
    error_body = {
        "detail": "Rate limit exceeded",
        "message": f"Too many requests. Please retry after {retry_after} seconds.",
        "retry_after": retry_after,
    }

    response = Response(
        content=json.dumps(error_body),
        status_code=429,
        media_type="application/json",
    )

    # Add rate limit headers
    response.headers["Retry-After"] = str(retry_after)
    response.headers["X-RateLimit-Remaining"] = "0"

    # Add the limit that was exceeded if available
    if hasattr(exc, "detail") and exc.detail:
        response.headers["X-RateLimit-Limit"] = exc.detail

    return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds X-RateLimit-Remaining header to all responses.

    This middleware works in conjunction with slowapi's route-based limiting
    to provide consistent rate limit information to clients.

    Note: The actual rate limiting is done by slowapi decorators on routes.
    This middleware adds the remaining count header to all responses.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Any,
    ) -> Response:
        """Add rate limit headers to all responses."""
        response: Response = await call_next(request)

        # Get the current rate limit state if available
        # slowapi stores this in request.state after checking limits
        if hasattr(request.state, "_rate_limiting_complete"):
            rate_limit_data = getattr(request.state, "_rate_limit_data", None)
            if rate_limit_data:
                remaining = rate_limit_data.get("remaining", 0)
                response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response


def get_limiter() -> Any:
    """
    Get the configured limiter instance.

    This function returns the module-level limiter instance,
    allowing it to be used by route decorators.

    Returns:
        Configured Limiter instance
    """
    return limiter


# Decorator functions for easy use in routes
def limit_extract(func: Callable[..., Any]) -> Callable[..., Any]:
    """Apply rate limit for extract endpoint (10/minute)."""
    decorated: Callable[..., Any] = limiter.limit(RATE_LIMITS["extract"])(func)
    return decorated


def limit_batch(func: Callable[..., Any]) -> Callable[..., Any]:
    """Apply rate limit for batch endpoint (2/minute)."""
    decorated: Callable[..., Any] = limiter.limit(RATE_LIMITS["batch"])(func)
    return decorated


def limit_extractions(func: Callable[..., Any]) -> Callable[..., Any]:
    """Apply rate limit for extractions read endpoints (100/minute)."""
    decorated: Callable[..., Any] = limiter.limit(RATE_LIMITS["extractions"])(func)
    return decorated
