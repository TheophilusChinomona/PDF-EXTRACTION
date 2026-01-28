"""FastAPI application for PDF extraction service."""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Dict, Union

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler  # type: ignore[import-not-found]
from slowapi.errors import RateLimitExceeded  # type: ignore[import-not-found]

from app.config import get_settings
from app.db.supabase_client import get_supabase_client
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.rate_limit import (
    get_limiter,
    rate_limit_exceeded_handler,
    RateLimitMiddleware,
)
from app.services.gemini_client import get_gemini_client

# Application metadata
VERSION = "1.0.0"
COMMIT_HASH = "development"  # This can be set via environment variable or build process


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan event handler for startup and shutdown."""
    # Startup: Validate environment configuration
    try:
        # This will raise ValidationError if required env vars are missing
        settings = get_settings()

        # Log startup (without exposing secrets)
        print(f"Starting PDF Extraction API v{VERSION}")
        print(f"Model: {settings.model_name}")
        print(f"Hybrid mode: {settings.enable_hybrid_mode}")
        print("Environment validation: OK")

    except Exception as e:
        print(f"Startup validation failed: {e}")
        raise

    yield

    # Shutdown: cleanup if needed
    print("Shutting down PDF Extraction API")


app = FastAPI(
    title="PDF Extraction API",
    description="Academic PDF Extraction Microservice with Hybrid Architecture (OpenDataLoader + Gemini)",
    version=VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Add rate limiter to app state (required by slowapi)
limiter = get_limiter()
app.state.limiter = limiter

# Register custom rate limit exceeded handler
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Add logging middleware (first, so it wraps all other middleware)
app.add_middleware(RequestLoggingMiddleware)

# Add rate limit middleware for adding X-RateLimit-Remaining header
app.add_middleware(RateLimitMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=None)
async def health_check() -> Union[Dict[str, Any], Response]:
    """
    Health check endpoint that verifies all required services are operational.

    Returns:
        JSON response with overall status and individual service statuses.

    Status Codes:
        200: All services healthy
        503: One or more services unavailable
    """
    timestamp = datetime.utcnow().isoformat()
    services: Dict[str, str] = {}
    overall_healthy = True

    # Check OpenDataLoader
    try:
        from opendataloader_pdf import convert  # noqa: F401
        services["opendataloader"] = "healthy"
    except Exception as e:
        services["opendataloader"] = f"unhealthy: {str(e)}"
        overall_healthy = False

    # Check Gemini API client
    try:
        client = get_gemini_client()
        if client:
            services["gemini_api"] = "healthy"
        else:
            services["gemini_api"] = "unhealthy: client is None"
            overall_healthy = False
    except Exception as e:
        services["gemini_api"] = f"unhealthy: {str(e)}"
        overall_healthy = False

    # Check Supabase connection
    try:
        supabase_client = get_supabase_client()
        # Test database connection with a simple query
        response = supabase_client.table("extractions").select("id").limit(1).execute()
        if response is not None:
            services["supabase"] = "healthy"
        else:
            services["supabase"] = "unhealthy: no response"
            overall_healthy = False
    except Exception as e:
        services["supabase"] = f"unhealthy: {str(e)}"
        overall_healthy = False

    response_data: Dict[str, Any] = {
        "status": "healthy" if overall_healthy else "unhealthy",
        "timestamp": timestamp,
        "services": services,
    }

    # FastAPI doesn't allow setting status_code in the return directly,
    # so we'll use Response object for 503
    if not overall_healthy:
        import json
        return Response(
            content=json.dumps(response_data),
            status_code=503,
            media_type="application/json",
        )

    return response_data


@app.get("/version")
async def version_info() -> Dict[str, str]:
    """
    Get version information for the API.

    Returns:
        JSON with version number and commit hash.
    """
    return {
        "version": VERSION,
        "commit_hash": COMMIT_HASH,
    }


# Include extraction router
from app.routers import extraction
app.include_router(extraction.router)

# Include review queue router
from app.routers import review_queue
app.include_router(review_queue.router)
