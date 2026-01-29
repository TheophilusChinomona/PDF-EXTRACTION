"""Tests for statistics endpoints."""

import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.routers import stats


@pytest.fixture(autouse=True)
def reset_stats_cache() -> None:
    """Reset routing stats cache before each test."""
    stats._routing_stats_cache = None
    stats._routing_stats_cache_time = 0


class TestCachingStatsEndpoint:
    """Test GET /api/stats/caching endpoint."""

    def test_caching_stats_no_data(self) -> None:
        """Test caching stats with no extractions."""
        client = TestClient(app)

        # Mock Supabase response with no extractions
        mock_response = MagicMock()
        mock_response.data = []

        with patch('app.routers.stats.get_supabase_client') as mock_get_client:
            mock_supabase = MagicMock()
            mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_supabase

            response = client.get("/api/stats/caching")

        assert response.status_code == 200
        data = response.json()

        assert data["total_requests"] == 0
        assert data["cache_hits"] == 0
        assert data["cache_misses"] == 0
        assert data["cache_hit_rate"] == 0.0
        assert data["total_cached_tokens"] == 0
        assert data["avg_cached_tokens_per_hit"] == 0.0

    def test_caching_stats_with_hits(self) -> None:
        """Test caching stats with cache hits and misses."""
        client = TestClient(app)

        # Mock Supabase response with extractions
        mock_response = MagicMock()
        mock_response.data = [
            {
                "processing_metadata": {
                    "cache_hit": True,
                    "cached_tokens": 500
                }
            },
            {
                "processing_metadata": {
                    "cache_hit": True,
                    "cached_tokens": 400
                }
            },
            {
                "processing_metadata": {
                    "cache_hit": False,
                    "cached_tokens": 0
                }
            },
            {
                "processing_metadata": {
                    "cache_hit": True,
                    "cached_tokens": 600
                }
            }
        ]

        with patch('app.routers.stats.get_supabase_client') as mock_get_client:
            mock_supabase = MagicMock()
            mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_supabase

            response = client.get("/api/stats/caching")

        assert response.status_code == 200
        data = response.json()

        assert data["total_requests"] == 4
        assert data["cache_hits"] == 3
        assert data["cache_misses"] == 1
        assert data["cache_hit_rate"] == 75.0
        assert data["total_cached_tokens"] == 1500  # 500 + 400 + 600
        assert data["avg_cached_tokens_per_hit"] == 500.0  # 1500 / 3

    def test_caching_stats_ignores_invalid_metadata(self) -> None:
        """Test that caching stats ignores extractions with invalid metadata."""
        client = TestClient(app)

        # Mock Supabase response with some invalid metadata
        mock_response = MagicMock()
        mock_response.data = [
            {
                "processing_metadata": {
                    "cache_hit": True,
                    "cached_tokens": 500
                }
            },
            {
                "processing_metadata": None  # Invalid: None
            },
            {
                # Missing processing_metadata entirely
            },
            {
                "processing_metadata": "not a dict"  # Invalid: string
            }
        ]

        with patch('app.routers.stats.get_supabase_client') as mock_get_client:
            mock_supabase = MagicMock()
            mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_supabase

            response = client.get("/api/stats/caching")

        assert response.status_code == 200
        data = response.json()

        # Only counts the valid extraction
        assert data["total_requests"] == 1
        assert data["cache_hits"] == 1
        assert data["cache_misses"] == 0


class TestRoutingStatsEndpoint:
    """Test GET /api/stats/routing endpoint."""

    def test_routing_stats_no_data(self) -> None:
        """Test routing stats with no extractions."""
        client = TestClient(app)

        # Mock Supabase response with no extractions
        mock_response = MagicMock()
        mock_response.data = []

        with patch('app.routers.stats.get_supabase_client') as mock_get_client:
            mock_supabase = MagicMock()
            mock_supabase.table.return_value.select.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_supabase

            response = client.get("/api/stats/routing")

        assert response.status_code == 200
        data = response.json()

        assert data["total_extractions"] == 0
        assert data["routing_distribution"] == {}
        assert data["avg_quality_score"] == 0.0
        assert data["cost_metrics"]["total_cost_usd"] == 0.0
        assert data["cost_metrics"]["savings_percent"] == 0.0
        assert data["performance_metrics"]["avg_processing_time_seconds"] == 0.0
        assert data["performance_metrics"]["p95_processing_time"] == 0.0

    def test_routing_stats_with_data(self) -> None:
        """Test routing stats with various extraction methods."""
        client = TestClient(app)

        # Mock Supabase response with extractions
        mock_response = MagicMock()
        mock_response.data = [
            {
                "processing_method": "hybrid",
                "quality_score": 0.85,
                "processing_time_seconds": 2.5,
                "cost_estimate_usd": 0.10  # Hybrid cost (20% of vision)
            },
            {
                "processing_method": "hybrid",
                "quality_score": 0.90,
                "processing_time_seconds": 2.3,
                "cost_estimate_usd": 0.08
            },
            {
                "processing_method": "vision_fallback",
                "quality_score": 0.60,
                "processing_time_seconds": 5.2,
                "cost_estimate_usd": 0.50  # Full vision cost
            },
            {
                "processing_method": "partial",
                "quality_score": 0.75,
                "processing_time_seconds": 1.8,
                "cost_estimate_usd": 0.05
            }
        ]

        with patch('app.routers.stats.get_supabase_client') as mock_get_client:
            mock_supabase = MagicMock()
            mock_supabase.table.return_value.select.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_supabase

            response = client.get("/api/stats/routing")

        assert response.status_code == 200
        data = response.json()

        assert data["total_extractions"] == 4
        assert data["routing_distribution"]["hybrid"] == 2
        assert data["routing_distribution"]["vision_fallback"] == 1
        assert data["routing_distribution"]["partial"] == 1

        # Quality score: (0.85 + 0.90 + 0.60 + 0.75) / 4 = 0.775
        assert data["avg_quality_score"] == 0.775

        # Total cost: 0.10 + 0.08 + 0.50 + 0.05 = 0.73
        assert data["cost_metrics"]["total_cost_usd"] == 0.73

        # Estimated pure vision cost: (0.10 * 5) + (0.08 * 5) + 0.50 + 0.05 = 1.45
        assert data["cost_metrics"]["estimated_pure_vision_cost_usd"] == 1.45

        # Savings: 1.45 - 0.73 = 0.72
        assert data["cost_metrics"]["total_savings_usd"] == 0.72

        # Savings percent: (0.72 / 1.45) * 100 = 49.66%
        assert abs(data["cost_metrics"]["savings_percent"] - 49.66) < 0.01

        # Average processing time: (2.5 + 2.3 + 5.2 + 1.8) / 4 = 2.95
        assert data["performance_metrics"]["avg_processing_time_seconds"] == 2.95

        # P95 processing time: sorted = [1.8, 2.3, 2.5, 5.2], p95_index = 3
        assert data["performance_metrics"]["p95_processing_time"] == 5.2

    def test_routing_stats_caching(self) -> None:
        """Test that routing stats are cached for 5 minutes."""
        client = TestClient(app)

        # Mock Supabase response
        mock_response = MagicMock()
        mock_response.data = [
            {
                "processing_method": "hybrid",
                "quality_score": 0.85,
                "processing_time_seconds": 2.5,
                "cost_estimate_usd": 0.10
            }
        ]

        with patch('app.routers.stats.get_supabase_client') as mock_get_client:
            mock_supabase = MagicMock()
            mock_supabase.table.return_value.select.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_supabase

            # First request - should hit database
            response1 = client.get("/api/stats/routing")
            assert response1.status_code == 200
            assert response1.headers.get("X-Cache-Hit") == "false"

            # Second request - should use cache
            response2 = client.get("/api/stats/routing")
            assert response2.status_code == 200
            assert response2.headers.get("X-Cache-Hit") == "true"

            # Verify database was only queried once
            assert mock_supabase.table.return_value.select.return_value.execute.call_count == 1

            # Verify responses are identical
            assert response1.json() == response2.json()

    def test_routing_stats_handles_nulls(self) -> None:
        """Test that routing stats handles null values gracefully."""
        client = TestClient(app)

        # Mock Supabase response with some null values
        mock_response = MagicMock()
        mock_response.data = [
            {
                "processing_method": "hybrid",
                "quality_score": 0.85,
                "processing_time_seconds": None,  # Null
                "cost_estimate_usd": None  # Null
            },
            {
                "processing_method": "vision_fallback",
                "quality_score": None,  # Null
                "processing_time_seconds": 3.5,
                "cost_estimate_usd": 0.50
            }
        ]

        with patch('app.routers.stats.get_supabase_client') as mock_get_client:
            mock_supabase = MagicMock()
            mock_supabase.table.return_value.select.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_supabase

            response = client.get("/api/stats/routing")

        assert response.status_code == 200
        data = response.json()

        # Should handle nulls gracefully
        assert data["total_extractions"] == 2
        assert data["routing_distribution"]["hybrid"] == 1
        assert data["routing_distribution"]["vision_fallback"] == 1

        # Quality score only includes non-null: 0.85
        assert data["avg_quality_score"] == 0.85

        # Cost only includes non-null: 0.50
        assert data["cost_metrics"]["total_cost_usd"] == 0.50

        # Processing time only includes non-null: 3.5
        assert data["performance_metrics"]["avg_processing_time_seconds"] == 3.5
