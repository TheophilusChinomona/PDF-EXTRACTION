#!/usr/bin/env python3
"""
Run the hybrid extraction pipeline on scraped_files with source_url containing education.gov.za.
Saves results to extractions and memo_extractions (DB). Skips already-extracted files.

Usage:
    python scripts/run_extraction_education_gov_za.py --limit 100
    python scripts/run_extraction_education_gov_za.py --limit 100 --dry-run

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

if os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
    os.environ["SUPABASE_KEY"] = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

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

SOURCE_URL_SUBSTRING = "education.gov.za"


def _get_supabase_client() -> Client:
    settings = get_settings()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or settings.supabase_key
    return create_client(settings.supabase_url, key)


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


def _doc_type_from_row(row: dict[str, Any]) -> str:
    """Return 'memo' or 'qp' from scraped_files.document_type or filename."""
    dt = (row.get("document_type") or "").strip().lower()
    if "memo" in dt or "memorandum" in dt or "marking" in dt:
        return "memo"
    if "question" in dt or "paper" in dt:
        return "qp"
    fn = (row.get("filename") or "").lower()
    if "memo" in fn or "ms." in fn or "mark" in fn or "memorandum" in fn:
        return "memo"
    return "qp"


async def _get_already_extracted(sb: Client) -> tuple[set[str], set[str]]:
    def _fetch():
        qp = sb.table("extractions").select("scraped_file_id").not_.is_("scraped_file_id", "null").execute()
        memo = sb.table("memo_extractions").select("scraped_file_id").not_.is_("scraped_file_id", "null").execute()
        return (qp.data or [], memo.data or [])

    qp_data, memo_data = await asyncio.to_thread(_fetch)
    qp_ids = {str(r["scraped_file_id"]) for r in qp_data if r.get("scraped_file_id")}
    memo_ids = {str(r["scraped_file_id"]) for r in memo_data if r.get("scraped_file_id")}
    return qp_ids, memo_ids


async def _fetch_education_gov_za_scraped_files(sb: Client, limit: int) -> list[dict]:
    """Fetch scraped_files with source_url containing education.gov.za, storage_path not null."""
    rows: list[dict] = []
    offset = 0
    page = 200
    while len(rows) < limit:
        def _query():
            return (
                sb.table("scraped_files")
                .select("id, storage_bucket, storage_path, filename, document_type")
                .ilike("source_url", f"%{SOURCE_URL_SUBSTRING}%")
                .not_.is_("storage_path", "null")
                .order("id")
                .range(offset, offset + page - 1)
                .execute()
            )
        r = await asyncio.to_thread(_query)
        data = r.data or []
        rows.extend(data)
        if len(data) < page:
            break
        offset += page
    return rows[:limit]


async def _extract_one(
    sb: Client,
    gemini_client: Any,
    row: dict,
    doc_type: str,
    dry_run: bool,
) -> str | None:
    scraped_file_id = str(row["id"])
    storage_row = {
        "storage_bucket": row.get("storage_bucket"),
        "storage_path": row.get("storage_path"),
        "filename": row.get("filename"),
    }
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
            logger.info("Already extracted (hash): %s -> %s", filename, existing)
            return existing

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(content)
        temp_path = f.name
    try:
        doc_structure = extract_pdf_structure(temp_path)
    except Exception as e:
        logger.warning("extract_pdf_structure failed %s: %s", filename, e)
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
            result = await extract_memo_data_hybrid(client=gemini_client, file_path=temp_path, doc_structure=doc_structure)
        else:
            result = await extract_pdf_data_hybrid(client=gemini_client, file_path=temp_path, doc_structure=doc_structure)
        status = "completed"
    except (PartialExtractionError, PartialMemoExtractionError) as e:
        result = e.partial_result
        file_info["error_message"] = str(e.original_exception)
        status = "partial"
    except Exception as e:
        logger.warning("Extraction failed %s: %s", filename, e)
        Path(temp_path).unlink(missing_ok=True)
        return None
    Path(temp_path).unlink(missing_ok=True)

    if dry_run:
        logger.info("[dry-run] Would save %s %s", doc_type, filename)
        return "dry-run"
    try:
        if doc_type == "memo":
            ext_id = await create_memo_extraction(sb, result, file_info, status=status)
        else:
            ext_id = await create_extraction(sb, result, file_info, status=status)
        logger.info("Saved %s: %s -> %s", doc_type, filename, ext_id)
        return ext_id
    except Exception as e:
        logger.warning("Failed to save %s %s: %s", doc_type, filename, e)
        return None


async def run(limit: int, dry_run: bool) -> None:
    sb = _get_supabase_client()
    qp_done, memo_done = await _get_already_extracted(sb)
    rows = await _fetch_education_gov_za_scraped_files(sb, limit)
    # Exclude already extracted
    to_process = [r for r in rows if str(r["id"]) not in qp_done and str(r["id"]) not in memo_done]
    logger.info("Education.gov.za scraped_files: %d fetched, %d to process (after skipping already extracted)", len(rows), len(to_process))
    if not to_process:
        return
    gemini_client = get_gemini_client()
    total_qp = 0
    total_memo = 0
    for i, row in enumerate(to_process, 1):
        doc_type = _doc_type_from_row(row)
        ext_id = await _extract_one(sb, gemini_client, row, doc_type, dry_run)
        if ext_id and ext_id != "dry-run":
            if doc_type == "memo":
                total_memo += 1
            else:
                total_qp += 1
        if (i % 10) == 0:
            logger.info("Progress: %d/%d", i, len(to_process))
    logger.info("Done. QP extractions: %d, Memo extractions: %d", total_qp, total_memo)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run extraction on education.gov.za scraped_files and save to DB.")
    parser.add_argument("--limit", type=int, default=100, help="Max PDFs to process (default: 100)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")
    args = parser.parse_args()
    asyncio.run(run(limit=args.limit, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
