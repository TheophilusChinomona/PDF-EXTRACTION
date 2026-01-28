"""Webhook notification service for extraction events.

This module provides webhook delivery with HMAC-SHA256 signatures,
HTTPS validation, and retry logic for reliable notification delivery.
"""

import hmac
import hashlib
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, UTC
import asyncio

import httpx

from app.config import get_settings


logger = logging.getLogger(__name__)


async def send_webhook(
    webhook_url: str,
    payload: Dict[str, Any],
    signature_key: Optional[str] = None,
    max_retries: int = 3,
    timeout_seconds: int = 30
) -> bool:
    """Send webhook notification with HMAC signature and retry logic.

    Args:
        webhook_url: Target webhook URL (must be HTTPS)
        payload: Webhook payload data
        signature_key: Secret key for HMAC signature (uses GEMINI_API_KEY if not provided)
        max_retries: Number of retry attempts on failure (default: 3)
        timeout_seconds: Request timeout in seconds (default: 30)

    Returns:
        bool: True if webhook delivered successfully, False otherwise

    Raises:
        ValueError: If webhook_url is not HTTPS
    """
    # Validate HTTPS
    if not webhook_url.startswith('https://'):
        raise ValueError(f"Webhook URL must use HTTPS, got: {webhook_url}")

    # Use GEMINI_API_KEY as default signature key
    if signature_key is None:
        settings = get_settings()
        signature_key = settings.gemini_api_key

    # Convert payload to JSON
    payload_json = json.dumps(payload, default=str)
    payload_bytes = payload_json.encode('utf-8')

    # Generate HMAC-SHA256 signature
    signature = hmac.new(
        signature_key.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

    # Prepare headers
    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Signature': signature,
        'User-Agent': 'PDF-Extraction-Service/1.0'
    }

    # Retry with exponential backoff
    retry_delays = [1, 2, 4]  # seconds
    last_error = None

    for attempt in range(max_retries):
        try:
            logger.info(f"Sending webhook to {webhook_url} (attempt {attempt + 1}/{max_retries})")

            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(
                    webhook_url,
                    content=payload_bytes,
                    headers=headers
                )

                # Log response
                logger.info(
                    f"Webhook delivery: status={response.status_code}, "
                    f"url={webhook_url}, attempt={attempt + 1}"
                )

                # Consider 2xx status codes as success
                if 200 <= response.status_code < 300:
                    return True

                # Log non-2xx responses
                logger.warning(
                    f"Webhook returned non-2xx status: {response.status_code}, "
                    f"body={response.text[:200]}"
                )
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"

        except httpx.TimeoutException as e:
            logger.warning(f"Webhook timeout on attempt {attempt + 1}: {str(e)}")
            last_error = f"Timeout: {str(e)}"

        except Exception as e:
            logger.warning(f"Webhook error on attempt {attempt + 1}: {str(e)}")
            last_error = str(e)

        # Wait before retry (except on last attempt)
        if attempt < max_retries - 1:
            delay = retry_delays[attempt]
            logger.info(f"Retrying webhook in {delay} seconds...")
            await asyncio.sleep(delay)

    # All retries failed
    logger.error(f"Webhook delivery failed after {max_retries} attempts: {last_error}")
    return False


async def send_extraction_completed_webhook(
    webhook_url: str,
    extraction_id: str,
    status: str,
    data: Optional[Dict[str, Any]] = None
) -> bool:
    """Send extraction.completed webhook event.

    Args:
        webhook_url: Target webhook URL
        extraction_id: UUID of the extraction
        status: Extraction status ('completed', 'failed', 'partial')
        data: Optional extraction data (summary, not full result)

    Returns:
        bool: True if webhook delivered successfully, False otherwise
    """
    payload = {
        'event': 'extraction.completed',
        'extraction_id': extraction_id,
        'status': status,
        'data': data or {},
        'timestamp': datetime.now(UTC).isoformat()
    }

    try:
        return await send_webhook(webhook_url, payload)
    except ValueError as e:
        logger.error(f"Invalid webhook URL: {str(e)}")
        return False


async def send_batch_completed_webhook(
    webhook_url: str,
    batch_job_id: str,
    status: str,
    summary: Dict[str, Any]
) -> bool:
    """Send batch.completed webhook event.

    Args:
        webhook_url: Target webhook URL
        batch_job_id: UUID of the batch job
        status: Batch job status ('completed', 'failed', 'partial')
        summary: Batch job summary data

    Returns:
        bool: True if webhook delivered successfully, False otherwise
    """
    payload = {
        'event': 'batch.completed',
        'batch_job_id': batch_job_id,
        'status': status,
        'summary': summary,
        'timestamp': datetime.now(UTC).isoformat()
    }

    try:
        return await send_webhook(webhook_url, payload)
    except ValueError as e:
        logger.error(f"Invalid webhook URL: {str(e)}")
        return False
