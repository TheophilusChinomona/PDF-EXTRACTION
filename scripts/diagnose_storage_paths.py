#!/usr/bin/env python3
"""
Diagnose storage path mismatches between scraped_files table and Firebase Storage.

Compares storage_path values in Supabase with actual blob names in Firebase Storage
to identify why downloads fail (404s). Prints a diagnostic report showing the
mismatch pattern (URL encoding, prefix differences, missing files, etc.).

Usage:
    python scripts/diagnose_storage_paths.py
    python scripts/diagnose_storage_paths.py --limit 50
    python scripts/diagnose_storage_paths.py --validated-only
"""

import argparse
import os
import sys
from collections import Counter
from typing import Any
from urllib.parse import quote, unquote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client, Client

from app.services.firebase_client import list_blobs, blob_exists, _get_client
from app.config import get_settings


DEFAULT_BUCKET = "scrapperdb-f854d.firebasestorage.app"


def _get_service_role_client() -> Client:
    settings = get_settings()
    url = settings.supabase_url
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or settings.supabase_key
    return create_client(url, service_key)


def _fetch_db_storage_paths(client: Client, validated_only: bool, limit: int) -> list[dict[str, Any]]:
    """Fetch scraped_files rows with storage_path populated."""
    query = (
        client.table("scraped_files")
        .select("id, storage_path, storage_bucket, filename, download_url")
    )
    if validated_only:
        # Join through validation_results to get only validated files
        vr = (
            client.table("validation_results")
            .select("scraped_file_id")
            .eq("status", "correct")
            .limit(limit)
            .execute()
        )
        validated_ids = [str(r["scraped_file_id"]) for r in (vr.data or []) if r.get("scraped_file_id")]
        if not validated_ids:
            return []
        query = query.in_("id", validated_ids)
    query = query.not_.is_("storage_path", "null").limit(limit)
    result = query.execute()
    return result.data or []


def _normalize_path(path: str) -> str:
    """Normalize a storage path by URL-decoding and stripping leading slashes."""
    decoded = unquote(path)
    return decoded.lstrip("/")


def _try_find_match(db_path: str, blob_set: set[str], blob_list: list[str]) -> tuple[str | None, str]:
    """Try various transformations to find a matching blob for a DB path.

    Returns (matched_blob_name, match_type) where match_type describes the fix needed.
    """
    normalized = _normalize_path(db_path)

    # Exact match
    if normalized in blob_set:
        return normalized, "exact"

    # URL-encoded match: the DB has decoded path, blob has encoded
    encoded = quote(normalized, safe="/")
    if encoded in blob_set:
        return encoded, "needs_url_encode"

    # Double-decoded: DB path was decoded twice
    double_decoded = _normalize_path(unquote(normalized))
    if double_decoded in blob_set:
        return double_decoded, "double_decoded"

    # Prefix variations
    common_prefixes = ["pdfs/", "scraped_files/", "uploads/", ""]
    base_name = normalized
    # Strip any known prefix from DB path
    for prefix in common_prefixes:
        if prefix and normalized.startswith(prefix):
            base_name = normalized[len(prefix):]
            break

    # Try adding each prefix
    for prefix in common_prefixes:
        candidate = prefix + base_name
        if candidate in blob_set:
            return candidate, f"prefix_mismatch(db='{db_path[:30]}', blob_prefix='{prefix}')"
        encoded_candidate = quote(candidate, safe="/")
        if encoded_candidate in blob_set:
            return encoded_candidate, f"prefix+encode(blob_prefix='{prefix}')"

    # Filename-only match (last resort)
    filename = normalized.rsplit("/", 1)[-1] if "/" in normalized else normalized
    matches = [b for b in blob_list if b.endswith("/" + filename) or b == filename]
    if len(matches) == 1:
        return matches[0], f"filename_match(db='{normalized}', blob='{matches[0]}')"
    if len(matches) > 1:
        return None, f"filename_ambiguous({len(matches)} blobs match '{filename}')"

    return None, "not_found"


def run(validated_only: bool, limit: int, check_exists: bool) -> None:
    client = _get_service_role_client()

    # 1. Fetch DB rows
    print(f"Fetching scraped_files storage paths (limit={limit}, validated_only={validated_only})...")
    rows = _fetch_db_storage_paths(client, validated_only, limit)
    if not rows:
        print("No rows found with storage_path populated.")
        return
    print(f"  Found {len(rows)} rows with storage_path in DB")

    # 2. List actual blobs in Firebase Storage
    print(f"\nListing blobs in Firebase Storage bucket: {DEFAULT_BUCKET}")
    try:
        all_blobs = list_blobs(DEFAULT_BUCKET)
    except Exception as e:
        print(f"  ERROR listing blobs: {e}")
        print("  Falling back to per-file exists check...")
        check_exists = True
        all_blobs = []

    if all_blobs:
        print(f"  Found {len(all_blobs)} blobs in bucket")
        # Show prefix distribution
        prefixes = Counter()
        for b in all_blobs:
            prefix = b.split("/")[0] if "/" in b else "(root)"
            prefixes[prefix] += 1
        print(f"  Blob prefix distribution (top 10):")
        for prefix, count in prefixes.most_common(10):
            print(f"    {prefix:40s} : {count}")

    blob_set = set(all_blobs)

    # 3. Compare DB paths with actual blobs
    print(f"\n{'='*70}")
    print("COMPARING DB storage_path vs Firebase Storage blobs")
    print(f"{'='*70}")

    match_types = Counter()
    mismatches: list[dict] = []
    exact_matches = 0

    for row in rows:
        db_path = (row.get("storage_path") or "").strip()
        if not db_path:
            match_types["empty_path"] += 1
            continue

        if check_exists and not all_blobs:
            # Fallback: check each file individually
            bucket = (row.get("storage_bucket") or DEFAULT_BUCKET).strip()
            gs_url = f"gs://{bucket}/{db_path.lstrip('/')}"
            if blob_exists(gs_url):
                match_types["exact"] += 1
                exact_matches += 1
            else:
                match_types["not_found"] += 1
                mismatches.append({
                    "id": row["id"],
                    "db_path": db_path,
                    "match_type": "not_found",
                    "matched_blob": None,
                    "filename": row.get("filename"),
                })
        else:
            matched_blob, match_type = _try_find_match(db_path, blob_set, all_blobs)
            match_types[match_type] += 1
            if match_type == "exact":
                exact_matches += 1
            else:
                mismatches.append({
                    "id": row["id"],
                    "db_path": db_path,
                    "match_type": match_type,
                    "matched_blob": matched_blob,
                    "filename": row.get("filename"),
                })

    # 4. Print report
    total = len(rows)
    print(f"\nResults ({total} files checked):")
    print(f"  Exact matches:   {exact_matches} ({exact_matches/total*100:.1f}%)")
    print(f"  Mismatches:      {len(mismatches)} ({len(mismatches)/total*100:.1f}%)")

    print(f"\nMatch type breakdown:")
    for mtype, count in match_types.most_common():
        print(f"  {mtype:45s} : {count:>5} ({count/total*100:.1f}%)")

    # Show fixable vs unfixable
    fixable = [m for m in mismatches if m["matched_blob"] is not None]
    unfixable = [m for m in mismatches if m["matched_blob"] is None]
    print(f"\nFixable (blob found with different path): {len(fixable)}")
    print(f"Unfixable (blob not found in bucket):     {len(unfixable)}")

    if fixable:
        print(f"\n{'='*70}")
        print(f"FIXABLE MISMATCHES (first 20)")
        print(f"{'='*70}")
        for m in fixable[:20]:
            print(f"\n  ID: {m['id']}")
            print(f"  Filename:     {m['filename']}")
            print(f"  DB path:      {m['db_path'][:80]}")
            print(f"  Actual blob:  {m['matched_blob'][:80] if m['matched_blob'] else 'N/A'}")
            print(f"  Fix type:     {m['match_type']}")

    if unfixable:
        print(f"\n{'='*70}")
        print(f"UNFIXABLE - NOT FOUND IN BUCKET (first 20)")
        print(f"{'='*70}")
        for m in unfixable[:20]:
            print(f"\n  ID: {m['id']}")
            print(f"  Filename:  {m['filename']}")
            print(f"  DB path:   {m['db_path'][:80]}")

    # Summary / recommended action
    print(f"\n{'='*70}")
    print("RECOMMENDED ACTION")
    print(f"{'='*70}")
    if exact_matches == total:
        print("  All paths match! The issue may be in _build_storage_url() or bucket name.")
    elif fixable:
        dominant_type = Counter(m["match_type"] for m in fixable).most_common(1)[0]
        print(f"  Dominant mismatch: {dominant_type[0]} ({dominant_type[1]} files)")
        print(f"  Run: python scripts/fix_storage_paths.py --dry-run")
        print(f"  Then: python scripts/fix_storage_paths.py --run")
    elif unfixable:
        print(f"  {len(unfixable)} files not found in bucket at all.")
        print("  These PDFs may have been deleted from Firebase Storage.")
        print("  The extraction script's --min-files flag will let it proceed with available files.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose storage path mismatches between DB and Firebase Storage")
    parser.add_argument("--limit", type=int, default=200, help="Max rows to check (default: 200)")
    parser.add_argument("--validated-only", action="store_true", help="Only check validated files")
    parser.add_argument("--check-exists", action="store_true", help="Check each file individually (slow but works if list_blobs fails)")
    args = parser.parse_args()
    run(validated_only=args.validated_only, limit=args.limit, check_exists=args.check_exists)


if __name__ == "__main__":
    main()
