"""Logging middleware for request tracking and structured logging."""

import json
import logging
import sys
import time
import uuid
from typing import Any, Awaitable, Callable, Dict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',  # We'll format as JSON ourselves
    stream=sys.stdout
)

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs request/response information in structured JSON format.

    Logs include:
    - Request ID (UUID)
    - HTTP method and path
    - Status code
    - Processing time
    - Client IP
    - Routing decisions (processing_method, quality_score)

    Security notes:
    - Does NOT log API keys, file contents, or sensitive user data
    - Does NOT log request/response bodies
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Process request and log structured information."""
        # Use request ID from RequestIDMiddleware if present, otherwise generate
        request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
        request.state.request_id = request_id

        # Record start time
        start_time = time.time()

        # Extract basic request info (before processing)
        log_data: Dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "user_ip": request.client.host if request.client else "unknown",
        }

        # Process the request
        try:
            response = await call_next(request)
        except Exception as e:
            # Log error with full stack trace and contextual message
            processing_time_ms = (time.time() - start_time) * 1000
            error_log = {
                **log_data,
                "status_code": 500,
                "processing_time_ms": round(processing_time_ms, 2),
                "error": str(e),
                "error_type": type(e).__name__,
                "message": f"Request failed: {request.method} {request.url.path}",
            }
            logger.error(json.dumps(error_log), exc_info=True)
            raise

        # Calculate processing time
        processing_time_ms = (time.time() - start_time) * 1000

        # Add response information
        log_data.update({
            "status_code": response.status_code,
            "processing_time_ms": round(processing_time_ms, 2),
        })

        # Extract routing/context from response headers (if present)
        if "X-Processing-Method" in response.headers:
            log_data["processing_method"] = response.headers["X-Processing-Method"]
        if "X-Doc-Type" in response.headers:
            log_data["doc_type"] = response.headers["X-Doc-Type"]

        if "X-Quality-Score" in response.headers:
            try:
                log_data["quality_score"] = float(response.headers["X-Quality-Score"])
            except (ValueError, TypeError):
                pass  # Ignore invalid quality scores

        # Log the request (as JSON)
        logger.info(json.dumps(log_data))

        # Add request ID to response headers for client reference
        response.headers["X-Request-ID"] = request_id

        return response


def get_request_id(request: Request) -> str:
    """
    Get the request ID from the request state.

    Args:
        request: FastAPI request object

    Returns:
        Request ID string (UUID)
    """
    return getattr(request.state, "request_id", "unknown")
