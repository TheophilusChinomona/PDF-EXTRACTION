"""
Test script: Download 10 PDFs from Firebase Storage (using signed URLs),
submit them to the local FastAPI /api/batch endpoint, and report results.

Usage:
    python scripts/test_batch_10.py
"""

import os
import shutil
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from supabase import create_client

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
API_BASE = os.getenv("TEST_API_BASE", "http://localhost:8000")
NUM_PDFS = 10

# Firebase Storage config
FIREBASE_CRED_PATH = os.getenv(
    "FIREBASE_CREDENTIALS_PATH", ""
)
FIREBASE_BUCKET = "scrapperdb-f854d.firebasestorage.app"


def init_firebase_storage():
    """Initialize Firebase Admin and return a storage bucket."""
    import firebase_admin
    from firebase_admin import credentials, storage

    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_CRED_PATH)
        firebase_admin.initialize_app(cred, {"storageBucket": FIREBASE_BUCKET})

    return storage.bucket()


def get_storage_path(download_url: str) -> str:
    """Extract the storage path from a Firebase Storage URL.

    URL format: https://storage.googleapis.com/<bucket>/downloads/filename.pdf
    Storage path: downloads/filename.pdf
    """
    parsed = urlparse(download_url)
    # Path is /<bucket>/downloads/filename.pdf -- strip the bucket prefix
    path = parsed.path
    # Remove leading slash and bucket name
    parts = path.lstrip("/").split("/", 1)
    if len(parts) == 2:
        return parts[1]  # "downloads/filename.pdf"
    return path.lstrip("/")


def query_scraped_files(supabase, limit: int = NUM_PDFS) -> list[dict]:
    """Fetch scraped_files records that have a download_url."""
    response = (
        supabase.table("scraped_files")
        .select("id, filename, download_url, subject, grade, year, document_type")
        .neq("download_url", "")
        .not_.is_("download_url", "null")
        .limit(limit)
        .execute()
    )
    rows = response.data or []
    if not rows:
        print("ERROR: No scraped_files with download_url found in Supabase.")
        sys.exit(1)
    print(f"Found {len(rows)} scraped_files with download URLs.")
    return rows


def download_from_firebase(bucket, storage_path: str, dest: str) -> bool:
    """Download a file from Firebase Storage using the admin SDK."""
    try:
        blob = bucket.blob(storage_path)
        blob.download_to_filename(dest)
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def submit_batch(file_paths: list[tuple[str, str]], source_ids: list[str] | None = None) -> dict:
    """
    POST files to /api/batch as multipart uploads.
    file_paths: list of (filename, local_path) tuples.
    source_ids: optional list of scraped_file_id UUIDs, one per file.
    Returns the JSON response.
    """
    import json as _json

    files = []
    open_handles = []
    try:
        for filename, local_path in file_paths:
            fh = open(local_path, "rb")
            open_handles.append(fh)
            files.append(("files", (filename, fh, "application/pdf")))

        # Build form data for non-file fields
        data: dict[str, str] = {}
        if source_ids:
            data["source_ids"] = _json.dumps(source_ids)

        # The batch endpoint processes synchronously, so set a long timeout
        # pool/connect=30s, read/write=600s (10 min for processing 10 PDFs)
        with httpx.Client(timeout=httpx.Timeout(
            connect=30.0, read=600.0, write=60.0, pool=30.0
        )) as client:
            print(f"\nSubmitting {len(files)} files to {API_BASE}/api/batch ...")
            if source_ids:
                print(f"  With {len(source_ids)} source_ids from scraped_files")
            start = time.time()
            resp = client.post(f"{API_BASE}/api/batch", files=files, data=data)
            elapsed = time.time() - start
            print(f"Response received in {elapsed:.1f}s  (HTTP {resp.status_code})")
            resp.raise_for_status()
            return resp.json()
    finally:
        for fh in open_handles:
            fh.close()


def fetch_batch_status(batch_job_id: str) -> dict:
    """GET /api/batch/{id} to retrieve final batch status."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{API_BASE}/api/batch/{batch_job_id}")
        resp.raise_for_status()
        return resp.json()


def print_summary(status: dict) -> None:
    """Pretty-print the batch job results."""
    print("\n" + "=" * 60)
    print("BATCH JOB RESULTS")
    print("=" * 60)
    print(f"  Job ID:           {status.get('id')}")
    print(f"  Status:           {status.get('status')}")
    print(f"  Total files:      {status.get('total_files')}")
    print(f"  Completed:        {status.get('completed_files')}")
    print(f"  Failed:           {status.get('failed_files')}")

    routing = status.get("routing_stats", {})
    print(f"  Routing hybrid:   {routing.get('hybrid', 0)}")
    print(f"  Routing vision:   {routing.get('vision_fallback', 0)}")

    cost = status.get("cost_estimate_usd")
    savings = status.get("cost_savings_usd")
    if cost is not None:
        print(f"  Cost estimate:    ${cost:.4f}")
    if savings is not None:
        print(f"  Cost savings:     ${savings:.4f}")

    extraction_ids = status.get("extraction_ids", [])
    print(f"  Extraction IDs ({len(extraction_ids)}):")
    for eid in extraction_ids:
        print(f"    - {eid}")

    print("=" * 60)


def main() -> None:
    print("=" * 60)
    print("PDF Batch Extraction Test (10 PDFs)")
    print("=" * 60)

    # 0. Init Firebase
    print("\n[0/4] Initializing Firebase Storage...")
    if not FIREBASE_CRED_PATH or not os.path.exists(FIREBASE_CRED_PATH):
        print(f"ERROR: FIREBASE_CREDENTIALS_PATH not set or file not found: {FIREBASE_CRED_PATH}")
        sys.exit(1)
    bucket = init_firebase_storage()
    print(f"  Bucket: {bucket.name}")

    # 1. Query Supabase for PDFs
    print("\n[1/4] Querying Supabase for scraped_files with download URLs...")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    rows = query_scraped_files(supabase, limit=NUM_PDFS)

    for r in rows:
        subj = r.get("subject", "?")
        grade = r.get("grade", "?")
        doc_type = r.get("document_type", "?")
        print(f"  - {r['filename']}  (subject={subj}, grade={grade}, type={doc_type})")

    # 2. Download PDFs from Firebase Storage to temp dir
    print(f"\n[2/4] Downloading {len(rows)} PDFs from Firebase Storage...")
    tmpdir = tempfile.mkdtemp(prefix="pdf_batch_test_")
    downloaded: list[tuple[str, str]] = []  # (filename, local_path)

    for r in rows:
        download_url = r["download_url"]
        storage_path = get_storage_path(download_url)
        filename = r["filename"] or f"{r['id']}.pdf"
        dest = os.path.join(tmpdir, filename)
        print(f"  Downloading {filename} ({storage_path})...", end=" ")
        if download_from_firebase(bucket, storage_path, dest):
            size_kb = os.path.getsize(dest) / 1024
            print(f"OK ({size_kb:.0f} KB)")
            downloaded.append((filename, dest))
        else:
            print("SKIPPED")

    if not downloaded:
        print("ERROR: No PDFs downloaded. Aborting.")
        shutil.rmtree(tmpdir, ignore_errors=True)
        sys.exit(1)

    print(f"\nDownloaded {len(downloaded)} / {len(rows)} PDFs.")

    # 3. Submit to batch endpoint
    print(f"\n[3/4] Submitting batch to {API_BASE}/api/batch ...")
    # Collect scraped_file_id UUIDs for each downloaded file (in download order)
    source_ids = [r["id"] for r in rows if (r["filename"] or f"{r['id']}.pdf") in [d[0] for d in downloaded]]
    if len(source_ids) != len(downloaded):
        print(f"  WARNING: source_ids count ({len(source_ids)}) != downloaded count ({len(downloaded)}), sending without source_ids")
        source_ids = []
    try:
        batch_response = submit_batch(downloaded, source_ids=source_ids or None)
    except httpx.HTTPStatusError as e:
        print(f"ERROR: Batch submission failed: {e.response.status_code}")
        print(f"  Detail: {e.response.text}")
        shutil.rmtree(tmpdir, ignore_errors=True)
        sys.exit(1)
    except httpx.ConnectError:
        print(f"ERROR: Cannot connect to {API_BASE}. Is the server running?")
        print("  Start it with: uvicorn app.main:app --host 0.0.0.0 --port 8000")
        shutil.rmtree(tmpdir, ignore_errors=True)
        sys.exit(1)

    batch_job_id = batch_response.get("batch_job_id")
    print(f"  Batch job ID: {batch_job_id}")
    print(f"  Status URL:   {batch_response.get('status_url')}")

    # 4. Fetch final status
    print("\n[4/4] Fetching batch job status...")
    try:
        status = fetch_batch_status(batch_job_id)
        print_summary(status)
    except Exception as e:
        print(f"  Warning: Could not fetch status: {e}")
        print(f"  Raw batch response: {batch_response}")

    # Cleanup temp files
    shutil.rmtree(tmpdir, ignore_errors=True)
    print(f"\nCleaned up temp directory: {tmpdir}")
    print("Done.")


if __name__ == "__main__":
    main()
