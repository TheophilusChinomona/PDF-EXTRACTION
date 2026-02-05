#!/usr/bin/env python3
"""
Backfill scraped_file_id on extractions and memo_extractions that were uploaded
from local JSON without linking to scraped_files.

Matching strategies (in order):
  1. Normalized filename: strip hash prefix from file_name, match scraped_files.filename (ilike).
  2. Metadata: subject + year + grade + session (only when exactly one scraped_file matches).

Usage:
  python scripts/backfill_scraped_file_ids.py --dry-run   # Report only
  python scripts/backfill_scraped_file_ids.py             # Apply updates
"""

import os
import re
import sys
import asyncio
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import get_supabase_client


def _normalize_filename(file_name: str) -> str:
    """Remove hash prefix (12 hex chars + '-') from extraction file_name."""
    return re.sub(r"^[a-f0-9]{12}-", "", file_name).strip()


def _normalize_subject(s: str | None) -> str:
    """Lowercase and strip for fuzzy subject comparison."""
    if s is None:
        return ""
    return (s or "").strip().lower()


def _safe_int(v) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _safe_str(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


async def _find_scraped_file_by_filename(client, filename: str, document_type: str):
    """Match scraped_files by normalized filename. Returns id or None."""
    clean = _normalize_filename(filename)
    if not clean:
        return None
    # Also try with .pdf in case scraped_files has no extension
    stem = clean.replace(".pdf", "").replace(".PDF", "")
    try:
        # Prefer exact match on filename (case-insensitive)
        r = await asyncio.to_thread(
            lambda: client.table("scraped_files")
            .select("id")
            .ilike("filename", clean)
            .eq("validation_status", "validated")
            .eq("document_type", document_type)
            .limit(2)
            .execute()
        )
        if r.data and len(r.data) == 1:
            return str(r.data[0]["id"])
        # Fallback: filename contains stem
        r = await asyncio.to_thread(
            lambda: client.table("scraped_files")
            .select("id")
            .ilike("filename", f"%{stem}%")
            .eq("validation_status", "validated")
            .eq("document_type", document_type)
            .limit(2)
            .execute()
        )
        if r.data and len(r.data) == 1:
            return str(r.data[0]["id"])
    except Exception:
        pass
    return None


async def _find_scraped_file_by_metadata(
    client, subject: str | None, year: int | None, grade: str | None, session: str | None, document_type: str
):
    """Match scraped_files by subject + year + grade + session when unique. Returns id or None."""
    year_n = _safe_int(year)
    grade_s = _safe_str(grade)
    grade_n = _safe_int(grade)
    session_s = _safe_str(session)
    subj_norm = _normalize_subject(subject)
    if not subj_norm:
        return None
    try:
        q = (
            client.table("scraped_files")
            .select("id, subject, year, grade, session")
            .eq("validation_status", "validated")
            .eq("document_type", document_type)
            .limit(20)
        )
        if year_n is not None:
            q = q.eq("year", year_n)
        r = await asyncio.to_thread(lambda: q.execute())
        if not r.data:
            return None
        # Filter in Python: subject similarity, optional grade/session
        candidates = []
        for row in r.data:
            if _normalize_subject(row.get("subject")) != subj_norm and subj_norm not in _normalize_subject(row.get("subject")) and _normalize_subject(row.get("subject")) not in subj_norm:
                continue
            if grade_s or grade_n is not None:
                g = row.get("grade")
                if g is not None and str(g).strip() != grade_s and _safe_int(g) != grade_n:
                    continue
            if session_s and row.get("session"):
                if session_s.lower() not in (row.get("session") or "").lower():
                    continue
            candidates.append(row)
        if len(candidates) == 1:
            return str(candidates[0]["id"])
    except Exception:
        pass
    return None


async def backfill_extractions(client, dry_run: bool) -> tuple[int, int]:
    """Backfill scraped_file_id for extractions. Returns (updated, skipped)."""
    r = await asyncio.to_thread(
        lambda: client.table("extractions")
        .select("id, file_name, subject, year, grade, session")
        .is_("scraped_file_id", "null")
        .execute()
    )
    rows = r.data or []
    updated = 0
    for row in rows:
        eid = row["id"]
        file_name = row.get("file_name") or ""
        scraped_id = await _find_scraped_file_by_filename(
            client, file_name, "Question Paper"
        )
        if not scraped_id:
            scraped_id = await _find_scraped_file_by_metadata(
                client,
                row.get("subject"),
                row.get("year"),
                row.get("grade"),
                row.get("session"),
                "Question Paper",
            )
        if scraped_id:
            if not dry_run:
                await asyncio.to_thread(
                    lambda eid=eid, scraped_id=scraped_id: client.table("extractions")
                    .update({"scraped_file_id": scraped_id})
                    .eq("id", eid)
                    .execute()
                )
            updated += 1
            print(f"  [extractions] {eid} -> scraped_file_id={scraped_id} ({file_name[:50]})")
        else:
            print(f"  [extractions] {eid} (no match) {file_name[:50]}")
    return updated, len(rows) - updated


async def backfill_memo_extractions(client, dry_run: bool) -> tuple[int, int]:
    """Backfill scraped_file_id for memo_extractions. Returns (updated, skipped)."""
    r = await asyncio.to_thread(
        lambda: client.table("memo_extractions")
        .select("id, file_name, subject, year, grade, session")
        .is_("scraped_file_id", "null")
        .execute()
    )
    rows = r.data or []
    updated = 0
    for row in rows:
        eid = row["id"]
        file_name = row.get("file_name") or ""
        scraped_id = await _find_scraped_file_by_filename(
            client, file_name, "Memorandum"
        )
        if not scraped_id:
            scraped_id = await _find_scraped_file_by_metadata(
                client,
                row.get("subject"),
                row.get("year"),
                row.get("grade"),
                row.get("session"),
                "Memorandum",
            )
        if scraped_id:
            if not dry_run:
                await asyncio.to_thread(
                    lambda eid=eid, scraped_id=scraped_id: client.table("memo_extractions")
                    .update({"scraped_file_id": scraped_id})
                    .eq("id", eid)
                    .execute()
                )
            updated += 1
            print(f"  [memo_extractions] {eid} -> scraped_file_id={scraped_id} ({file_name[:50]})")
        else:
            print(f"  [memo_extractions] {eid} (no match) {file_name[:50]}")
    return updated, len(rows) - updated


async def main(dry_run: bool) -> None:
    client = get_supabase_client()
    print("=" * 70)
    print("BACKFILL scraped_file_id ON EXTRACTIONS AND MEMO_EXTRACTIONS")
    print(f"Mode: {'DRY RUN (no writes)' if dry_run else 'LIVE'}")
    print("=" * 70)

    print("\nExtractions (Question Papers):")
    ext_updated, ext_skipped = await backfill_extractions(client, dry_run)
    print(f"  -> Updated: {ext_updated}, No match: {ext_skipped}")

    print("\nMemo extractions (Memoranda):")
    memo_updated, memo_skipped = await backfill_memo_extractions(client, dry_run)
    print(f"  -> Updated: {memo_updated}, No match: {memo_skipped}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Extractions updated:     {ext_updated}")
    print(f"  Memo extractions updated: {memo_updated}")
    if dry_run:
        print("  (Dry run: no changes written)")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill scraped_file_id on orphan extractions")
    parser.add_argument("--dry-run", action="store_true", help="Report matches only, do not update")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
