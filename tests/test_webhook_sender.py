"""Tests for webhook notification service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import httpx

from app.services.webhook_sender import (
    send_webhook,
    send_extraction_completed_webhook,
    send_batch_completed_webhook,
)


@pytest.mark.asyncio
async def test_send_webhook_success():
    """Test successful webhook delivery."""
    webhook_url = "https://example.com/webhook"
    payload = {"event": "test", "data": "value"}

    with patch("app.services.webhook_sender.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        result = await send_webhook(webhook_url, payload, signature_key="test-key")

        assert result is True
        mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_send_webhook_non_https():
    """Test webhook validation rejects non-HTTPS URLs."""
    webhook_url = "http://example.com/webhook"
    payload = {"event": "test"}

    with pytest.raises(ValueError, match="must use HTTPS"):
        await send_webhook(webhook_url, payload, signature_key="test-key")


@pytest.mark.asyncio
async def test_send_webhook_timeout_with_retry():
    """Test webhook retry on timeout."""
    webhook_url = "https://example.com/webhook"
    payload = {"event": "test"}

    with patch("app.services.webhook_sender.httpx.AsyncClient") as mock_client_class:
        with patch("app.services.webhook_sender.asyncio.sleep", new_callable=AsyncMock):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await send_webhook(
                webhook_url,
                payload,
                signature_key="test-key",
                max_retries=2
            )

            assert result is False
            assert mock_client.post.call_count == 2  # Initial + 1 retry


@pytest.mark.asyncio
async def test_send_webhook_non_2xx_status():
    """Test webhook retry on non-2xx status."""
    webhook_url = "https://example.com/webhook"
    payload = {"event": "test"}

    with patch("app.services.webhook_sender.httpx.AsyncClient") as mock_client_class:
        with patch("app.services.webhook_sender.asyncio.sleep", new_callable=AsyncMock):
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await send_webhook(
                webhook_url,
                payload,
                signature_key="test-key",
                max_retries=2
            )

            assert result is False
            assert mock_client.post.call_count == 2  # Initial + 1 retry


@pytest.mark.asyncio
async def test_send_webhook_eventual_success():
    """Test webhook succeeds after retries."""
    webhook_url = "https://example.com/webhook"
    payload = {"event": "test"}

    with patch("app.services.webhook_sender.httpx.AsyncClient") as mock_client_class:
        with patch("app.services.webhook_sender.asyncio.sleep", new_callable=AsyncMock):
            mock_client = AsyncMock()

            # First call fails, second succeeds
            mock_response_fail = MagicMock()
            mock_response_fail.status_code = 500
            mock_response_fail.text = "Error"

            mock_response_success = MagicMock()
            mock_response_success.status_code = 200

            mock_client.post = AsyncMock(side_effect=[mock_response_fail, mock_response_success])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await send_webhook(
                webhook_url,
                payload,
                signature_key="test-key",
                max_retries=3
            )

            assert result is True
            assert mock_client.post.call_count == 2  # Initial + 1 retry


@pytest.mark.asyncio
async def test_send_webhook_signature_generation():
    """Test HMAC signature is generated and added to headers."""
    webhook_url = "https://example.com/webhook"
    payload = {"event": "test"}
    signature_key = "my-secret-key"

    with patch("app.services.webhook_sender.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        await send_webhook(webhook_url, payload, signature_key=signature_key)

        # Verify signature header was included
        call_args = mock_client.post.call_args
        headers = call_args.kwargs['headers']
        assert 'X-Webhook-Signature' in headers
        assert len(headers['X-Webhook-Signature']) == 64  # SHA-256 hex digest length


@pytest.mark.asyncio
async def test_send_extraction_completed_webhook():
    """Test extraction completed webhook helper."""
    webhook_url = "https://example.com/webhook"
    extraction_id = "123e4567-e89b-12d3-a456-426614174000"
    status = "completed"
    data = {"file_name": "test.pdf"}

    with patch("app.services.webhook_sender.send_webhook", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        result = await send_extraction_completed_webhook(
            webhook_url,
            extraction_id,
            status,
            data
        )

        assert result is True
        mock_send.assert_called_once()

        # Verify payload structure
        call_args = mock_send.call_args
        payload = call_args[0][1]  # Second positional arg is payload
        assert payload['event'] == 'extraction.completed'
        assert payload['extraction_id'] == extraction_id
        assert payload['status'] == status
        assert 'timestamp' in payload


@pytest.mark.asyncio
async def test_send_batch_completed_webhook():
    """Test batch completed webhook helper."""
    webhook_url = "https://example.com/webhook"
    batch_job_id = "123e4567-e89b-12d3-a456-426614174000"
    status = "completed"
    summary = {
        'total_files': 5,
        'completed_files': 4,
        'failed_files': 1
    }

    with patch("app.services.webhook_sender.send_webhook", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        result = await send_batch_completed_webhook(
            webhook_url,
            batch_job_id,
            status,
            summary
        )

        assert result is True
        mock_send.assert_called_once()

        # Verify payload structure
        call_args = mock_send.call_args
        payload = call_args[0][1]
        assert payload['event'] == 'batch.completed'
        assert payload['batch_job_id'] == batch_job_id
        assert payload['status'] == status
        assert payload['summary'] == summary
        assert 'timestamp' in payload


@pytest.mark.asyncio
async def test_send_extraction_completed_webhook_invalid_url():
    """Test extraction webhook with invalid URL."""
    webhook_url = "http://example.com/webhook"  # HTTP not HTTPS
    extraction_id = "123e4567-e89b-12d3-a456-426614174000"

    result = await send_extraction_completed_webhook(
        webhook_url,
        extraction_id,
        "completed",
        {}
    )

    # Should return False on error, not raise exception
    assert result is False
