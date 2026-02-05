#!/usr/bin/env python3
"""
Register missing PDFs in scraped_files and link orphan extractions.

For extractions/memo_extractions that have no scraped_file_id:
1. List files in Firebase Storage to find the actual storage paths.
2. Match each extraction's file_name (with or without hash prefix) to a storage path.
3. Create a scraped_files record with storage_path and metadata from the extraction.
4. Update the extraction with the new scraped_file_id.

Usage:
  python scripts/register_and_link_extractions.py --dry-run   # Report only
  python scripts/register_and_link_extractions.py              # Create records and link
"""

import hashlib
import os
import re
import sys
import asyncio
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import get_supabase_client
from app.services.firebase_client import list_blobs


# Default bucket (from existing scraped_files)
DEFAULT_STORAGE_BUCKET = "scrapperdb-f854d.firebasestorage.app"
STORAGE_PREFIX = "pdfs/"


def _normalize_filename(file_name: str) -> str:
    """Remove hash prefix (12 hex chars + '-') from extraction file_name."""
    return re.sub(r"^[a-f0-9]{12}-", "", file_name).strip()


def _safe_int(v) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _make_file_id(storage_path: str) -> str:
    """Generate a deterministic file_id for scraped_files (32-char hex)."""
    return hashlib.md5(storage_path.encode()).hexdigest()


def _subject_to_keywords(subject: str | None) -> list[str]:
    """Extract searchable keywords from subject (e.g. 'IsiZulu Ulimi Lwasekhaya (HL) P1' -> ['isizulu', 'hl', 'p1'])."""
    if not subject:
        return []
    s = re.sub(r"[()]", " ", (subject or "").lower())
    words = re.findall(r"[a-z0-9]+", s)
    # Drop very short and generic words
    return [w for w in words if len(w) > 1 and w not in ("the", "and", "for", "ya", "la", "le")]


def _path_doc_type(path: str, is_memo: bool) -> bool:
    """True if path looks like QP (when is_memo=False) or Memorandum (when is_memo=True)."""
    name = path.split("/")[-1].lower() if "/" in path else path.lower()
    if is_memo:
        return "memo" in name or "mg" in name or "mark-scheme" in name or "mark_scheme" in name
    return "memo" not in name and "mg" not in name and "mark-scheme" not in name and "mark_scheme" not in name


def _path_has_year(path: str, year: int | None) -> bool:
    if year is None:
        return True
    return str(year) in path


def find_storage_path_by_filename(
    filename: str, storage_paths: list[str]
) -> str | None:
    """
    Find a storage path that matches the extraction file_name.

    Tries: exact match on full path ending, then normalized filename (no hash).
    """
    if not filename:
        return None
    filename_lower = filename.lower()
    normalized = _normalize_filename(filename)
    normalized_lower = normalized.lower()
    # Match by path ending in the exact filename
    for path in storage_paths:
        path_lower = path.lower()
        if path_lower.endswith(filename_lower) or path_lower.endswith("/" + filename_lower):
            return path
    # Match by path ending in normalized filename (no hash)
    for path in storage_paths:
        path_lower = path.lower()
        base = path.split("/")[-1] if "/" in path else path
        if base.lower() == normalized_lower:
            return path
        if path_lower.endswith("/" + normalized_lower):
            return path
    # Match by path containing normalized stem (for truncated display names)
    stem = normalized_lower.replace(".pdf", "").replace(".mg", "")
    if len(stem) < 10:
        return None
    candidates = [p for p in storage_paths if stem in p.lower()]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        # Prefer path whose last segment starts with or equals normalized
        for p in candidates:
            seg = p.split("/")[-1].lower()
            if seg == normalized_lower or seg.startswith(normalized_lower[:20]):
                return p
        return candidates[0]
    return None


def find_storage_path_by_metadata(
    extraction: dict,
    storage_paths: list[str],
    is_memo: bool,
) -> str | None:
    """
    Find a storage path by matching extraction metadata (subject, year, document type).

    Storage filenames use patterns like "Subject-Grade-12-...-QP-May-June-2025.pdf".
    """
    year = _safe_int(extraction.get("year"))
    keywords = _subject_to_keywords(extraction.get("subject"))
    if not keywords:
        return None
    # Filter by year and document type
    candidates = [
        p for p in storage_paths
        if _path_has_year(p, year) and _path_doc_type(p, is_memo)
    ]
    path_lower = None
    best_path = None
    best_score = 0
    for path in candidates:
        path_lower = path.lower()
        score = sum(1 for k in keywords if k in path_lower)
        if score > best_score and score >= 2:
            best_score = score
            best_path = path
    return best_path


def build_scraped_file_record(
    extraction: dict,
    storage_path: str | None,
    document_type: str,
    bucket: str,
) -> dict:
    """Build a scraped_files insert row from extraction metadata."""
    filename = _normalize_filename(extraction.get("file_name") or "")
    if not filename and storage_path:
        filename = storage_path.split("/")[-1]
    if not filename:
        filename = f"unknown-{extraction.get('subject', 'doc') or 'doc'}.pdf"
    grade = _safe_int(extraction.get("grade"))
    # file_id must be unique; use storage_path if available else deterministic from metadata
    file_id_source = storage_path or f"{extraction.get('file_name')}{extraction.get('subject')}{extraction.get('year')}"
    return {
        "file_id": _make_file_id(file_id_source),
        "filename": filename[:500] if len(filename) > 500 else filename,
        "storage_path": storage_path,
        "storage_bucket": bucket if storage_path else None,
        "subject": extraction.get("subject"),
        "year": _safe_int(extraction.get("year")),
        "grade": grade,
        "session": extraction.get("session"),
        "document_type": document_type,
        "validation_status": "validated",
        "status": "queued_for_extraction",
    }


async def process_extractions(
    client,
    storage_paths: list[str],
    bucket: str,
    dry_run: bool,
) -> tuple[int, int]:
    """Create scraped_files for orphan extractions and link them. Returns (linked, no_match)."""
    r = await asyncio.to_thread(
        lambda: client.table("extractions")
        .select("id, file_name, subject, year, grade, session")
        .is_("scraped_file_id", "null")
        .execute()
    )
    rows = r.data or []
    linked = 0
    no_match = 0
    for row in rows:
        eid = row["id"]
        file_name = row.get("file_name") or ""
        path = find_storage_path_by_filename(file_name, storage_paths)
        if not path:
            path = find_storage_path_by_metadata(row, storage_paths, is_memo=False)
        if not path:
            # Still create scraped_file with null storage_path so we have consistent ID and link
            path = None
        if dry_run:
            print(f"  [extractions] {eid} -> would create scraped_file and link ({path or 'no storage path'}) ({file_name[:45]})")
            linked += 1
            continue
        record = build_scraped_file_record(row, path, "Question Paper", bucket)
        try:
            ins = await asyncio.to_thread(
                lambda r=record: client.table("scraped_files").insert(r).execute()
            )
            if ins.data:
                scraped_id = ins.data[0]["id"]
            else:
                # Duplicate file_id: fetch existing scraped_file by file_id
                existing = await asyncio.to_thread(
                    lambda r=record: client.table("scraped_files")
                    .select("id")
                    .eq("file_id", r["file_id"])
                    .limit(1)
                    .execute()
                )
                if not existing.data:
                    print(f"  [extractions] {eid} insert failed")
                    no_match += 1
                    continue
                scraped_id = existing.data[0]["id"]
            await asyncio.to_thread(
                lambda eid=eid, scraped_id=scraped_id: client.table("extractions")
                .update({"scraped_file_id": scraped_id})
                .eq("id", eid)
                .execute()
            )
            path_info = path[:40] + "..." if path and len(path) > 40 else (path or "no path")
            print(f"  [extractions] {eid} -> scraped_file_id={scraped_id} ({path_info})")
            linked += 1
        except Exception as e:
            err = str(e)
            if "23505" in err and "file_id" in err:
                # Duplicate file_id: use existing scraped_file
                try:
                    existing = await asyncio.to_thread(
                        lambda r=record: client.table("scraped_files")
                        .select("id")
                        .eq("file_id", r["file_id"])
                        .limit(1)
                        .execute()
                    )
                    if existing.data:
                        scraped_id = existing.data[0]["id"]
                        await asyncio.to_thread(
                            lambda eid=eid, scraped_id=scraped_id: client.table("extractions")
                            .update({"scraped_file_id": scraped_id})
                            .eq("id", eid)
                            .execute()
                        )
                        path_info = path[:40] + "..." if path and len(path) > 40 else (path or "no path")
                        print(f"  [extractions] {eid} -> scraped_file_id={scraped_id} (existing) ({path_info})")
                        linked += 1
                    else:
                        no_match += 1
                except Exception as e2:
                    print(f"  [extractions] {eid} error: {e2}")
                    no_match += 1
            else:
                print(f"  [extractions] {eid} error: {e}")
                no_match += 1
    return linked, no_match


async def process_memo_extractions(
    client,
    storage_paths: list[str],
    bucket: str,
    dry_run: bool,
) -> tuple[int, int]:
    """Create scraped_files for orphan memo_extractions and link them. Returns (linked, no_match)."""
    r = await asyncio.to_thread(
        lambda: client.table("memo_extractions")
        .select("id, file_name, subject, year, grade, session")
        .is_("scraped_file_id", "null")
        .execute()
    )
    rows = r.data or []
    linked = 0
    no_match = 0
    for row in rows:
        eid = row["id"]
        file_name = row.get("file_name") or ""
        path = find_storage_path_by_filename(file_name, storage_paths)
        if not path:
            path = find_storage_path_by_metadata(row, storage_paths, is_memo=True)
        if not path:
            path = None
        if dry_run:
            print(f"  [memo_extractions] {eid} -> would create scraped_file and link ({path or 'no storage path'}) ({file_name[:45]})")
            linked += 1
            continue
        record = build_scraped_file_record(row, path, "Memorandum", bucket)
        try:
            ins = await asyncio.to_thread(
                lambda r=record: client.table("scraped_files").insert(r).execute()
            )
            if ins.data:
                scraped_id = ins.data[0]["id"]
            else:
                existing = await asyncio.to_thread(
                    lambda r=record: client.table("scraped_files")
                    .select("id")
                    .eq("file_id", r["file_id"])
                    .limit(1)
                    .execute()
                )
                if not existing.data:
                    print(f"  [memo_extractions] {eid} insert failed")
                    no_match += 1
                    continue
                scraped_id = existing.data[0]["id"]
            await asyncio.to_thread(
                lambda eid=eid, scraped_id=scraped_id: client.table("memo_extractions")
                .update({"scraped_file_id": scraped_id})
                .eq("id", eid)
                .execute()
            )
            path_info = path[:40] + "..." if path and len(path) > 40 else (path or "no path")
            print(f"  [memo_extractions] {eid} -> scraped_file_id={scraped_id} ({path_info})")
            linked += 1
        except Exception as e:
            err = str(e)
            if "23505" in err and "file_id" in err:
                try:
                    existing = await asyncio.to_thread(
                        lambda r=record: client.table("scraped_files")
                        .select("id")
                        .eq("file_id", r["file_id"])
                        .limit(1)
                        .execute()
                    )
                    if existing.data:
                        scraped_id = existing.data[0]["id"]
                        await asyncio.to_thread(
                            lambda eid=eid, scraped_id=scraped_id: client.table("memo_extractions")
                            .update({"scraped_file_id": scraped_id})
                            .eq("id", eid)
                            .execute()
                        )
                        path_info = path[:40] + "..." if path and len(path) > 40 else (path or "no path")
                        print(f"  [memo_extractions] {eid} -> scraped_file_id={scraped_id} (existing) ({path_info})")
                        linked += 1
                    else:
                        no_match += 1
                except Exception as e2:
                    print(f"  [memo_extractions] {eid} error: {e2}")
                    no_match += 1
            else:
                print(f"  [memo_extractions] {eid} error: {e}")
                no_match += 1
    return linked, no_match


async def main(dry_run: bool, bucket: str) -> None:
    client = get_supabase_client()
    print("=" * 70)
    print("REGISTER MISSING PDFs AND LINK EXTRACTIONS")
    print(f"Mode: {'DRY RUN (no writes)' if dry_run else 'LIVE'}")
    print(f"Bucket: {bucket}")
    print("=" * 70)

    print("\nListing Firebase Storage files...")
    try:
        storage_paths = list_blobs(bucket, STORAGE_PREFIX)
    except Exception as e:
        print(f"Failed to list storage: {e}")
        return
    print(f"  Found {len(storage_paths)} paths under {STORAGE_PREFIX}")

    print("\nExtractions (Question Papers):")
    ext_linked, ext_no = await process_extractions(client, storage_paths, bucket, dry_run)
    print(f"  -> Linked: {ext_linked}, No match: {ext_no}")

    print("\nMemo extractions (Memoranda):")
    memo_linked, memo_no = await process_memo_extractions(
        client, storage_paths, bucket, dry_run
    )
    print(f"  -> Linked: {memo_linked}, No match: {memo_no}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Extractions linked:     {ext_linked}")
    print(f"  Memo extractions linked: {memo_linked}")
    if dry_run:
        print("  (Dry run: no changes written)")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Register missing PDFs in scraped_files and link orphan extractions"
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only, do not create or update")
    parser.add_argument(
        "--bucket",
        default=DEFAULT_STORAGE_BUCKET,
        help=f"Firebase Storage bucket (default: {DEFAULT_STORAGE_BUCKET})",
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run, bucket=args.bucket))
