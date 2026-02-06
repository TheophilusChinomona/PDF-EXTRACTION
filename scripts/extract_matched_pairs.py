#!/usr/bin/env python3
"""
Run extraction on matched exam_sets (QP + Memo pairs) from Firebase Storage.

Downloads PDFs for each pair, runs the hybrid extraction pipeline, and saves
results to extractions and memo_extractions with scraped_file_id linkage.

Usage:
    python scripts/extract_matched_pairs.py --subject english --status matched
    python scripts/extract_matched_pairs.py --subject english --limit 10
    python scripts/extract_matched_pairs.py --dry-run --subject english

Requires: SUPABASE_SERVICE_ROLE_KEY, GEMINI_API_KEY, Firebase credentials in .env
"""

import argparse
import asyncio
import hashlib
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from supabase import create_client, Client

from app.config import get_settings
from app.db.extractions import create_extraction, check_duplicate
from app.db.memo_extractions import create_memo_extraction, check_memo_duplicate
from app.services.firebase_client import download_as_bytes
from app.services.gemini_client import get_gemini_client
from app.services.opendataloader_extractor import extract_pdf_structure
from app.services.pdf_extractor import extract_pdf_data_hybrid, PartialExtractionError
from app.services.memo_extractor import extract_memo_data_hybrid, PartialMemoExtractionError

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _get_supabase_client() -> Client:
    settings = get_settings()
    url = settings.supabase_url
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or settings.supabase_key
    return create_client(url, service_key)


def _build_storage_url(row: dict[str, Any]) -> str:
    bucket = (row.get("storage_bucket") or "").strip() or "default"
    path = (row.get("storage_path") or "").strip().lstrip("/")
    return f"gs://{bucket}/{path}"


def _sanitize_filename(name: str) -> str:
    if not name or not name.strip():
        return "document.pdf"
    name = name.strip()
    if not name.lower().endswith(".pdf"):
        name = name + ".pdf"
    return name


async def _get_already_extracted(sb: Client) -> tuple[set[str], set[str]]:
    """Return (set of scraped_file_ids with QP extraction, set with memo extraction)."""
    qp_ids: set[str] = set()
    memo_ids: set[str] = set()

    def fetch_qp():
        r = sb.table("extractions").select("scraped_file_id").not_.is_("scraped_file_id", "null").execute()
        return r.data or []

    def fetch_memo():
        r = sb.table("memo_extractions").select("scraped_file_id").not_.is_("scraped_file_id", "null").execute()
        return r.data or []

    qp_data = await asyncio.to_thread(fetch_qp)
    memo_data = await asyncio.to_thread(fetch_memo)
    for row in qp_data:
        sid = row.get("scraped_file_id")
        if sid:
            qp_ids.add(str(sid))
    for row in memo_data:
        sid = row.get("scraped_file_id")
        if sid:
            memo_ids.add(str(sid))
    return qp_ids, memo_ids


def _source_url_matches(source_url: str | None, substring: str) -> bool:
    """True if source_url contains substring (case-insensitive)."""
    if not substring or not (source_url or "").strip():
        return True
    return substring.lower() in (source_url or "").lower()


async def _fetch_exam_sets(
    sb: Client,
    subject: str | None,
    status: str | None,
    limit: int | None,
    source_url: str | None,
) -> list[dict]:
    """Fetch exam_sets (complete pairs) with scraped_files storage info.
    When source_url is set, only include pairs where both QP and Memo scraped_files have source_url containing it.
    If source_url is set, we first get scraped_file ids with that source_url and filter exam_sets by them (avoids fetching many pairs that will be discarded).
    """
    exam_sets: list[dict] = []

    if source_url:
        # Get scraped_file ids that have this source_url (batch; paginate if needed)
        sf_ids: set[str] = set()
        page_size = 1000
        offset = 0
        while True:
            r = (
                sb.table("scraped_files")
                .select("id")
                .ilike("source_url", f"%{source_url}%")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            data = r.data or []
            for row in data:
                if row.get("id"):
                    sf_ids.add(str(row["id"]))
            if len(data) < page_size:
                break
            offset += page_size
        if not sf_ids:
            logger.info("No scraped_files with source_url containing %r; no exam_sets can match.", source_url)
            return []

        # Query exam_sets where question_paper_id is in that set; then keep only where memo_id is also in sf_ids (both from source_url)
        ids_list = list(sf_ids)
        chunk = 200
        for i in range(0, len(ids_list), chunk):
            part = ids_list[i : i + chunk]
            q = (
                sb.table("exam_sets")
                .select("*")
                .not_.is_("question_paper_id", "null")
                .not_.is_("memo_id", "null")
                .in_("question_paper_id", part)
            )
            if status:
                q = q.eq("status", status)
            if subject:
                q = q.ilike("subject", f"%{subject}%")
            q = q.order("created_at", desc=True)
            # Fetch enough to allow for memo_id filter (we may discard some)
            fetch_limit = (limit + 50) if limit else 500
            q = q.limit(fetch_limit)
            resp = q.execute()
            for es in resp.data or []:
                if str(es.get("memo_id") or "") in sf_ids:
                    exam_sets.append(es)
                    if limit and len(exam_sets) >= limit:
                        break
            if limit and len(exam_sets) >= limit:
                break
        exam_sets = exam_sets[:limit] if limit else exam_sets
    else:
        q = (
            sb.table("exam_sets")
            .select("*")
            .not_.is_("question_paper_id", "null")
            .not_.is_("memo_id", "null")
        )
        if status:
            q = q.eq("status", status)
        if subject:
            q = q.ilike("subject", f"%{subject}%")
        q = q.order("created_at", desc=True)
        if limit:
            q = q.limit(limit)
        resp = q.execute()
        exam_sets = resp.data or []

    # Enrich with scraped_files (storage_bucket, storage_path, filename, source_url) for QP and Memo
    out = []
    for es in exam_sets:
        qp_id = es.get("question_paper_id")
        memo_id = es.get("memo_id")
        qp_row = None
        memo_row = None
        if qp_id:
            r = sb.table("scraped_files").select("id, storage_bucket, storage_path, filename, source_url").eq("id", qp_id).execute()
            if r.data:
                qp_row = r.data[0]
        if memo_id:
            r = sb.table("scraped_files").select("id, storage_bucket, storage_path, filename, source_url").eq("id", memo_id).execute()
            if r.data:
                memo_row = r.data[0]
        # When source_url was not used in query, filter here: both QP and Memo must match
        if source_url and (qp_row or memo_row):
            qp_ok = _source_url_matches(qp_row.get("source_url") if qp_row else None, source_url)
            memo_ok = _source_url_matches(memo_row.get("source_url") if memo_row else None, source_url)
            if not (qp_ok and memo_ok):
                continue
        out.append({
            **es,
            "qp_scraped": qp_row,
            "memo_scraped": memo_row,
        })
    return out


async def _extract_one_file(
    sb: Client,
    gemini_client: Any,
    scraped_file_id: str,
    storage_row: dict,
    doc_type: str,
    dry_run: bool,
) -> str | None:
    """
    Download one PDF, run extraction, save to DB. Returns extraction id or None.
    doc_type is 'qp' or 'memo'.
    """
    storage_url = _build_storage_url(storage_row)
    filename = _sanitize_filename(storage_row.get("filename") or "document.pdf")

    try:
        content = await asyncio.to_thread(download_as_bytes, storage_url)
    except Exception as e:
        logger.warning("Download failed %s: %s", storage_url, e)
        return None

    if not content:
        logger.warning("Empty file: %s", storage_url)
        return None

    file_hash = hashlib.sha256(content).hexdigest()

    if not dry_run:
        existing = await (check_memo_duplicate(sb, file_hash) if doc_type == "memo" else check_duplicate(sb, file_hash))
        if existing:
            logger.info("Already extracted (hash match): %s -> %s", filename, existing)
            return existing

    suffix = "qp" if doc_type == "qp" else "memo"
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        temp_path = f.name
        f.write(content)
    try:
        doc_structure = extract_pdf_structure(temp_path)
    except Exception as e:
        logger.warning("extract_pdf_structure failed for %s: %s", filename, e)
        Path(temp_path).unlink(missing_ok=True)
        return None

    file_info = {
        "file_name": filename,
        "file_size_bytes": len(content),
        "file_hash": file_hash,
        "scraped_file_id": scraped_file_id,
    }

    try:
        if doc_type == "memo":
            result = await extract_memo_data_hybrid(
                client=gemini_client,
                file_path=temp_path,
                doc_structure=doc_structure,
            )
        else:
            result = await extract_pdf_data_hybrid(
                client=gemini_client,
                file_path=temp_path,
                doc_structure=doc_structure,
            )
    except (PartialExtractionError, PartialMemoExtractionError) as e:
        result = e.partial_result
        file_info["error_message"] = str(e.original_exception)
        status = "partial"
    except Exception as e:
        logger.warning("Extraction failed for %s: %s", filename, e)
        Path(temp_path).unlink(missing_ok=True)
        return None
    else:
        status = "completed"

    Path(temp_path).unlink(missing_ok=True)

    if dry_run:
        logger.info("[dry-run] Would save %s %s", suffix, filename)
        return "dry-run"

    try:
        if doc_type == "memo":
            ext_id = await create_memo_extraction(sb, result, file_info, status=status)
        else:
            ext_id = await create_extraction(sb, result, file_info, status=status)
        logger.info("Saved %s: %s -> %s", suffix, filename, ext_id)
        return ext_id
    except Exception as e:
        logger.warning("Failed to save %s %s: %s", suffix, filename, e)
        return None


async def run(
    dry_run: bool,
    subject: str | None,
    status: str | None,
    limit: int | None,
    skip_existing: bool,
    source_url: str | None,
) -> None:
    sb = _get_supabase_client()
    exam_sets = await _fetch_exam_sets(sb, subject=subject, status=status, limit=limit, source_url=source_url)
    if not exam_sets:
        msg = "No exam_sets found for subject=%s status=%s" % (subject, status)
        if source_url:
            msg += " source_url=%s (need pairs where both QP and Memo scraped_files have this source)" % source_url
        logger.info(msg)
        return

    qp_done: set[str] = set()
    memo_done: set[str] = set()
    if skip_existing:
        qp_done, memo_done = await _get_already_extracted(sb)

    gemini_client = get_gemini_client()
    total_qp = 0
    total_memo = 0
    for es in exam_sets:
        qp_scraped = es.get("qp_scraped")
        memo_scraped = es.get("memo_scraped")
        subj = es.get("subject") or "?"
        year = es.get("year") or "?"
        paper = es.get("paper_number") or "?"
        if qp_scraped and str(qp_scraped["id"]) not in qp_done:
            ext_id = await _extract_one_file(
                sb, gemini_client,
                scraped_file_id=str(qp_scraped["id"]),
                storage_row=qp_scraped,
                doc_type="qp",
                dry_run=dry_run,
            )
            if ext_id and ext_id != "dry-run":
                qp_done.add(str(qp_scraped["id"]))
                total_qp += 1
        if memo_scraped and str(memo_scraped["id"]) not in memo_done:
            ext_id = await _extract_one_file(
                sb, gemini_client,
                scraped_file_id=str(memo_scraped["id"]),
                storage_row=memo_scraped,
                doc_type="memo",
                dry_run=dry_run,
            )
            if ext_id and ext_id != "dry-run":
                memo_done.add(str(memo_scraped["id"]))
                total_memo += 1
    logger.info("Done. QP extractions: %d, Memo extractions: %d", total_qp, total_memo)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run extraction on matched exam_sets from Firebase Storage.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")
    parser.add_argument("--subject", type=str, default=None, help="Filter by subject (partial match)")
    parser.add_argument("--status", type=str, default=None, help="Filter by status (e.g. matched)")
    parser.add_argument("--source-url", type=str, default=None, help="Filter to pairs where both QP and Memo scraped_files have source_url containing this (e.g. education.gov.za)")
    parser.add_argument("--limit", type=int, default=None, help="Max exam_sets to process")
    parser.add_argument("--no-skip-existing", action="store_true", help="Re-extract even if scraped_file_id already has extraction")
    args = parser.parse_args()

    asyncio.run(run(
        dry_run=args.dry_run,
        subject=args.subject,
        status=args.status,
        limit=args.limit,
        skip_existing=not args.no_skip_existing,
        source_url=args.source_url,
    ))


if __name__ == "__main__":
    main()
