#!/usr/bin/env python3
"""
Submit extraction jobs to the local FastAPI server for validated-but-not-extracted files.

Downloads PDFs from Firebase Storage, groups them into batches, and POSTs each batch
to POST /api/batch on the local server. Useful when Gemini Batch API is unavailable.

Usage:
    python scripts/run_extraction_local_api.py --dry-run
    python scripts/run_extraction_local_api.py --dry-run --limit 10
    python scripts/run_extraction_local_api.py --limit 50 --batch-size 25
    python scripts/run_extraction_local_api.py --api-url http://localhost:8000

NOTE: Requires SUPABASE_SERVICE_ROLE_KEY in .env to bypass RLS.
NOTE: The local FastAPI server must be running before executing this script.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import httpx
from supabase import create_client, Client

from app.db.validation_results import list_validation_results
from app.services.firebase_client import download_as_bytes
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

CANDIDATE_LIMIT = 500
DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_BATCH_SIZE = 50
MAX_BATCH_SIZE = 100
REQUEST_TIMEOUT = 900.0  # 15 minutes


def _get_service_role_client() -> Client:
    settings = get_settings()
    url = settings.supabase_url
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or settings.supabase_key
    return create_client(url, service_key)


def _build_storage_url(row: dict[str, Any]) -> str:
    bucket = (row.get("storage_bucket") or "").strip() or "default"
    path = (row.get("storage_path") or "").strip().lstrip("/")
    return f"gs://{bucket}/{path}"


async def _get_scraped_file_ids_already_extracted(client: Any) -> set[str]:
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


def _post_batch(
    api_url: str,
    pdf_files: list[tuple[bytes, str]],
    source_ids: list[str],
) -> dict[str, Any]:
    """POST a batch of PDFs to the local API. Returns the JSON response."""
    files_payload = [
        ("files", (filename, pdf_bytes, "application/pdf"))
        for pdf_bytes, filename in pdf_files
    ]
    data = {"source_ids": json.dumps(source_ids)}

    with httpx.Client(timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=30.0)) as http:
        resp = http.post(f"{api_url}/api/batch", files=files_payload, data=data)
        resp.raise_for_status()
        return resp.json()


async def run(
    dry_run: bool,
    batch_size: int,
    limit: int | None,
    api_url: str,
) -> None:
    client = _get_service_role_client()

    # 1. Get validated files
    items, _ = await list_validation_results(client, status="correct", limit=CANDIDATE_LIMIT, offset=0)
    logger.info("Fetched %d validation_results with status='correct'", len(items))
    candidates = [r for r in items if r.get("scraped_file_id")]
    logger.info("Candidates with scraped_file_id: %d", len(candidates))

    # 2. Exclude already extracted
    already = await _get_scraped_file_ids_already_extracted(client)
    logger.info("Already extracted scraped_file_ids: %d", len(already))
    eligible = [r for r in candidates if str(r["scraped_file_id"]) not in already]
    logger.info("Eligible after filtering: %d", len(eligible))

    if limit:
        eligible = eligible[:limit]
        logger.info("Capped to --limit %d: %d files", limit, len(eligible))

    if not eligible:
        logger.info("No validated-but-not-extracted files found. Exiting.")
        return

    if dry_run:
        logger.info(
            "Dry run: would process %d files in %d batch(es) of up to %d",
            len(eligible),
            (len(eligible) + batch_size - 1) // batch_size,
            batch_size,
        )
        for i, r in enumerate(eligible[:10], 1):
            logger.info("  [%d] scraped_file_id=%s", i, r["scraped_file_id"])
        if len(eligible) > 10:
            logger.info("  ... and %d more", len(eligible) - 10)
        return

    # 3. Fetch scraped_files rows
    scraped_ids = [str(r["scraped_file_id"]) for r in eligible]
    scraped_rows = await _get_scraped_files_batch(client, scraped_ids)
    id_to_row = {str(r["id"]): r for r in scraped_rows}

    # 4. Download PDFs
    logger.info("Downloading %d PDFs from Firebase Storage...", len(scraped_ids))
    pdf_files: list[tuple[bytes, str, str]] = []  # (bytes, filename, scraped_file_id)
    download_failed = 0

    for i, sid in enumerate(scraped_ids, 1):
        row = id_to_row.get(sid)
        if not row:
            logger.warning("[%d/%d] scraped_files row not found for %s", i, len(scraped_ids), sid)
            download_failed += 1
            continue
        try:
            url = _build_storage_url(row)
            pdf_bytes = await asyncio.to_thread(download_as_bytes, url)
        except Exception as e:
            logger.warning("[%d/%d] Download failed for %s: %s", i, len(scraped_ids), sid, e)
            download_failed += 1
            continue
        filename = (row.get("filename") or "document.pdf").strip() or "document.pdf"
        pdf_files.append((pdf_bytes, filename, sid))
        if i % 20 == 0 or i == 1:
            logger.info("[%d/%d] Downloaded %d, failed %d", i, len(scraped_ids), len(pdf_files), download_failed)

    logger.info("Download complete: %d succeeded, %d failed", len(pdf_files), download_failed)

    if not pdf_files:
        logger.error("No PDFs downloaded. Check storage paths and Firebase credentials.")
        return

    # 5. Submit in batches
    total_batches = (len(pdf_files) + batch_size - 1) // batch_size
    logger.info("Submitting %d files in %d batch(es) to %s", len(pdf_files), total_batches, api_url)

    batch_results: list[dict[str, Any]] = []
    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = start + batch_size
        chunk = pdf_files[start:end]

        files_for_post = [(b, fname) for b, fname, _ in chunk]
        sids_for_post = [sid for _, _, sid in chunk]

        logger.info(
            "Batch %d/%d: submitting %d files...",
            batch_idx + 1, total_batches, len(chunk),
        )

        try:
            result = await asyncio.to_thread(
                _post_batch, api_url, files_for_post, sids_for_post,
            )
            batch_job_id = result.get("batch_job_id", "?")
            status = result.get("status", "?")
            logger.info(
                "Batch %d/%d: batch_job_id=%s status=%s",
                batch_idx + 1, total_batches, batch_job_id, status,
            )
            batch_results.append(result)
        except httpx.HTTPStatusError as e:
            logger.error(
                "Batch %d/%d: HTTP %d — %s",
                batch_idx + 1, total_batches, e.response.status_code, e.response.text[:500],
            )
            if e.response.status_code in (401, 403):
                logger.error("Authentication error. Aborting remaining batches.")
                break
        except httpx.ConnectError:
            logger.error("Cannot reach API server at %s. Is it running?", api_url)
            break
        except Exception as e:
            logger.error("Batch %d/%d: failed — %s", batch_idx + 1, total_batches, e)

    # 6. Summary
    print(f"\nDone. {len(batch_results)}/{total_batches} batches submitted successfully.")
    for r in batch_results:
        print(f"  batch_job_id={r.get('batch_job_id')}  status={r.get('status')}  files={r.get('total_files')}")
    print(f"\nCheck status: GET {api_url}/api/batch/{{batch_job_id}}")
    print("Export results: python scripts/export_extractions_md.py --all")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit extraction jobs to local FastAPI server for validated PDFs.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count eligible files without downloading or submitting.",
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help=f"Files per API request (default: {DEFAULT_BATCH_SIZE}, max: {MAX_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max total files to process.",
    )
    parser.add_argument(
        "--api-url", type=str, default=DEFAULT_API_URL,
        help=f"Local server URL (default: {DEFAULT_API_URL}).",
    )
    args = parser.parse_args()

    if args.batch_size > MAX_BATCH_SIZE:
        parser.error(f"--batch-size cannot exceed {MAX_BATCH_SIZE}")

    asyncio.run(run(
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        limit=args.limit,
        api_url=args.api_url,
    ))


if __name__ == "__main__":
    main()
