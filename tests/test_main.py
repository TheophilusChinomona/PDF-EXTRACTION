"""Tests for FastAPI application endpoints."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create FastAPI test client."""
    return TestClient(app)


# Version Endpoint Tests


def test_version_endpoint(client: TestClient) -> None:
    """Test version endpoint returns version and commit hash."""
    response = client.get("/version")
    assert response.status_code == 200

    data = response.json()
    assert "version" in data
    assert "commit_hash" in data
    assert data["version"] == "1.0.0"
    assert data["commit_hash"] == "development"


def test_version_endpoint_format(client: TestClient) -> None:
    """Test version endpoint returns correct format."""
    response = client.get("/version")
    data = response.json()

    assert isinstance(data, dict)
    assert len(data) == 2  # Only version and commit_hash
    assert isinstance(data["version"], str)
    assert isinstance(data["commit_hash"], str)


# Health Check Tests


@patch("app.main.get_supabase_client")
@patch("app.main.get_gemini_client")
def test_health_check_all_healthy(
    mock_gemini: MagicMock, mock_supabase: MagicMock, client: TestClient
) -> None:
    """Test health check when all services are healthy."""
    # Mock Gemini client
    mock_gemini.return_value = MagicMock()

    # Mock Supabase client
    mock_supabase_client = MagicMock()
    mock_response = MagicMock()
    mock_response.execute.return_value = mock_response
    mock_supabase_client.table.return_value.select.return_value.limit.return_value = (
        mock_response
    )
    mock_supabase.return_value = mock_supabase_client

    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "services" in data

    services = data["services"]
    assert services["opendataloader"] == "healthy"
    assert services["gemini_api"] == "healthy"
    assert services["supabase"] == "healthy"


@patch("app.main.get_supabase_client")
@patch("app.main.get_gemini_client")
def test_health_check_gemini_unhealthy(
    mock_gemini: MagicMock, mock_supabase: MagicMock, client: TestClient
) -> None:
    """Test health check when Gemini API is unavailable."""
    # Mock Gemini client to raise exception
    mock_gemini.side_effect = Exception("API key not configured")

    # Mock Supabase client (healthy)
    mock_supabase_client = MagicMock()
    mock_response = MagicMock()
    mock_response.execute.return_value = mock_response
    mock_supabase_client.table.return_value.select.return_value.limit.return_value = (
        mock_response
    )
    mock_supabase.return_value = mock_supabase_client

    response = client.get("/health")
    assert response.status_code == 503

    data = response.json()
    assert data["status"] == "unhealthy"
    assert "unhealthy" in data["services"]["gemini_api"]
    assert "API key not configured" in data["services"]["gemini_api"]


@patch("app.main.get_supabase_client")
@patch("app.main.get_gemini_client")
def test_health_check_supabase_unhealthy(
    mock_gemini: MagicMock, mock_supabase: MagicMock, client: TestClient
) -> None:
    """Test health check when Supabase connection fails."""
    # Mock Gemini client (healthy)
    mock_gemini.return_value = MagicMock()

    # Mock Supabase client to raise exception
    mock_supabase.side_effect = Exception("Connection refused")

    response = client.get("/health")
    assert response.status_code == 503

    data = response.json()
    assert data["status"] == "unhealthy"
    assert "unhealthy" in data["services"]["supabase"]
    assert "Connection refused" in data["services"]["supabase"]


@patch("app.main.get_supabase_client")
@patch("app.main.get_gemini_client")
def test_health_check_multiple_services_unhealthy(
    mock_gemini: MagicMock, mock_supabase: MagicMock, client: TestClient
) -> None:
    """Test health check when multiple services are unhealthy."""
    # Mock both services to fail
    mock_gemini.side_effect = Exception("Gemini error")
    mock_supabase.side_effect = Exception("Supabase error")

    response = client.get("/health")
    assert response.status_code == 503

    data = response.json()
    assert data["status"] == "unhealthy"
    assert "unhealthy" in data["services"]["gemini_api"]
    assert "unhealthy" in data["services"]["supabase"]


@patch("app.main.get_supabase_client")
@patch("app.main.get_gemini_client")
def test_health_check_response_structure(
    mock_gemini: MagicMock, mock_supabase: MagicMock, client: TestClient
) -> None:
    """Test health check response has correct structure."""
    # Mock both services as healthy
    mock_gemini.return_value = MagicMock()

    mock_supabase_client = MagicMock()
    mock_response = MagicMock()
    mock_response.execute.return_value = mock_response
    mock_supabase_client.table.return_value.select.return_value.limit.return_value = (
        mock_response
    )
    mock_supabase.return_value = mock_supabase_client

    response = client.get("/health")
    data = response.json()

    # Check top-level structure
    assert "status" in data
    assert "timestamp" in data
    assert "services" in data

    # Check services structure
    services = data["services"]
    assert "opendataloader" in services
    assert "gemini_api" in services
    assert "supabase" in services

    # Verify timestamp format (ISO 8601)
    assert "T" in data["timestamp"]
    assert isinstance(data["timestamp"], str)


@patch("app.main.get_supabase_client")
@patch("app.main.get_gemini_client")
def test_health_check_supabase_none_response(
    mock_gemini: MagicMock, mock_supabase: MagicMock, client: TestClient
) -> None:
    """Test health check when Supabase returns None response."""
    # Mock Gemini client (healthy)
    mock_gemini.return_value = MagicMock()

    # Mock Supabase to return None
    mock_supabase_client = MagicMock()
    mock_supabase_client.table.return_value.select.return_value.limit.return_value.execute.return_value = (
        None
    )
    mock_supabase.return_value = mock_supabase_client

    response = client.get("/health")
    assert response.status_code == 503

    data = response.json()
    assert data["status"] == "unhealthy"
    assert "no response" in data["services"]["supabase"]


@patch("app.main.get_supabase_client")
@patch("app.main.get_gemini_client")
def test_health_check_gemini_returns_none(
    mock_gemini: MagicMock, mock_supabase: MagicMock, client: TestClient
) -> None:
    """Test health check when get_gemini_client returns None."""
    # Mock Gemini client to return None
    mock_gemini.return_value = None

    # Mock Supabase client (healthy)
    mock_supabase_client = MagicMock()
    mock_response = MagicMock()
    mock_response.execute.return_value = mock_response
    mock_supabase_client.table.return_value.select.return_value.limit.return_value = (
        mock_response
    )
    mock_supabase.return_value = mock_supabase_client

    response = client.get("/health")
    assert response.status_code == 503

    data = response.json()
    assert data["status"] == "unhealthy"
    assert "client is None" in data["services"]["gemini_api"]


# Lifespan Event Tests


@patch("app.main.get_settings")
def test_lifespan_success(mock_settings: MagicMock) -> None:
    """Test lifespan with valid configuration."""
    # Mock settings
    mock_settings.return_value = MagicMock(
        model_name="gemini-3-flash-preview", enable_hybrid_mode=True
    )

    # Create a test client which will trigger lifespan events
    from fastapi.testclient import TestClient
    from app.main import app

    try:
        with TestClient(app) as client:
            # If we get here, startup was successful
            assert client is not None
    except Exception:
        pytest.fail("Lifespan startup should not raise exception with valid settings")


@patch("app.main.get_settings")
def test_lifespan_validation_failure(mock_settings: MagicMock) -> None:
    """Test lifespan raises exception when validation fails."""
    from pydantic import ValidationError

    # Mock settings to raise ValidationError
    mock_settings.side_effect = ValidationError.from_exception_data(
        "Settings",
        [{"type": "missing", "loc": ("gemini_api_key",), "msg": "Field required"}],
    )

    from fastapi.testclient import TestClient
    from app.main import app

    # Startup should raise exception
    with pytest.raises(ValidationError):
        with TestClient(app):
            pass


# API Documentation Tests


def test_openapi_docs_available(client: TestClient) -> None:
    """Test that OpenAPI documentation is available at /docs."""
    response = client.get("/docs")
    assert response.status_code == 200


def test_redoc_docs_available(client: TestClient) -> None:
    """Test that ReDoc documentation is available at /redoc."""
    response = client.get("/redoc")
    assert response.status_code == 200


def test_openapi_schema_available(client: TestClient) -> None:
    """Test that OpenAPI schema is available at /openapi.json."""
    response = client.get("/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    assert "openapi" in schema
    assert "info" in schema
    assert schema["info"]["title"] == "PDF Extraction API"
    assert schema["info"]["version"] == "1.0.0"
