"""Unit tests for Gemini Batch API module (create, poll, download_batch_results)."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio

from app.services.gemini_batch import (
    create_batch_job,
    poll_batch_job,
    download_batch_results,
    BatchJobResult,
    BatchResponseItem,
    TERMINAL_STATES,
    INLINE_SIZE_LIMIT_BYTES,
)


class TestCreateBatchJob:
    """Tests for create_batch_job."""

    @pytest.mark.asyncio
    async def test_create_batch_job_inline_returns_job_name(self):
        """Inline path: create returns job name."""
        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.name = "batches/123"
        mock_client.batches.create.return_value = mock_job

        keyed = [
            {"key": "k1", "request": {"contents": [{"parts": [{"text": "hi"}], "role": "user"}]}},
            {"key": "k2", "request": {"contents": [{"parts": [{"text": "bye"}], "role": "user"}]}},
        ]
        with patch("app.services.gemini_batch.asyncio.to_thread", new_callable=AsyncMock) as m_to_thread:
            m_to_thread.return_value = mock_job
            name = await create_batch_job(mock_client, keyed, display_name="test")
        assert name == "batches/123"
        m_to_thread.assert_called_once()
        kwargs = m_to_thread.call_args[1]
        assert kwargs.get("model") == "models/gemini-2.5-flash"
        assert kwargs.get("src") == [{"contents": [{"parts": [{"text": "hi"}], "role": "user"}]}, {"contents": [{"parts": [{"text": "bye"}], "role": "user"}]}]
        assert kwargs.get("config") == {"display_name": "test"}

    @pytest.mark.asyncio
    async def test_create_batch_job_empty_raises(self):
        """Empty keyed_requests raises ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            await create_batch_job(MagicMock(), [], model="models/gemini-2.5-flash")


class TestPollBatchJob:
    """Tests for poll_batch_job."""

    @pytest.mark.asyncio
    async def test_poll_returns_immediately_when_terminal(self):
        """When first get() returns terminal state, return immediately."""
        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.dest = None
        mock_job.error = None
        state = MagicMock()
        state.name = "JOB_STATE_SUCCEEDED"
        mock_job.state = state

        with patch("app.services.gemini_batch.asyncio.to_thread", new_callable=AsyncMock) as m:
            m.return_value = mock_job
            result = await poll_batch_job(mock_client, "batches/123", timeout_seconds=10, poll_interval=1)
        assert result.name == "batches/123"
        assert result.state == "JOB_STATE_SUCCEEDED"
        assert m.call_count == 1

    @pytest.mark.asyncio
    async def test_poll_waits_until_terminal(self):
        """Poll until state is terminal."""
        mock_client = MagicMock()
        running = MagicMock()
        running.name = "JOB_STATE_RUNNING"
        succeeded = MagicMock()
        succeeded.name = "JOB_STATE_SUCCEEDED"
        mock_job_running = MagicMock()
        mock_job_running.state = running
        mock_job_running.dest = None
        mock_job_running.error = None
        mock_job_done = MagicMock()
        mock_job_done.state = succeeded
        mock_job_done.dest = None
        mock_job_done.error = None

        with patch("app.services.gemini_batch.asyncio.to_thread", new_callable=AsyncMock) as m:
            with patch("app.services.gemini_batch.asyncio.sleep", new_callable=AsyncMock):
                m.side_effect = [mock_job_running, mock_job_done]
                result = await poll_batch_job(mock_client, "batches/123", timeout_seconds=60, poll_interval=1)
        assert result.state == "JOB_STATE_SUCCEEDED"
        assert m.call_count == 2


class TestDownloadBatchResults:
    """Tests for download_batch_results."""

    @pytest.mark.asyncio
    async def test_download_inline_with_keys(self):
        """Inline responses: keys_in_order maps to responses."""
        mock_client = MagicMock()
        r1 = MagicMock()
        r1.error = None
        r1.response = MagicMock()
        r1.response.text = '{"subject":"Math"}'
        r2 = MagicMock()
        r2.error = None
        r2.response = MagicMock()
        r2.response.text = '{"subject":"Sci"}'
        dest = MagicMock()
        dest.inlined_responses = [r1, r2]
        dest.file_name = None
        job = BatchJobResult(name="batches/1", state="JOB_STATE_SUCCEEDED", dest=dest)

        items = await download_batch_results(mock_client, job, keys_in_order=["id1", "id2"])
        assert len(items) == 2
        assert items[0].key == "id1"
        assert items[0].response_text == '{"subject":"Math"}'
        assert items[0].error is None
        assert items[1].key == "id2"
        assert items[1].response_text == '{"subject":"Sci"}'

    @pytest.mark.asyncio
    async def test_download_inline_error_per_item(self):
        """Inline: one response has error."""
        mock_client = MagicMock()
        r1 = MagicMock()
        r1.error = "Something failed"
        r1.response = None
        dest = MagicMock()
        dest.inlined_responses = [r1]
        dest.file_name = None
        job = BatchJobResult(name="batches/1", state="JOB_STATE_SUCCEEDED", dest=dest)

        items = await download_batch_results(mock_client, job, keys_in_order=["k1"])
        assert len(items) == 1
        assert items[0].key == "k1"
        assert items[0].error == "Something failed"
        assert items[0].response_text is None

    @pytest.mark.asyncio
    async def test_download_file_jsonl(self):
        """File output: download and parse JSONL."""
        mock_client = MagicMock()
        line1 = '{"key":"a","response":{"candidates":[{"content":{"parts":[{"text":"result A"}]}}]}}'
        line2 = '{"key":"b","error":"per-request error"}'
        content = (line1 + "\n" + line2).encode("utf-8")
        with patch("app.services.gemini_batch.asyncio.to_thread", new_callable=AsyncMock) as m:
            m.return_value = content
            dest = MagicMock()
            dest.inlined_responses = None
            dest.file_name = "files/result.jsonl"
            job = BatchJobResult(name="batches/1", state="JOB_STATE_SUCCEEDED", dest=dest)

            items = await download_batch_results(mock_client, job, keys_in_order=None)
        assert len(items) == 2
        assert items[0].key == "a"
        assert items[0].response_text == "result A"
        assert items[1].key == "b"
        assert items[1].error == "per-request error"


class TestConstants:
    """Test terminal states and size limit."""

    def test_terminal_states_include_expected(self):
        assert "JOB_STATE_SUCCEEDED" in TERMINAL_STATES
        assert "JOB_STATE_FAILED" in TERMINAL_STATES
        assert "JOB_STATE_CANCELLED" in TERMINAL_STATES
        assert "JOB_STATE_EXPIRED" in TERMINAL_STATES

    def test_inline_size_limit_is_20mb(self):
        assert INLINE_SIZE_LIMIT_BYTES == 20 * 1024 * 1024
