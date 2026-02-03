"""
PGMQ (Postgres Message Queue) client for validation and extraction queues.

Uses asyncpg for async operations. Connection pooling and visibility timeout
handling for message locking. Dead letter queue support for failed messages.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

# Lazy import to avoid requiring asyncpg when PGMQ is not configured
_pool: Any = None


async def _get_pool():
    """Return asyncpg connection pool; create if needed. Requires PGMQ_DATABASE_URL."""
    global _pool
    if _pool is not None:
        return _pool
    settings = get_settings()
    url = getattr(settings, "pgmq_database_url", None) or getattr(
        settings, "database_url", None
    )
    if not url:
        raise ValueError(
            "PGMQ requires pgmq_database_url (or database_url) to be set. "
            "Use a Postgres connection URL (postgresql://...)."
        )
    try:
        import asyncpg
    except ImportError:
        raise ImportError(
            "PGMQ client requires asyncpg. Install with: pip install asyncpg"
        ) from None
    _pool = await asyncpg.create_pool(
        url,
        min_size=1,
        max_size=10,
        command_timeout=60,
    )
    return _pool


async def init_pgmq_pool() -> None:
    """Create PGMQ connection pool at startup. No-op if pgmq_database_url is unset."""
    settings = get_settings()
    if not getattr(settings, "pgmq_database_url", None) and not getattr(
        settings, "database_url", None
    ):
        return
    try:
        await _get_pool()
        logger.info("PGMQ connection pool initialized")
    except Exception as e:
        logger.warning("PGMQ pool init skipped: %s", e)


async def close_pgmq_pool() -> None:
    """Close PGMQ connection pool at shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PGMQ connection pool closed")


def _queue_name(queue: str) -> str:
    settings = get_settings()
    if queue == "validation":
        return settings.pgmq_validation_queue
    if queue == "extraction":
        return settings.pgmq_extraction_queue
    if queue == "dead_letter":
        return settings.pgmq_dead_letter_queue
    return queue


async def send(queue: str, msg: Dict[str, Any], delay: int = 0) -> Optional[int]:
    """
    Send a message to a named queue. Queue can be 'validation', 'extraction', or raw name.

    Returns:
        Message ID (bigint) or None if send failed.
    """
    pool = await _get_pool()
    q = _queue_name(queue)
    msg_json = json.dumps(msg) if isinstance(msg, dict) else msg
    row = await pool.fetchrow(
        "SELECT pgmq.send($1::text, $2::jsonb, $3::int) AS msg_id",
        q,
        msg_json,
        delay,
    )
    if row is not None:
        msg_id = row["msg_id"] if "msg_id" in row.keys() else (row[0] if len(row) else None)
        if msg_id is not None:
            return int(msg_id)
    return None


async def read(
    queue: str,
    vt_seconds: Optional[int] = None,
    qty: int = 1,
) -> List[Dict[str, Any]]:
    """
    Read up to qty messages from the queue. Visibility timeout (vt) hides
    messages from other consumers for vt_seconds.

    Returns:
        List of dicts with keys: msg_id, read_ct, enqueued_at, vt, message.
    """
    pool = await _get_pool()
    settings = get_settings()
    vt = vt_seconds if vt_seconds is not None else settings.pgmq_visibility_timeout_seconds
    q = _queue_name(queue)
    rows = await pool.fetch(
        "SELECT msg_id, read_ct, enqueued_at, vt, message FROM pgmq.read($1::text, $2::int, $3::int)",
        q,
        vt,
        qty,
    )
    return [
        {
            "msg_id": r["msg_id"],
            "read_ct": r["read_ct"],
            "enqueued_at": r["enqueued_at"],
            "vt": r["vt"],
            "message": r["message"] if isinstance(r["message"], dict) else json.loads(r["message"]) if r["message"] else {},
        }
        for r in rows
    ]


async def delete(queue: str, msg_id: int) -> bool:
    """Delete a message from the queue. Returns True if deleted."""
    pool = await _get_pool()
    q = _queue_name(queue)
    result = await pool.fetchval("SELECT pgmq.delete($1::text, $2::bigint)", q, msg_id)
    return bool(result)


async def archive(queue: str, msg_id: int) -> bool:
    """Archive a message (remove from queue, keep in archive). Returns True if archived."""
    pool = await _get_pool()
    q = _queue_name(queue)
    result = await pool.fetchval("SELECT pgmq.archive($1::text, $2::bigint)", q, msg_id)
    return bool(result)


async def send_to_dead_letter(msg: Dict[str, Any], reason: str = "") -> Optional[int]:
    """Send a failed message to the dead letter queue. Optionally add 'reason' to msg."""
    payload = {**msg, "dead_letter_reason": reason}
    return await send("dead_letter", payload)
