"""
Migration Script: Firestore → Supabase (Comprehensive)
=======================================================

Migrates scraped_files from Firestore to Supabase with full field mapping,
including all denormalized metadata fields, Firebase Storage paths,
and user tracking data.

Requires migration 007_extend_scraped_files_for_firebase.sql to be applied first.

Usage:
    # Preview without writing (dry run)
    python scripts/migrate_firestore_to_supabase.py --dry-run

    # Execute migration
    python scripts/migrate_firestore_to_supabase.py --run

    # Verify migration counts match
    python scripts/migrate_firestore_to_supabase.py --verify

    # Migrate a specific collection
    python scripts/migrate_firestore_to_supabase.py --run --collection scraped_files

Created: 2026-02-02
"""

import os
import sys
import hashlib
import logging
import argparse
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Constants
BATCH_SIZE = 100
DEFAULT_BUCKET = "scrapperdb-f854d.firebasestorage.app"

COLLECTIONS = {
    "scraped_files": {
        "firestore_collection": "scraped_files",
        "supabase_table": "scraped_files",
    },
}


# ============================================================================
# Firebase Initialization
# ============================================================================


def initialize_firebase():
    """Initialize Firebase Admin SDK and return Firestore client."""
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        cred_path = os.environ.get(
            "FIREBASE_CREDENTIALS_PATH",
            r"C:\Users\theoc\Desktop\Work\Academy Scrapper\Scrapper.FE\serviceAccountKey.json",
        )
        if not os.path.exists(cred_path):
            logger.error(f"Firebase credentials not found at: {cred_path}")
            logger.error("Set FIREBASE_CREDENTIALS_PATH in .env")
            sys.exit(1)

        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)

    return firestore.client()


# ============================================================================
# Supabase Initialization
# ============================================================================


def initialize_supabase():
    """Initialize Supabase client with service role key for full access."""
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    # Prefer service role key for migration (bypasses RLS)
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")

    if not url or not key:
        logger.error("SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY) must be set in .env")
        sys.exit(1)

    if not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        logger.warning(
            "Using anon key instead of service role key. "
            "Migration may fail due to RLS. Set SUPABASE_SERVICE_ROLE_KEY in .env"
        )

    return create_client(url, key)


# ============================================================================
# Field Helpers
# ============================================================================


def generate_file_id(filename: str) -> str:
    """Generate file_id from filename using MD5 hash."""
    return hashlib.md5(filename.encode()).hexdigest()


def clean_string(value: Any) -> Optional[str]:
    """Clean string value, converting empty/whitespace to None."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def firestore_timestamp_to_iso(ts: Any) -> Optional[str]:
    """Convert Firestore Timestamp or datetime to ISO 8601 string."""
    if ts is None:
        return None

    # Firestore Timestamp object (has .seconds and .nanoseconds)
    if hasattr(ts, "seconds"):
        dt = datetime.fromtimestamp(ts.seconds, tz=timezone.utc)
        return dt.isoformat()

    # Already a datetime
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            dt = ts.replace(tzinfo=timezone.utc)
        else:
            dt = ts
        return dt.isoformat()

    # ISO string passthrough
    if isinstance(ts, str):
        return ts

    return None


def extract_storage_path(storage_url: Optional[str], storage_path_field: Optional[str] = None) -> Optional[str]:
    """
    Extract the Firebase Storage path from a storage URL or storagePath field.

    Handles URLs like:
    - https://storage.googleapis.com/bucket/path/to/file.pdf
    - https://firebasestorage.googleapis.com/v0/b/bucket/o/path%2Fto%2Ffile.pdf?alt=media&token=...
    - gs://bucket/path/to/file.pdf
    """
    # Prefer the explicit storagePath field from Firestore if present
    if storage_path_field:
        return storage_path_field

    if not storage_url:
        return None

    try:
        if storage_url.startswith("gs://"):
            parts = storage_url.replace("gs://", "").split("/", 1)
            return parts[1] if len(parts) > 1 else None

        parsed = urlparse(storage_url)

        # storage.googleapis.com URL (most common in this dataset)
        # Format: https://storage.googleapis.com/{bucket}/{path}
        if "storage.googleapis.com" in parsed.netloc:
            # Path: /{bucket}/{path/to/file}
            parts = parsed.path.lstrip("/").split("/", 1)
            if len(parts) > 1:
                return unquote(parts[1])

        # firebasestorage.googleapis.com URL
        if "firebasestorage.googleapis.com" in parsed.netloc:
            path_parts = parsed.path.split("/o/")
            if len(path_parts) > 1:
                return unquote(path_parts[1])

        # Direct storage URL (scrapperdb-f854d.firebasestorage.app)
        if "firebasestorage.app" in parsed.netloc:
            return unquote(parsed.path.lstrip("/"))

    except Exception:
        pass

    return None


def map_status(status: Any) -> str:
    """Map Firestore status to PostgreSQL file_status enum."""
    if status is None:
        return "pending"

    status_str = str(status).lower().strip()

    valid = {"pending", "downloading", "downloaded", "processing", "completed", "failed"}
    if status_str in valid:
        return status_str

    aliases = {
        "success": "completed",
        "done": "completed",
        "error": "failed",
        "failure": "failed",
        "in_progress": "processing",
        "queued": "pending",
    }
    return aliases.get(status_str, "pending")


def safe_int(value: Any, min_val: Optional[int] = None, max_val: Optional[int] = None) -> Optional[int]:
    """Safely convert to int with optional bounds checking.

    Handles strings like 'Grade 12' by extracting the number.
    """
    if value is None:
        return None

    s = str(value).strip()
    if s.lower() == "unknown" or s == "":
        return None

    try:
        n = int(s)
    except (ValueError, TypeError):
        # Try extracting digits from strings like "Grade 12"
        import re
        match = re.search(r"\d+", s)
        if match:
            n = int(match.group())
        else:
            return None

    if min_val is not None and n < min_val:
        return None
    if max_val is not None and n > max_val:
        return None
    return n


def clean_or_none(value: Any) -> Optional[str]:
    """Clean string value, treating 'Unknown' as None."""
    s = clean_string(value)
    if s and s.lower() == "unknown":
        return None
    return s


# ============================================================================
# Record Transformation
# ============================================================================


def transform_scraped_file(doc_id: str, doc_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform a Firestore scraped_files document to Supabase schema.

    Handles all field mappings including:
    - Basic fields (filename, status, urls)
    - Denormalized metadata (document_type, year, session, etc.)
    - Firebase Storage path extraction
    - User tracking (user_id, user_email)
    - Timestamp conversions
    """
    filename = doc_data.get("filename", "")
    if not filename:
        logger.warning(f"Document {doc_id} has no filename, using doc_id")
        filename = doc_id

    # Use fileId from Firestore if present, otherwise generate from filename
    file_id = doc_data.get("fileId") or generate_file_id(filename)

    # Extract metadata sub-object
    metadata = doc_data.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    # Storage URL: try storageUrl first, then download_url, then storage_url
    storage_url = (
        doc_data.get("storageUrl")
        or doc_data.get("storage_url")
        or doc_data.get("download_url")
    )

    # Source URL: try url first, then sourceUrl
    source_url = doc_data.get("url") or doc_data.get("sourceUrl") or doc_data.get("source_url")

    # Grade: check top-level, then metadata (handles "Grade 12" strings)
    grade = safe_int(
        doc_data.get("grade") or metadata.get("grade"),
        min_val=1,
        max_val=12,
    )

    # Subject: check top-level, then metadata (filter out "Unknown")
    subject = clean_or_none(doc_data.get("subject") or metadata.get("subject"))

    # Denormalized fields: check both top-level and metadata, filter "Unknown"
    document_type = clean_or_none(
        doc_data.get("documentType") or metadata.get("documentType") or metadata.get("document_type")
    )
    year = safe_int(
        doc_data.get("year") or metadata.get("year"),
        min_val=1990, max_val=2100,
    )
    session = clean_or_none(
        doc_data.get("term") or metadata.get("quarter")
        or metadata.get("term") or metadata.get("session")
    )
    syllabus = clean_or_none(
        doc_data.get("curriculum") or metadata.get("syllabus") or metadata.get("curriculum")
    )
    language = clean_or_none(
        doc_data.get("language") or metadata.get("language")
    )

    # File size: try multiple field names
    file_size = safe_int(
        doc_data.get("fileSize")
        or doc_data.get("sizeBytes")
        or doc_data.get("fileSizeBytes")
        or doc_data.get("file_size"),
        min_val=0,
    )

    # Build clean metadata JSONB (preserve full original for reference)
    clean_metadata = {}
    if metadata:
        clean_metadata = {k: v for k, v in metadata.items() if v is not None}

    # Add recognition quality if present
    recognition_quality = metadata.get("recognitionQuality") or metadata.get("recognition_quality")
    if recognition_quality is not None:
        clean_metadata["recognitionQuality"] = recognition_quality

    record = {
        "file_id": file_id,
        "filename": filename,
        "subject": subject,
        "grade": grade,
        "source_url": clean_string(source_url),
        "download_url": clean_string(storage_url),
        "status": map_status(doc_data.get("status")),
        "file_size": file_size,
        "metadata": clean_metadata if clean_metadata else {},
        # New columns from migration 007
        "storage_path": extract_storage_path(storage_url, doc_data.get("storagePath")),
        "storage_bucket": DEFAULT_BUCKET,
        "document_type": document_type,
        "year": year,
        "session": session,
        "syllabus": syllabus,
        "language": language,
        "user_id": clean_string(doc_data.get("userId") or doc_data.get("user_id")),
        "user_email": clean_string(doc_data.get("userEmail") or doc_data.get("user_email")),
        "job_id": clean_string(doc_data.get("jobId") or doc_data.get("job_id")),
        # firestore_doc_id column removed (migration 019); Supabase is sole source of truth
    }

    # Timestamps
    downloaded_at = firestore_timestamp_to_iso(
        doc_data.get("downloadedAt") or doc_data.get("downloaded_at")
    )
    if downloaded_at:
        record["downloaded_at"] = downloaded_at

    created_at = firestore_timestamp_to_iso(
        doc_data.get("createdAt") or doc_data.get("created_at")
    )
    if created_at:
        record["created_at"] = created_at

    updated_at = firestore_timestamp_to_iso(
        doc_data.get("updatedAt") or doc_data.get("updated_at")
    )
    if updated_at:
        record["updated_at"] = updated_at

    return record


# ============================================================================
# Data Loading
# ============================================================================


def load_firestore_collection(collection_name: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Load all documents from a Firestore collection."""
    logger.info(f"Loading Firestore collection: {collection_name}")
    db = initialize_firebase()

    docs = db.collection(collection_name).stream()
    records = [(doc.id, doc.to_dict()) for doc in docs]

    logger.info(f"Loaded {len(records)} documents from {collection_name}")
    return records


# ============================================================================
# Modes: Dry Run, Run, Verify
# ============================================================================


def dry_run(collection: str = "scraped_files") -> None:
    """Preview migration without writing to database."""
    config = COLLECTIONS[collection]
    data = load_firestore_collection(config["firestore_collection"])

    if not data:
        print(f"\nNo documents found in Firestore collection: {config['firestore_collection']}")
        return

    # Transform all records
    transformed = []
    transform_errors = []
    for doc_id, doc_data in data:
        try:
            record = transform_scraped_file(doc_id, doc_data)
            transformed.append(record)
        except Exception as e:
            transform_errors.append((doc_id, str(e)))

    # Gather statistics
    stats = {
        "status": {},
        "subject": {},
        "document_type": {},
        "year": {},
        "session": {},
        "has_storage_path": 0,
        "has_user_id": 0,
        "has_source_url": 0,
        "has_download_url": 0,
    }

    missing = {"subject": 0, "grade": 0, "source_url": 0, "document_type": 0, "year": 0}

    for rec in transformed:
        # Count distributions
        for field in ["status", "subject", "document_type", "year", "session"]:
            val = rec.get(field) or "Unknown"
            stats[field][val] = stats[field].get(val, 0) + 1

        # Count presence
        if rec.get("storage_path"):
            stats["has_storage_path"] += 1
        if rec.get("user_id"):
            stats["has_user_id"] += 1
        if rec.get("source_url"):
            stats["has_source_url"] += 1
        if rec.get("download_url"):
            stats["has_download_url"] += 1

        # Count missing
        for field in missing:
            if not rec.get(field):
                missing[field] += 1

    total = len(transformed)

    # Print report
    print("\n" + "=" * 70)
    print(f"MIGRATION PREVIEW - {collection.upper()}")
    print("=" * 70)

    print(f"\nTotal documents: {len(data)}")
    print(f"Successfully transformed: {total}")
    if transform_errors:
        print(f"Transform errors: {len(transform_errors)}")

    print(f"\nField Coverage:")
    print(f"  Has storage_path:  {stats['has_storage_path']:>5} / {total} ({stats['has_storage_path']/total*100:.1f}%)")
    print(f"  Has user_id:       {stats['has_user_id']:>5} / {total} ({stats['has_user_id']/total*100:.1f}%)")
    print(f"  Has source_url:    {stats['has_source_url']:>5} / {total} ({stats['has_source_url']/total*100:.1f}%)")
    print(f"  Has download_url:  {stats['has_download_url']:>5} / {total} ({stats['has_download_url']/total*100:.1f}%)")

    print(f"\nMissing Fields:")
    for field, count in missing.items():
        pct = count / total * 100 if total else 0
        print(f"  {field:>15}: {count:>5} ({pct:.1f}%)")

    print(f"\nStatus Distribution:")
    for val, count in sorted(stats["status"].items(), key=lambda x: -x[1]):
        print(f"  {val:>15}: {count:>5} ({count/total*100:.1f}%)")

    print(f"\nTop 10 Subjects:")
    sorted_subjects = sorted(stats["subject"].items(), key=lambda x: -x[1])[:10]
    for val, count in sorted_subjects:
        print(f"  {val:>30}: {count:>5}")

    print(f"\nDocument Types:")
    for val, count in sorted(stats["document_type"].items(), key=lambda x: -x[1]):
        print(f"  {val:>15}: {count:>5}")

    print(f"\nYears:")
    for val, count in sorted(stats["year"].items(), key=lambda x: str(x[0])):
        print(f"  {val:>15}: {count:>5}")

    # Sample records
    print("\n" + "-" * 70)
    print("SAMPLE TRANSFORMATIONS (first 3 records)")
    print("-" * 70)

    for i, ((doc_id, original), rec) in enumerate(zip(data[:3], transformed[:3])):
        print(f"\n--- Record {i+1} ---")
        print(f"  Firestore doc ID:  {doc_id}")
        print(f"  file_id:           {rec['file_id']}")
        print(f"  filename:          {rec['filename'][:60]}")
        print(f"  subject:           {rec['subject']}")
        print(f"  grade:             {rec['grade']}")
        print(f"  document_type:     {rec['document_type']}")
        print(f"  year:              {rec['year']}")
        print(f"  session:           {rec['session']}")
        print(f"  storage_path:      {(rec.get('storage_path') or '')[:60]}")
        print(f"  status:            {rec['status']}")

    if transform_errors:
        print("\n" + "-" * 70)
        print(f"TRANSFORM ERRORS (first 5 of {len(transform_errors)})")
        print("-" * 70)
        for doc_id, err in transform_errors[:5]:
            print(f"  {doc_id}: {err}")

    print("\n" + "=" * 70)
    print("To execute: python scripts/migrate_firestore_to_supabase.py --run")
    print("=" * 70 + "\n")


def run_migration(collection: str = "scraped_files") -> None:
    """Execute migration to Supabase."""
    config = COLLECTIONS[collection]
    supabase = initialize_supabase()

    data = load_firestore_collection(config["firestore_collection"])
    if not data:
        print(f"No documents found in {config['firestore_collection']}")
        return

    # Transform
    logger.info("Transforming records...")
    records = []
    errors = []
    for doc_id, doc_data in data:
        try:
            record = transform_scraped_file(doc_id, doc_data)
            records.append(record)
        except Exception as e:
            errors.append({"doc_id": doc_id, "error": str(e)})
            logger.error(f"Transform error for {doc_id}: {e}")

    logger.info(f"Transformed {len(records)} records ({len(errors)} errors)")

    # Deduplicate by file_id (keep last occurrence)
    seen = {}
    for rec in records:
        seen[rec["file_id"]] = rec
    unique_records = list(seen.values())

    if len(unique_records) != len(records):
        logger.warning(
            f"Deduplicated: {len(records)} -> {len(unique_records)} "
            f"({len(records) - len(unique_records)} duplicates removed)"
        )

    # Upsert in batches
    table = config["supabase_table"]
    logger.info(f"Upserting {len(unique_records)} records to {table} in batches of {BATCH_SIZE}...")

    success_count = 0
    batch_errors = []

    try:
        from tqdm import tqdm
        iterator = tqdm(range(0, len(unique_records), BATCH_SIZE), desc="Migrating")
    except ImportError:
        iterator = range(0, len(unique_records), BATCH_SIZE)
        logger.info("(Install tqdm for progress bar)")

    for i in iterator:
        batch = unique_records[i : i + BATCH_SIZE]
        try:
            response = (
                supabase.table(table)
                .upsert(batch, on_conflict="file_id")
                .execute()
            )
            success_count += len(response.data)
        except Exception as e:
            batch_errors.append({"batch_start": i, "batch_size": len(batch), "error": str(e)})
            logger.error(f"Batch {i} error: {e}")

    # Report
    print("\n" + "=" * 70)
    print(f"MIGRATION RESULTS - {collection.upper()}")
    print("=" * 70)
    print(f"  Source documents:       {len(data)}")
    print(f"  Transformed:            {len(records)}")
    print(f"  After dedup:            {len(unique_records)}")
    print(f"  Successfully upserted:  {success_count}")
    print(f"  Transform errors:       {len(errors)}")
    print(f"  Batch errors:           {len(batch_errors)}")

    if batch_errors:
        print("\n  Batch Errors:")
        for err in batch_errors[:5]:
            print(f"    Batch {err['batch_start']}: {err['error'][:100]}")

    print(f"\nTo verify: python scripts/migrate_firestore_to_supabase.py --verify")
    print("=" * 70 + "\n")


def verify_migration(collection: str = "scraped_files") -> None:
    """Verify migration by comparing Firestore and Supabase counts."""
    config = COLLECTIONS[collection]
    supabase = initialize_supabase()

    # Source count
    data = load_firestore_collection(config["firestore_collection"])
    source_count = len(data)

    # Supabase count
    table = config["supabase_table"]
    response = supabase.table(table).select("id", count="exact").execute()
    db_count = response.count or 0

    # Status distribution in Supabase
    status_counts = {}
    for status in ["pending", "downloading", "downloaded", "processing", "completed", "failed"]:
        resp = supabase.table(table).select("id", count="exact").eq("status", status).execute()
        c = resp.count or 0
        if c > 0:
            status_counts[status] = c

    # Count records with new fields populated
    field_checks = {}
    for field in ["storage_path", "document_type", "year", "user_id"]:
        resp = supabase.table(table).select("id", count="exact").not_.is_(field, "null").execute()
        field_checks[field] = resp.count or 0

    # Spot-check 3 records
    spot_checks = []
    sample_indices = [0, len(data) // 2, -1] if len(data) >= 3 else list(range(len(data)))
    for idx in sample_indices:
        doc_id, doc_data = data[idx]
        filename = doc_data.get("filename", doc_id)
        file_id = doc_data.get("fileId") or generate_file_id(filename)

        result = supabase.table(table).select("*").eq("file_id", file_id).execute()
        found = len(result.data) > 0
        spot_checks.append({
            "filename": filename,
            "file_id": file_id,
            "found": found,
        })

    # Report
    print("\n" + "=" * 70)
    print(f"VERIFICATION RESULTS - {collection.upper()}")
    print("=" * 70)

    print(f"\nRecord Counts:")
    print(f"  Firestore: {source_count}")
    print(f"  Supabase:  {db_count}")

    if db_count >= source_count:
        print(f"  [OK] Supabase has all records")
    else:
        print(f"  [WARN] Missing {source_count - db_count} records in Supabase")

    print(f"\nStatus Distribution (Supabase):")
    for status, count in sorted(status_counts.items()):
        pct = count / db_count * 100 if db_count else 0
        print(f"  {status:>15}: {count:>5} ({pct:.1f}%)")

    print(f"\nNew Fields Populated:")
    for field, count in field_checks.items():
        pct = count / db_count * 100 if db_count else 0
        print(f"  {field:>20}: {count:>5} / {db_count} ({pct:.1f}%)")

    print(f"\nSpot Checks:")
    all_ok = True
    for check in spot_checks:
        mark = "[OK]" if check["found"] else "[MISSING]"
        print(f"  {mark} {check['filename'][:50]}")
        if not check["found"]:
            all_ok = False

    if all_ok and db_count >= source_count:
        print(f"\n[SUCCESS] Migration verification PASSED")
    else:
        print(f"\n[FAILED] Migration verification has issues - review above")

    print("=" * 70 + "\n")


# ============================================================================
# CLI
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Firestore collections to Supabase"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Preview migration without writing")
    group.add_argument("--run", action="store_true", help="Execute migration")
    group.add_argument("--verify", action="store_true", help="Verify migration counts")

    parser.add_argument(
        "--collection",
        choices=list(COLLECTIONS.keys()),
        default="scraped_files",
        help="Collection to migrate (default: scraped_files)",
    )

    args = parser.parse_args()

    if args.dry_run:
        dry_run(args.collection)
    elif args.run:
        run_migration(args.collection)
    elif args.verify:
        verify_migration(args.collection)


if __name__ == "__main__":
    main()
