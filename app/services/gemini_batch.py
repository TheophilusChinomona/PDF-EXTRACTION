"""
Gemini Batch API service.

Provides create, poll, and result-download for Gemini Batch API jobs.
Used for validation and extraction at 50% cost with ~24h turnaround.
"""

import asyncio
import json
import logging
import tempfile
from dataclasses import dataclass, field
from typing import Any

from google import genai

logger = logging.getLogger(__name__)

# ~20MB threshold for inline vs JSONL (Batch API docs)
INLINE_SIZE_LIMIT_BYTES = 20 * 1024 * 1024

# Terminal batch job states
TERMINAL_STATES = frozenset({
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
})


@dataclass
class BatchResponseItem:
    """Single response from a batch job (per key)."""

    key: str
    response_text: str | None = None
    error: str | None = None


@dataclass
class BatchJobResult:
    """Result of a completed batch job (from batches.get)."""

    name: str
    state: str
    dest: Any = None  # inlined_responses or file_name
    error: Any = None


def _estimate_request_size(request: dict) -> int:
    """Rough size in bytes of a single request dict (for inline vs JSONL decision)."""
    return len(json.dumps(request).encode("utf-8"))


async def create_batch_job(
    client: genai.Client,
    keyed_requests: list[dict],
    model: str = "models/gemini-2.5-flash",
    display_name: str | None = None,
) -> str:
    """Submit a batch job (inline or JSONL based on total size).

    Args:
        client: Gemini API client.
        keyed_requests: List of {"key": str, "request": GenerateContentRequest}.
            Each "request" is a dict with "contents" and optionally "config".
        model: Model name for the batch (e.g. models/gemini-2.5-flash).
        display_name: Optional display name for the job.

    Returns:
        Job name (e.g. batches/123456) from the API.

    Raises:
        ValueError: If keyed_requests is empty.
    """
    if not keyed_requests:
        raise ValueError("keyed_requests must not be empty")

    total_size = sum(
        _estimate_request_size(item.get("request", {})) for item in keyed_requests
    )
    use_inline = total_size <= INLINE_SIZE_LIMIT_BYTES

    config: dict[str, Any] = {}
    if display_name:
        config["display_name"] = display_name

    if use_inline:
        # Inline: list of GenerateContentRequest (no key in request; order preserved)
        inline_requests = [item["request"] for item in keyed_requests]
        job = await asyncio.to_thread(
            client.batches.create,
            model=model,
            src=inline_requests,
            config=config,
        )
    else:
        # JSONL: write temp file, upload, create from file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".jsonl",
            delete=False,
            encoding="utf-8",
        ) as f:
            for item in keyed_requests:
                f.write(json.dumps(item) + "\n")
            jsonl_path = f.name

        try:
            uploaded = await asyncio.to_thread(
                client.files.upload,
                file=jsonl_path,
                config={"mime_type": "application/jsonl"},
            )
            job = await asyncio.to_thread(
                client.batches.create,
                model=model,
                src=uploaded.name,
                config=config,
            )
        finally:
            import os
            try:
                os.unlink(jsonl_path)
            except OSError as e:
                logger.warning("Failed to remove temp JSONL %s: %s", jsonl_path, e)

    if job.name is None:
        raise ValueError("Batch job created but name is None")
    return job.name


async def poll_batch_job(
    client: genai.Client,
    job_name: str,
    timeout_seconds: int = 86400,
    poll_interval: int = 60,
) -> BatchJobResult:
    """Poll until terminal state. Returns job with results metadata.

    Args:
        client: Gemini API client.
        job_name: Job name (e.g. batches/123456).
        timeout_seconds: Max time to poll (default 24h).
        poll_interval: Seconds between polls.

    Returns:
        BatchJobResult with name, state, dest (for results), error.

    Raises:
        TimeoutError: If job does not reach terminal state within timeout.
    """
    import time
    deadline = time.monotonic() + timeout_seconds
    state_attr = "state"

    while True:
        batch_job = await asyncio.to_thread(client.batches.get, name=job_name)
        state = getattr(batch_job, state_attr, None)
        if state is not None and hasattr(state, "name"):
            state_str = state.name
        else:
            state_str = str(state) if state else "UNKNOWN"

        if state_str in TERMINAL_STATES:
            dest = getattr(batch_job, "dest", None)
            err = getattr(batch_job, "error", None)
            return BatchJobResult(name=job_name, state=state_str, dest=dest, error=err)

        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Batch job {job_name} did not complete within {timeout_seconds}s (last state: {state_str})"
            )

        logger.info("Batch job %s state=%s, waiting %ds", job_name, state_str, poll_interval)
        await asyncio.sleep(poll_interval)


async def download_batch_results(
    client: genai.Client,
    job: BatchJobResult,
    keys_in_order: list[str] | None = None,
) -> list[BatchResponseItem]:
    """Parse batch job results (inline or file) into list of BatchResponseItem.

    Args:
        client: Gemini API client.
        job: Completed BatchJobResult from poll_batch_job.
        keys_in_order: For inline results, order of keys matching request order.
            If None and job has file output, keys come from each JSONL line.

    Returns:
        List of BatchResponseItem (key, response_text or error).
    """
    items: list[BatchResponseItem] = []

    if job.dest is None:
        return items

    # Inline responses: order matches request order
    inlined = getattr(job.dest, "inlined_responses", None)
    if inlined is not None and keys_in_order is not None:
        for i, key in enumerate(keys_in_order):
            if i >= len(inlined):
                items.append(BatchResponseItem(key=key, error="Missing response"))
                continue
            resp = inlined[i]
            err = getattr(resp, "error", None)
            if err:
                items.append(BatchResponseItem(key=key, error=str(err)))
                continue
            r = getattr(resp, "response", None)
            if r is not None:
                text = getattr(r, "text", None)
                items.append(BatchResponseItem(key=key, response_text=text or ""))
            else:
                items.append(BatchResponseItem(key=key, error="Empty response"))
        return items

    # File output: download JSONL and parse by key
    file_name = getattr(job.dest, "file_name", None)
    if file_name:
        content = await asyncio.to_thread(client.files.download, file=file_name)
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSONL line: %s", e)
                continue
            key = parsed.get("key")
            if key is None:
                continue
            if "error" in parsed:
                items.append(BatchResponseItem(key=key, error=str(parsed["error"])))
                continue
            resp = parsed.get("response", {})
            if resp and "candidates" in resp and resp["candidates"]:
                parts = resp["candidates"][0].get("content", {}).get("parts", [])
                text = ""
                for p in parts:
                    if "text" in p:
                        text += p.get("text", "")
                items.append(BatchResponseItem(key=key, response_text=text))
            else:
                items.append(BatchResponseItem(key=key, error="No candidates in response"))
        return items

    return items


async def build_validation_request(
    client: genai.Client,
    pdf_content: bytes,
    filename: str,
    user_prompt: str,
    system_instruction: str,
    response_schema: dict[str, Any],
) -> tuple[dict, str]:
    """Upload PDF to File API and build a single validation GenerateContentRequest.

    Returns (request_dict, uploaded_file_name). Caller can use file_name for cleanup.
    """
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_content)
        path = f.name
    try:
        uploaded = await asyncio.to_thread(client.files.upload, file=path)
        name = uploaded.name if hasattr(uploaded, "name") else str(uploaded)
        # Use full URI for Batch API (not just the file name)
        file_uri = uploaded.uri if hasattr(uploaded, "uri") else name
        # Request: one user content with file + text parts; config = response_schema
        request = {
            "contents": [
                {
                    "parts": [
                        {"file_data": {"file_uri": file_uri}},
                        {"text": user_prompt},
                    ],
                    "role": "user",
                }
            ],
            "config": {
                "system_instruction": {"parts": [{"text": system_instruction}]},
                "response_mime_type": "application/json",
                "response_schema": response_schema,
                "temperature": 0,
            },
        }
        return request, name
    finally:
        import os
        try:
            os.unlink(path)
        except OSError:
            pass


async def build_extraction_request(
    client: genai.Client,
    pdf_content: bytes,
    filename: str,
    doc_type: str,
    user_prompt: str,
    system_instruction: str,
    response_schema: dict[str, Any],
) -> tuple[dict, str]:
    """Upload PDF to File API and build a single extraction GenerateContentRequest.

    Returns (request_dict, uploaded_file_name). doc_type is 'memo' or 'question_paper'.
    """
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_content)
        path = f.name
    try:
        uploaded = await asyncio.to_thread(client.files.upload, file=path)
        name = uploaded.name if hasattr(uploaded, "name") else str(uploaded)
        # Use full URI for Batch API (not just the file name)
        file_uri = uploaded.uri if hasattr(uploaded, "uri") else name
        request = {
            "contents": [
                {
                    "parts": [
                        {"file_data": {"file_uri": file_uri}},
                        {"text": user_prompt},
                    ],
                    "role": "user",
                }
            ],
            "config": {
                "system_instruction": {"parts": [{"text": system_instruction}]},
                "response_mime_type": "application/json",
                "response_schema": response_schema,
                "temperature": 0,
            },
        }
        return request, name
    finally:
        import os
        try:
            os.unlink(path)
        except OSError:
            pass
