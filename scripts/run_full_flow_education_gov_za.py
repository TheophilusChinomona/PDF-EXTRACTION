#!/usr/bin/env python3
"""
Run the full pipeline for education.gov.za papers:

  1. Submit batch validation for all scraped_files with source_url containing education.gov.za.
  2. (After validation completes) Run batch matcher to create exam_sets.
  3. Extract matched pairs (QP + Memo extraction).
  4. Export to Markdown.
  5. Download source PDFs and write SOURCE-LINKS.

Usage:
  # Submit validation only (then poll until complete)
  python scripts/run_full_flow_education_gov_za.py --submit-validation

  # Run matcher + extract + export + download (after validation has run and results are in DB)
  python scripts/run_full_flow_education_gov_za.py --match --extract --export --download

  # Run everything: submit validation, then matcher/extract/export/download (matcher and later steps will do little until validation completes)
  python scripts/run_full_flow_education_gov_za.py --all

Requires: .env with SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, GEMINI_API_KEY, Firebase credentials.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Use service role key for validation_jobs insert and batch operations (bypass RLS)
if os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
    os.environ["SUPABASE_KEY"] = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

SOURCE_URL_SUBSTRING = "education.gov.za"


async def get_education_gov_za_scraped_file_ids():
    """Return list of scraped_file id (str) where source_url contains education.gov.za."""
    from app.db.supabase_client import get_supabase_client
    client = get_supabase_client()
    ids = []
    offset = 0
    page = 1000
    while True:
        resp = await asyncio.to_thread(
            lambda o=offset, p=page: client.table("scraped_files")
            .select("id")
            .ilike("source_url", f"%{SOURCE_URL_SUBSTRING}%")
            .range(o, o + p - 1)
            .execute()
        )
        data = resp.data or []
        ids.extend([str(row["id"]) for row in data])
        if len(data) < page:
            break
        offset += page
    return ids


# Max scraped_file_ids per validation batch (Supabase .in_() and Gemini limits)
VALIDATION_BATCH_SIZE = 200


async def submit_validation():
    """Submit Gemini Batch validation for all education.gov.za scraped_files (in chunks)."""
    from app.db.validation_jobs import create_validation_job
    from app.db.supabase_client import get_supabase_client
    from app.services.validation_batch import submit_validation_batch

    ids = await get_education_gov_za_scraped_file_ids()
    if not ids:
        print("No scraped_files found for source_url containing education.gov.za.")
        return False
    print(f"Found {len(ids)} scraped_files with source_url containing education.gov.za.")
    client = get_supabase_client()
    for i in range(0, len(ids), VALIDATION_BATCH_SIZE):
        chunk = ids[i : i + VALIDATION_BATCH_SIZE]
        job_id = await create_validation_job(client, total_files=len(chunk), status="queued")
        print(f"Created validation_job {job_id} for {len(chunk)} files. Submitting to Gemini Batch API...")
        gemini_job_id = await submit_validation_batch(chunk, job_id)
        print(f"  Submitted. gemini_batch_job_id={gemini_job_id}")
    print("Poll until complete: python -m app.cli poll-batch-jobs --interval 60")
    return True


async def run_matcher(limit: int = 2000):
    """Run batch matcher (links validation_results to exam_sets)."""
    from app.services.batch_matcher import run_batch_matcher
    stats = await run_batch_matcher(limit=limit)
    print(f"Batch matcher: scanned={stats['scanned']} matched={stats['matched']} created={stats['created']} errors={stats['errors']}")
    return stats


def run_extract(limit=None, dry_run=True):
    """Run extract_matched_pairs with --source-url education.gov.za."""
    import subprocess
    cmd = [
        sys.executable,
        "scripts/extract_matched_pairs.py",
        "--source-url", SOURCE_URL_SUBSTRING,
        "--status", "matched",
    ]
    if limit:
        cmd.extend(["--limit", str(limit)])
    if dry_run:
        cmd.append("--dry-run")
    r = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent)
    return r.returncode == 0


def run_export(limit=None):
    """Run export_extractions_md.py --exam-sets --source-url education.gov.za."""
    import subprocess
    cmd = [
        sys.executable,
        "scripts/export_extractions_md.py",
        "--exam-sets",
        "--source-url", SOURCE_URL_SUBSTRING,
        "--status", "matched",
    ]
    if limit:
        cmd.extend(["--limit", str(limit)])
    r = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent)
    return r.returncode == 0


def run_download(limit=None):
    """Run download_matched_pairs_pdfs.py --source-url education.gov.za."""
    import subprocess
    cmd = [
        sys.executable,
        "scripts/download_matched_pairs_pdfs.py",
        "--source-url", SOURCE_URL_SUBSTRING,
        "--status", "matched",
    ]
    if limit:
        cmd.extend(["--limit", str(limit)])
    r = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent)
    return r.returncode == 0


async def main():
    parser = argparse.ArgumentParser(description="Full flow for education.gov.za papers.")
    parser.add_argument("--submit-validation", action="store_true", help="Submit batch validation for education.gov.za scraped_files")
    parser.add_argument("--match", action="store_true", help="Run batch matcher (after validation has completed)")
    parser.add_argument("--extract", action="store_true", help="Run extract_matched_pairs with --source-url education.gov.za")
    parser.add_argument("--export", action="store_true", help="Run export_extractions_md --exam-sets --source-url education.gov.za")
    parser.add_argument("--download", action="store_true", help="Run download_matched_pairs_pdfs with --source-url education.gov.za")
    parser.add_argument("--all", action="store_true", help="Run submit-validation, then match, extract, export, download")
    parser.add_argument("--limit", type=int, default=None, help="Limit for extract/export/download (default: no limit)")
    parser.add_argument("--matcher-limit", type=int, default=2000, help="Max validation_results to process in batch matcher (default: 2000)")
    parser.add_argument("--no-dry-run", action="store_true", help="For extract: actually write to DB (default is --dry-run)")
    args = parser.parse_args()

    if args.all:
        args.submit_validation = True
        args.match = True
        args.extract = True
        args.export = True
        args.download = True

    if not any([args.submit_validation, args.match, args.extract, args.export, args.download]):
        parser.print_help()
        return

    if args.submit_validation:
        ok = await submit_validation()
        if not ok:
            return
        if not args.all:
            print("Next: poll with python -m app.cli poll-batch-jobs --interval 60, then run with --match --extract --export --download")
            return

    if args.match:
        await run_matcher(limit=args.matcher_limit)

    if args.extract:
        run_extract(limit=args.limit, dry_run=not args.no_dry_run)

    if args.export:
        run_export(limit=args.limit)

    if args.download:
        run_download(limit=args.limit)


if __name__ == "__main__":
    asyncio.run(main())
