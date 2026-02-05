#!/usr/bin/env python3
"""
Fix storage_path values in scraped_files to match actual Firebase Storage blob names.

Run diagnose_storage_paths.py first to understand the mismatch pattern, then use this
script to apply fixes.

Usage:
    # Preview fixes without writing
    python scripts/fix_storage_paths.py --dry-run

    # Apply fixes
    python scripts/fix_storage_paths.py --run

    # Only fix validated files
    python scripts/fix_storage_paths.py --dry-run --validated-only

    # Limit scope
    python scripts/fix_storage_paths.py --dry-run --limit 50
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

from app.services.firebase_client import list_blobs
from app.config import get_settings


DEFAULT_BUCKET = "scrapperdb-f854d.firebasestorage.app"


def _get_service_role_client() -> Client:
    settings = get_settings()
    url = settings.supabase_url
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or settings.supabase_key
    return create_client(url, service_key)


def _normalize_path(path: str) -> str:
    return unquote(path).lstrip("/")


def _find_correct_blob(db_path: str, blob_set: set[str], blob_list: list[str]) -> str | None:
    """Try to find the correct blob name for a given DB storage_path.

    Returns the correct blob name or None if no match found.
    """
    normalized = _normalize_path(db_path)

    # Already correct
    if normalized in blob_set:
        return None  # No fix needed

    # URL-encoded match
    encoded = quote(normalized, safe="/")
    if encoded in blob_set:
        return encoded

    # Double-decoded
    double_decoded = _normalize_path(unquote(normalized))
    if double_decoded in blob_set:
        return double_decoded

    # Prefix variations
    common_prefixes = ["pdfs/", "scraped_files/", "uploads/", ""]
    base_name = normalized
    for prefix in common_prefixes:
        if prefix and normalized.startswith(prefix):
            base_name = normalized[len(prefix):]
            break

    for prefix in common_prefixes:
        candidate = prefix + base_name
        if candidate in blob_set:
            return candidate
        encoded_candidate = quote(candidate, safe="/")
        if encoded_candidate in blob_set:
            return encoded_candidate

    # Filename-only match
    filename = normalized.rsplit("/", 1)[-1] if "/" in normalized else normalized
    matches = [b for b in blob_list if b.endswith("/" + filename) or b == filename]
    if len(matches) == 1:
        return matches[0]

    return None


def run(dry_run: bool, validated_only: bool, limit: int) -> None:
    client = _get_service_role_client()

    # 1. List actual blobs
    print(f"Listing blobs in Firebase Storage bucket: {DEFAULT_BUCKET}...")
    try:
        all_blobs = list_blobs(DEFAULT_BUCKET)
    except Exception as e:
        print(f"ERROR: Could not list blobs: {e}")
        print("Cannot fix paths without knowing actual blob names.")
        return

    print(f"  Found {len(all_blobs)} blobs")
    blob_set = set(all_blobs)

    # 2. Fetch DB rows
    print(f"Fetching scraped_files storage paths (limit={limit})...")
    if validated_only:
        vr = (
            client.table("validation_results")
            .select("scraped_file_id")
            .eq("status", "correct")
            .limit(limit)
            .execute()
        )
        validated_ids = [str(r["scraped_file_id"]) for r in (vr.data or []) if r.get("scraped_file_id")]
        if not validated_ids:
            print("No validated files found.")
            return
        query = (
            client.table("scraped_files")
            .select("id, storage_path, storage_bucket, filename")
            .in_("id", validated_ids)
            .not_.is_("storage_path", "null")
        )
    else:
        query = (
            client.table("scraped_files")
            .select("id, storage_path, storage_bucket, filename")
            .not_.is_("storage_path", "null")
            .limit(limit)
        )

    rows = query.execute().data or []
    print(f"  Found {len(rows)} rows with storage_path")

    # 3. Find fixes
    fixes: list[dict[str, Any]] = []
    already_correct = 0
    not_found = 0
    fix_types = Counter()

    for row in rows:
        db_path = (row.get("storage_path") or "").strip()
        if not db_path:
            continue

        correct_blob = _find_correct_blob(db_path, blob_set, all_blobs)
        if correct_blob is None:
            # Either already correct or not found
            normalized = _normalize_path(db_path)
            if normalized in blob_set:
                already_correct += 1
            else:
                not_found += 1
        else:
            fixes.append({
                "id": row["id"],
                "old_path": db_path,
                "new_path": correct_blob,
                "filename": row.get("filename"),
            })
            # Categorize the fix
            if correct_blob == quote(_normalize_path(db_path), safe="/"):
                fix_types["url_encode"] += 1
            elif correct_blob == _normalize_path(unquote(_normalize_path(db_path))):
                fix_types["double_decode"] += 1
            else:
                fix_types["other"] += 1

    # 4. Report
    print(f"\nResults ({len(rows)} rows checked):")
    print(f"  Already correct: {already_correct}")
    print(f"  Need fixing:     {len(fixes)}")
    print(f"  Not found:       {not_found}")

    if fix_types:
        print(f"\nFix type breakdown:")
        for ftype, count in fix_types.most_common():
            print(f"  {ftype:30s} : {count}")

    if fixes:
        print(f"\nFixes to apply (first 20):")
        for f in fixes[:20]:
            print(f"  ID: {f['id']}")
            print(f"    old: {f['old_path'][:80]}")
            print(f"    new: {f['new_path'][:80]}")

    if dry_run:
        if fixes:
            print(f"\nDry run complete. {len(fixes)} rows would be updated.")
            print("Run with --run to apply fixes.")
        else:
            print("\nNo fixes needed.")
        return

    # 5. Apply fixes
    if not fixes:
        print("\nNo fixes to apply.")
        return

    print(f"\nApplying {len(fixes)} fixes...")
    success = 0
    errors = 0
    for i, f in enumerate(fixes, 1):
        try:
            client.table("scraped_files").update(
                {"storage_path": f["new_path"]}
            ).eq("id", f["id"]).execute()
            success += 1
            if success % 20 == 0:
                print(f"  [{i}/{len(fixes)}] {success} updated, {errors} errors")
        except Exception as e:
            errors += 1
            print(f"  ERROR updating {f['id']}: {e}")

    print(f"\nDone: {success} updated, {errors} errors out of {len(fixes)} fixes.")
    if success > 0:
        print("Re-run the extraction script:")
        print("  python scripts/run_extraction_batch_from_validated.py --dry-run")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix storage_path values in scraped_files to match Firebase Storage blob names.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Preview fixes without writing to DB.")
    group.add_argument("--run", action="store_true", help="Apply fixes to DB.")
    parser.add_argument("--validated-only", action="store_true", help="Only fix validated files.")
    parser.add_argument("--limit", type=int, default=500, help="Max rows to process (default: 500).")
    args = parser.parse_args()
    run(dry_run=args.dry_run, validated_only=args.validated_only, limit=args.limit)


if __name__ == "__main__":
    main()
