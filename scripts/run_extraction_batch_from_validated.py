#!/usr/bin/env python3
"""
Submit a Gemini Batch API extraction job for up to 100 validated-but-not-extracted files.

Selects validation_results with status='correct' whose scraped_file_id is not yet
in extractions or memo_extractions, downloads PDFs from storage, creates a batch_job,
and submits via submit_extraction_batch. Run from project root:

  python scripts/run_extraction_batch_from_validated.py
  python scripts/run_extraction_batch_from_validated.py --dry-run
  python scripts/run_extraction_batch_from_validated.py --min-files 10
  python scripts/run_extraction_batch_from_validated.py --force

Use --dry-run to only count/list eligible files without creating a job or calling Gemini.
Use --min-files N to require at least N successful downloads before submitting (default: 1).
Use --force to proceed even if 0 files downloaded (not useful, but disables the min-files check).
After running, poll for results: python -m app.cli poll-batch-jobs --once (or --interval 120).

NOTE: Requires SUPABASE_SERVICE_ROLE_KEY in .env (or SUPABASE_KEY set to service_role key)
to bypass RLS and read validation_results.
"""

import argparse
import asyncio
import logging
import os
import sys
from typing import Any

# Run from project root so app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()  # Load .env into os.environ before importing app modules

from supabase import create_client, Client

from app.db.batch_jobs import create_batch_job
from app.db.validation_results import list_validation_results
from app.services.extraction_batch import submit_extraction_batch
from app.services.firebase_client import download_as_bytes
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

MAX_FILES = 100
CANDIDATE_LIMIT = 200


def _get_service_role_client() -> Client:
    """
    Create Supabase client using service_role key to bypass RLS.
    
    Tries SUPABASE_SERVICE_ROLE_KEY first, then falls back to SUPABASE_KEY.
    """
    settings = get_settings()
    url = settings.supabase_url
    # Prefer service_role key if available
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or settings.supabase_key
    return create_client(url, service_key)


def _doc_type_from_validation_row(row: dict[str, Any]) -> str:
    """Return 'memo' or 'question_paper' from validation_result paper_type."""
    paper_type = (
        (row.get("metadata") or {}).get("paper_type")
        or row.get("paper_type")
        or ""
    )
    if isinstance(paper_type, str):
        pt = paper_type.strip().lower()
    else:
        pt = str(paper_type).strip().lower()
    if "memo" in pt or "marking" in pt or "mg" in pt:
        return "memo"
    return "question_paper"


def _build_storage_url(row: dict[str, Any]) -> str:
    """Build gs:// URL from scraped_files row."""
    bucket = (row.get("storage_bucket") or "").strip() or "default"
    path = (row.get("storage_path") or "").strip().lstrip("/")
    return f"gs://{bucket}/{path}"


async def _get_scraped_file_ids_already_extracted(client: Any) -> set[str]:
    """Return set of scraped_file_id (str) that have an extraction or memo_extraction."""
    extracted: set[str] = set()

    def fetch_extractions():
        r = client.table("extractions").select("scraped_file_id").not_.is_("scraped_file_id", "null").execute()
        return r.data or []

    def fetch_memos():
        r = client.table("memo_extractions").select("scraped_file_id").not_.is_("scraped_file_id", "null").execute()
        return r.data or []

    ext_data = await asyncio.to_thread(fetch_extractions)
    memo_data = await asyncio.to_thread(fetch_memos)
    for row in ext_data:
        sid = row.get("scraped_file_id")
        if sid:
            extracted.add(str(sid))
    for row in memo_data:
        sid = row.get("scraped_file_id")
        if sid:
            extracted.add(str(sid))
    return extracted


async def _get_scraped_files_batch(client: Any, scraped_file_ids: list[str]) -> list[dict[str, Any]]:
    """Fetch scraped_files rows by ids. Returns list of dicts with id, storage_bucket, storage_path, filename."""
    if not scraped_file_ids:
        return []

    def fetch():
        r = (
            client.table("scraped_files")
            .select("id, storage_bucket, storage_path, filename")
            .in_("id", scraped_file_ids)
            .execute()
        )
        return r.data or []

    data = await asyncio.to_thread(fetch)
    return list(data) if isinstance(data, list) else [data]


async def run(dry_run: bool, min_files: int = 1, force: bool = False) -> None:
    client = _get_service_role_client()

    # 1. Validation results with status='correct' (limit 200 to have buffer after filter)
    items, _ = await list_validation_results(client, status="correct", limit=CANDIDATE_LIMIT, offset=0)
    logger.info("Fetched %d validation_results with status='correct'", len(items))
    # Only rows with scraped_file_id (schema has it NOT NULL, but be safe)
    candidates = [r for r in items if r.get("scraped_file_id")]
    logger.info("Candidates with scraped_file_id: %d", len(candidates))

    # 2. Exclude already extracted / memo
    already = await _get_scraped_file_ids_already_extracted(client)
    logger.info("Already extracted scraped_file_ids: %d (first 5: %s)", len(already), list(already)[:5])
    if candidates:
        logger.info("First candidate scraped_file_id: %s (type: %s)", candidates[0]["scraped_file_id"], type(candidates[0]["scraped_file_id"]))
    eligible = [r for r in candidates if str(r["scraped_file_id"]) not in already]
    logger.info("Eligible after filtering: %d", len(eligible))
    eligible = eligible[:MAX_FILES]

    if not eligible:
        logger.info("No validated-but-not-extracted files found. Exiting.")
        return

    if dry_run:
        logger.info("Dry run: would submit %d files (first few scraped_file_ids: %s)", len(eligible), [str(r["scraped_file_id"]) for r in eligible[:5]])
        return

    # 3. Scraped_files rows and doc_type per row
    scraped_ids = [str(r["scraped_file_id"]) for r in eligible]
    scraped_rows = await _get_scraped_files_batch(client, scraped_ids)
    id_to_row = {str(r["id"]): r for r in scraped_rows}
    id_to_validation = {str(r["scraped_file_id"]): r for r in eligible}

    # 4. Download PDFs and build (bytes, filename, doc_type), source_ids
    files: list[tuple[bytes, str, str]] = []
    source_ids: list[str] = []
    total_to_download = len(scraped_ids)
    succeeded = 0
    failed = 0
    failed_ids: list[str] = []
    for i, sid in enumerate(scraped_ids, 1):
        row = id_to_row.get(sid)
        if not row:
            logger.warning("[%d/%d] scraped_files row not found for %s", i, total_to_download, sid)
            failed += 1
            failed_ids.append(sid)
            continue
        vrow = id_to_validation.get(sid) or {}
        doc_type = _doc_type_from_validation_row(vrow)
        try:
            url = _build_storage_url(row)
            pdf_bytes = await asyncio.to_thread(download_as_bytes, url)
        except Exception as e:
            logger.warning("[%d/%d] Failed to download %s (url=%s): %s", i, total_to_download, sid, _build_storage_url(row), e)
            failed += 1
            failed_ids.append(sid)
            continue
        succeeded += 1
        if i % 10 == 0 or i == 1:
            logger.info("[%d/%d] Downloaded: %d succeeded, %d failed", i, total_to_download, succeeded, failed)
        filename = (row.get("filename") or "document.pdf").strip() or "document.pdf"
        files.append((pdf_bytes, filename, doc_type))
        source_ids.append(sid)

    # Download summary
    logger.info("Download complete: %d succeeded, %d failed out of %d", succeeded, failed, total_to_download)

    if not files or (len(files) < min_files and not force):
        logger.error(
            "Only %d PDFs downloaded (minimum required: %d). %d failed.",
            len(files), min_files, failed,
        )
        if failed == total_to_download:
            logger.error(
                "ALL downloads failed. This usually means storage_path values in scraped_files "
                "don't match actual blob names in Firebase Storage."
            )
            logger.error("Run: python scripts/diagnose_storage_paths.py --validated-only")
            logger.error("Then: python scripts/fix_storage_paths.py --dry-run")
        elif not force:
            logger.error("Use --force to proceed anyway, or --min-files %d to lower the threshold.", len(files))
        return

    # Cap at 100 for create_batch_job
    files = files[:MAX_FILES]
    source_ids = source_ids[:MAX_FILES]

    # 5. Create batch_job and submit extraction batch
    batch_job_id = await create_batch_job(client, total_files=len(files), webhook_url=None)
    gemini_batch_job_id = await submit_extraction_batch(
        files,
        batch_job_id=batch_job_id,
        source_ids=source_ids,
    )

    print("Batch job created.")
    print(f"  batch_job_id:       {batch_job_id}")
    print(f"  gemini_batch_job_id: {gemini_batch_job_id}")
    print(f"  files submitted:     {len(files)}")
    print()
    print("To process results when the Gemini job completes, run:")
    print("  python -m app.cli poll-batch-jobs --once")
    print("  (or: python -m app.cli poll-batch-jobs --interval 120)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit Gemini Batch extraction for validated-not-extracted files.")
    parser.add_argument("--dry-run", action="store_true", help="Only count/list eligible files; do not create job or call Gemini.")
    parser.add_argument("--min-files", type=int, default=1, help="Minimum successful downloads required to proceed (default: 1).")
    parser.add_argument("--force", action="store_true", help="Proceed even if fewer than --min-files were downloaded.")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, min_files=args.min_files, force=args.force))


if __name__ == "__main__":
    main()
