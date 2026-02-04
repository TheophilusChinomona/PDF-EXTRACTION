"""
Batch job: scan documents not linked to any exam_set and run matching.

Idempotent; safe to run multiple times. Logs total scanned, matched, created, errors.
"""

import asyncio
import logging
from typing import Any, Dict, Set
from uuid import UUID

from supabase import Client

from app.db import exam_sets as db_exam_sets
from app.db import validation_results as db_validation_results
from app.db.supabase_client import get_supabase_client
from app.services.exam_matcher import match_document_to_exam_set
from app.utils.normalizers import (
    normalize_grade,
    normalize_paper_number,
    normalize_session,
    normalize_subject,
)

logger = logging.getLogger(__name__)


async def _get_linked_scraped_file_ids(client: Client) -> Set[UUID]:
    """Return set of scraped_file_ids that are already QP or Memo in some exam_set."""
    linked: Set[UUID] = set()
    offset = 0
    limit = 200
    while True:
        items, _ = await db_exam_sets.list_exam_sets(
            client,
            limit=limit,
            offset=offset,
        )
        if not items:
            break
        for row in items:
            qp = row.get("question_paper_id")
            if qp:
                linked.add(UUID(qp) if isinstance(qp, str) else qp)
            memo = row.get("memo_id")
            if memo:
                linked.add(UUID(memo) if isinstance(memo, str) else memo)
        if len(items) < limit:
            break
        offset += limit
    return linked


def _validation_row_to_metadata(row: Dict[str, Any]) -> Dict[str, Any]:
    """Build metadata dict for match_document_to_exam_set from validation_results row."""
    return {
        "subject": row.get("subject"),
        "grade": row.get("grade"),
        "year": row.get("year"),
        "paper_type": row.get("paper_type"),
        "paper_number": row.get("paper_number"),
        "session": row.get("session"),
        "syllabus": row.get("syllabus"),
    }


async def run_batch_matcher(
    client: Optional[Client] = None,
    limit: int = 500,
) -> Dict[str, int]:
    """
    Run matching for all validation_results not yet linked to an exam_set.
    Returns dict: scanned, matched, created, errors.
    """
    if client is None:
        client = get_supabase_client()
    stats = {"scanned": 0, "matched": 0, "created": 0, "errors": 0}
    linked = await _get_linked_scraped_file_ids(client)
    offset = 0
    page_size = min(limit, 100)
    while offset < limit:
        items, total = await db_validation_results.list_validation_results(
            client,
            limit=page_size,
            offset=offset,
        )
        for row in items:
            scraped_file_id_str = row.get("scraped_file_id")
            if not scraped_file_id_str:
                stats["errors"] += 1
                continue
            scraped_file_id = UUID(scraped_file_id_str) if isinstance(scraped_file_id_str, str) else scraped_file_id_str
            if scraped_file_id in linked:
                continue
            stats["scanned"] += 1
            metadata = _validation_row_to_metadata(row)
            try:
                subj = normalize_subject(metadata.get("subject") or "")
                gr = normalize_grade(metadata.get("grade"))
                pn = normalize_paper_number(metadata.get("paper_number"))
                sess = normalize_session(metadata.get("session") or "")
                if not subj or gr is None or not sess:
                    stats["errors"] += 1
                    continue
                existing_before = await db_exam_sets.find_exam_set_by_match_key(
                    client,
                    subject=subj,
                    grade=gr,
                    paper_number=pn,
                    year=metadata.get("year") or 0,
                    session=sess,
                    syllabus=metadata.get("syllabus"),
                )
                result_id = await match_document_to_exam_set(client, scraped_file_id, metadata)
                if result_id:
                    linked.add(scraped_file_id)
                    if existing_before is None:
                        stats["created"] += 1
                    else:
                        stats["matched"] += 1
                else:
                    stats["errors"] += 1
            except Exception as e:
                logger.exception("Batch matcher error for scraped_file_id=%s: %s", scraped_file_id, e)
                stats["errors"] += 1
        if not items or len(items) < page_size:
            break
        offset += len(items)
        if offset >= limit:
            break
    logger.info(
        "Batch matcher finished: scanned=%d matched=%d created=%d errors=%d",
        stats["scanned"],
        stats["matched"],
        stats["created"],
        stats["errors"],
    )
    return stats
