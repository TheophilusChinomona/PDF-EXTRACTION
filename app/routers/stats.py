"""
Statistics and analytics API endpoints.

Provides endpoints for caching statistics and routing performance metrics.
"""

import time
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, Response, HTTPException, status

from app.db.supabase_client import get_supabase_client
from app.middleware.rate_limit import get_limiter

router = APIRouter(prefix="/api/stats", tags=["statistics"])
limiter = get_limiter()

# Cache for routing statistics (5-minute TTL)
_routing_stats_cache: Optional[Dict[str, Any]] = None
_routing_stats_cache_time: float = 0
_ROUTING_STATS_CACHE_TTL = 300  # 5 minutes in seconds


@router.get("/caching", status_code=status.HTTP_200_OK)
@limiter.limit("100/minute")  # type: ignore[untyped-decorator]
async def get_caching_stats(request: Request) -> Response:
    """
    Get context caching statistics showing cache hit rate and cost savings.

    This endpoint aggregates cache usage data from all completed extractions,
    calculating the cache hit rate and estimated token savings from caching.

    Returns:
        200: JSON with caching statistics including:
            - total_requests: Total number of extraction requests
            - cache_hits: Number of requests that used cached content
            - cache_misses: Number of requests without cache hits
            - cache_hit_rate: Percentage of requests with cache hits (0-100)
            - total_cached_tokens: Total tokens saved via caching
            - avg_cached_tokens_per_hit: Average tokens cached per hit
        500: Database error

    Example response:
        {
            "total_requests": 1000,
            "cache_hits": 850,
            "cache_misses": 150,
            "cache_hit_rate": 85.0,
            "total_cached_tokens": 425000,
            "avg_cached_tokens_per_hit": 500.0
        }

    Raises:
        HTTPException: Database query errors
    """
    supabase_client = get_supabase_client()

    try:
        # Query all completed extractions (exclude pending/failed without results)
        response = supabase_client.table('extractions').select(
            'processing_metadata'
        ).in_('status', ['completed', 'partial']).execute()

        extractions = response.data

        # Calculate cache statistics
        total_requests = 0
        cache_hits = 0
        cache_misses = 0
        total_cached_tokens = 0

        for extraction in extractions:
            metadata = extraction.get('processing_metadata')
            if not metadata or not isinstance(metadata, dict):
                continue

            total_requests += 1

            # Check if cache was used
            cache_hit = metadata.get('cache_hit', False)
            cached_tokens = metadata.get('cached_tokens', 0)

            if cache_hit:
                cache_hits += 1
                total_cached_tokens += cached_tokens
            else:
                cache_misses += 1

        # Calculate derived metrics
        cache_hit_rate = (cache_hits / total_requests * 100) if total_requests > 0 else 0.0
        avg_cached_tokens_per_hit = (total_cached_tokens / cache_hits) if cache_hits > 0 else 0.0

        # Build response
        stats = {
            "total_requests": total_requests,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "cache_hit_rate": round(cache_hit_rate, 2),
            "total_cached_tokens": total_cached_tokens,
            "avg_cached_tokens_per_hit": round(avg_cached_tokens_per_hit, 2)
        }

        import json
        return Response(
            content=json.dumps(stats),
            media_type="application/json",
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )


@router.get("/routing", status_code=status.HTTP_200_OK)
@limiter.limit("100/minute")  # type: ignore[untyped-decorator]
async def get_routing_stats(request: Request) -> Response:
    """
    Get routing statistics showing distribution of processing methods and cost savings.

    This endpoint provides insights into how the hybrid extraction pipeline routes
    PDFs between different processing methods, along with cost and performance metrics.
    Results are cached for 5 minutes to reduce database load.

    Returns:
        200: JSON with routing and cost statistics including:
            - total_extractions: Total number of extractions
            - routing_distribution: Count by processing_method (hybrid, vision_fallback, partial)
            - avg_quality_score: Average OpenDataLoader quality score
            - cost_metrics:
                - total_cost_usd: Total API cost
                - estimated_pure_vision_cost_usd: Cost if all used Vision API
                - total_savings_usd: Money saved via hybrid routing
                - savings_percent: Percentage cost reduction
            - performance_metrics:
                - avg_processing_time_seconds: Average processing time
                - p95_processing_time: 95th percentile processing time
        500: Database error

    Example response:
        {
            "total_extractions": 1000,
            "routing_distribution": {
                "hybrid": 800,
                "vision_fallback": 150,
                "partial": 50
            },
            "avg_quality_score": 0.82,
            "cost_metrics": {
                "total_cost_usd": 12.50,
                "estimated_pure_vision_cost_usd": 62.50,
                "total_savings_usd": 50.00,
                "savings_percent": 80.0
            },
            "performance_metrics": {
                "avg_processing_time_seconds": 2.3,
                "p95_processing_time": 5.1
            }
        }

    Raises:
        HTTPException: Database query errors
    """
    global _routing_stats_cache, _routing_stats_cache_time

    # Check if cache is valid (within 5-minute TTL)
    current_time = time.time()
    if _routing_stats_cache and (current_time - _routing_stats_cache_time) < _ROUTING_STATS_CACHE_TTL:
        import json
        return Response(
            content=json.dumps(_routing_stats_cache),
            media_type="application/json",
            status_code=status.HTTP_200_OK,
            headers={"X-Cache-Hit": "true"}
        )

    supabase_client = get_supabase_client()

    try:
        # Query all extractions with relevant fields
        response = supabase_client.table('extractions').select(
            'processing_method, quality_score, processing_time_seconds, cost_estimate_usd'
        ).execute()

        extractions = response.data

        # Initialize counters
        total_extractions = len(extractions)
        routing_distribution: Dict[str, int] = {}
        quality_scores: list[float] = []
        processing_times: list[float] = []
        total_cost_usd = 0.0
        estimated_pure_vision_cost_usd = 0.0

        for extraction in extractions:
            # Count routing distribution
            method = extraction.get('processing_method', 'unknown')
            routing_distribution[method] = routing_distribution.get(method, 0) + 1

            # Collect quality scores
            quality_score = extraction.get('quality_score')
            if quality_score is not None:
                quality_scores.append(float(quality_score))

            # Collect processing times
            processing_time = extraction.get('processing_time_seconds')
            if processing_time is not None:
                processing_times.append(float(processing_time))

            # Calculate cost metrics
            cost = extraction.get('cost_estimate_usd')
            if cost is not None:
                cost_float = float(cost)
                total_cost_usd += cost_float

                # Estimate pure vision cost (hybrid saves 80%, so multiply by 5)
                if method == 'hybrid':
                    estimated_pure_vision_cost_usd += cost_float * 5
                else:
                    # Vision fallback or partial - already full cost
                    estimated_pure_vision_cost_usd += cost_float

        # Calculate average quality score
        avg_quality_score = (sum(quality_scores) / len(quality_scores)) if quality_scores else 0.0

        # Calculate cost savings
        total_savings_usd = estimated_pure_vision_cost_usd - total_cost_usd
        savings_percent = (
            (total_savings_usd / estimated_pure_vision_cost_usd * 100)
            if estimated_pure_vision_cost_usd > 0 else 0.0
        )

        # Calculate performance metrics
        avg_processing_time = (sum(processing_times) / len(processing_times)) if processing_times else 0.0

        # Calculate p95 processing time
        p95_processing_time = 0.0
        if processing_times:
            sorted_times = sorted(processing_times)
            p95_index = int(len(sorted_times) * 0.95)
            if p95_index < len(sorted_times):
                p95_processing_time = sorted_times[p95_index]

        # Build response
        stats = {
            "total_extractions": total_extractions,
            "routing_distribution": routing_distribution,
            "avg_quality_score": round(avg_quality_score, 3),
            "cost_metrics": {
                "total_cost_usd": round(total_cost_usd, 6),
                "estimated_pure_vision_cost_usd": round(estimated_pure_vision_cost_usd, 6),
                "total_savings_usd": round(total_savings_usd, 6),
                "savings_percent": round(savings_percent, 2)
            },
            "performance_metrics": {
                "avg_processing_time_seconds": round(avg_processing_time, 3),
                "p95_processing_time": round(p95_processing_time, 3)
            }
        }

        # Update cache
        _routing_stats_cache = stats
        _routing_stats_cache_time = current_time

        import json
        return Response(
            content=json.dumps(stats),
            media_type="application/json",
            status_code=status.HTTP_200_OK,
            headers={"X-Cache-Hit": "false"}
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
