#!/usr/bin/env python3
"""
Fix storage_path for scraped_files with source_url containing education.gov.za.

Uses the Firebase (GCS) SDK to list actual blob paths, then matches each row by
path (exact, prefix variations, or filename) and updates storage_path when the
current path 404s.

Usage:
    python scripts/fix_storage_paths_education_gov_za.py --dry-run
    python scripts/fix_storage_paths_education_gov_za.py --run
"""

import argparse
import os
import sys
from urllib.parse import quote, unquote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client, Client

from app.services.firebase_client import list_blobs
from app.config import get_settings


DEFAULT_BUCKET = "scrapperdb-f854d.firebasestorage.app"
SOURCE_URL_SUBSTRING = "education.gov.za"
PAGE_SIZE = 200


def _get_service_role_client() -> Client:
    settings = get_settings()
    url = settings.supabase_url
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or settings.supabase_key
    return create_client(url, key)


def _normalize_path(path: str) -> str:
    return unquote(path).lstrip("/")


def _find_correct_blob(
    db_path: str,
    blob_set: set[str],
    blob_list: list[str],
) -> str | None:
    """Find the correct blob path for a DB storage_path. Returns None if already correct or not found."""
    normalized = _normalize_path(db_path)
    if normalized in blob_set:
        return None

    encoded = quote(normalized, safe="/")
    if encoded in blob_set:
        return encoded

    double_decoded = _normalize_path(unquote(normalized))
    if double_decoded in blob_set:
        return double_decoded

    common_prefixes = ["pdfs/", "downloads/", "scraped_files/", "uploads/", ""]
    base_name = normalized
    for p in common_prefixes:
        if p and normalized.startswith(p):
            base_name = normalized[len(p):]
            break

    for p in common_prefixes:
        candidate = p + base_name
        if candidate in blob_set:
            return candidate
        enc = quote(candidate, safe="/")
        if enc in blob_set:
            return enc

    filename = normalized.rsplit("/", 1)[-1] if "/" in normalized else normalized
    matches = [b for b in blob_list if b.endswith("/" + filename) or b == filename]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        for m in matches:
            if "education" in m.lower() or "gov" in m.lower() or "pdfs/" in m:
                return m
        return matches[0]

    return None


def run(dry_run: bool) -> None:
    client = _get_service_role_client()

    print("Listing blobs in Firebase Storage (pdfs/ and downloads/)...")
    try:
        blobs_pdfs = list_blobs(DEFAULT_BUCKET, prefix="pdfs/", max_results=60_000)
        blobs_downloads = list_blobs(DEFAULT_BUCKET, prefix="downloads/", max_results=5_000)
        all_blobs = list(dict.fromkeys(blobs_pdfs + blobs_downloads))
    except Exception as e:
        print(f"ERROR listing blobs: {e}")
        return
    print(f"  Found {len(all_blobs)} blobs (pdfs: {len(blobs_pdfs)}, downloads: {len(blobs_downloads)})")
    blob_set = set(all_blobs)

    print(f"Fetching scraped_files where source_url ILIKE '%{SOURCE_URL_SUBSTRING}%'...")
    rows: list[dict] = []
    offset = 0
    while True:
        q = (
            client.table("scraped_files")
            .select("id, storage_path, storage_bucket, filename")
            .ilike("source_url", f"%{SOURCE_URL_SUBSTRING}%")
            .not_.is_("storage_path", "null")
            .order("id")
            .range(offset, offset + PAGE_SIZE - 1)
        )
        r = q.execute()
        data = r.data or []
        rows.extend(data)
        if len(data) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    seen: set[str] = set()
    unique_rows: list[dict] = []
    for row in rows:
        uid = str(row.get("id"))
        if uid not in seen:
            seen.add(uid)
            unique_rows.append(row)
    rows = unique_rows
    print(f"  Found {len(rows)} rows with storage_path")

    fixes: list[dict] = []
    already_ok = 0
    not_found = 0
    not_found_rows: list[dict] = []

    for row in rows:
        db_path = (row.get("storage_path") or "").strip()
        if not db_path:
            continue
        normalized = _normalize_path(db_path)
        if normalized in blob_set:
            already_ok += 1
            continue
        correct = _find_correct_blob(db_path, blob_set, all_blobs)
        if correct is None:
            not_found += 1
            not_found_rows.append({"id": row["id"], "storage_path": db_path, "filename": row.get("filename")})
            continue
        fixes.append({
            "id": row["id"],
            "old_path": db_path,
            "new_path": correct,
            "filename": row.get("filename"),
        })

    print(f"\nResults: already_ok={already_ok} to_fix={len(fixes)} not_found={not_found}")
    if not_found_rows:
        print("Not found in Firebase (no matching blob):")
        for r in not_found_rows[:20]:
            print(f"  id={r['id']} path={r['storage_path']} filename={r['filename']}")

    if not fixes:
        print("No fixes to apply.")
        return

    print(f"\nSample fixes (first 10):")
    for f in fixes[:10]:
        print(f"  {f['filename']}")
        print(f"    old: {f['old_path'][:70]}")
        print(f"    new: {f['new_path'][:70]}")

    if dry_run:
        print(f"\nDry run: {len(fixes)} rows would be updated. Run with --run to apply.")
        return

    print(f"\nApplying {len(fixes)} updates...")
    ok, err = 0, 0
    for i, f in enumerate(fixes, 1):
        try:
            client.table("scraped_files").update({"storage_path": f["new_path"]}).eq("id", f["id"]).execute()
            ok += 1
            if ok % 100 == 0:
                print(f"  [{i}/{len(fixes)}] {ok} updated")
        except Exception as e:
            err += 1
            print(f"  ERROR {f['id']}: {e}")
    print(f"Done: {ok} updated, {err} errors.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix storage_path for education.gov.za scraped_files using Firebase Storage.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Preview fixes only.")
    group.add_argument("--run", action="store_true", help="Apply fixes to DB.")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
