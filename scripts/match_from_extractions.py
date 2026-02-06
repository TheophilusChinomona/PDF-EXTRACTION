#!/usr/bin/env python3
"""
Create/update exam_sets from existing extractions and memo_extractions (e.g. education.gov.za).
Uses extraction metadata (subject, grade, year, session) to match QPs and Memos into pairs.
Does not require validation_results.

Usage:
    # Match all education.gov.za extractions/memos currently in DB
    python scripts/match_from_extractions.py --source-url education.gov.za

    # Dry run
    python scripts/match_from_extractions.py --source-url education.gov.za --dry-run

Requires: SUPABASE_SERVICE_ROLE_KEY in .env
"""

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

if os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
    os.environ["SUPABASE_KEY"] = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

from supabase import create_client, Client

from app.config import get_settings
from app.services.exam_matcher import match_document_to_exam_set
from app.utils.normalizers import (
    normalize_grade,
    normalize_paper_number,
    normalize_session,
    normalize_subject,
)

SOURCE_URL_SUBSTRING = "education.gov.za"


def _get_client() -> Client:
    settings = get_settings()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or settings.supabase_key
    return create_client(settings.supabase_url, key)


def _paper_number_from_subject(subject: str) -> int:
    """Try to get paper number from subject string (e.g. 'P2', 'V1', 'Paper 2')."""
    if not subject:
        return 1
    s = (subject or "").strip()
    # Match P1, P2, V1, V2, Paper 1, etc.
    m = re.search(r"\b[PV](\d+)\b", s, re.I) or re.search(r"paper\s*(\d+)", s, re.I)
    return int(m.group(1)) if m else 1


def _extraction_to_metadata(row: dict, is_memo: bool) -> dict:
    subject = (row.get("subject") or "").strip() or "Unknown"
    grade_raw = row.get("grade")
    # Treat "Unknown" or unparseable grade as 12 so matching can proceed
    grade = grade_raw
    if grade is None or (isinstance(grade, str) and grade.strip().lower() in ("unknown", "")):
        grade = 12
    year = row.get("year")
    session = (row.get("session") or "").strip() or "Unknown"
    syllabus = (row.get("syllabus") or "").strip() or None
    paper_number = _paper_number_from_subject(subject)
    paper_type = "memo" if is_memo else "question_paper"
    return {
        "subject": subject,
        "grade": grade,
        "year": year,
        "session": session,
        "syllabus": syllabus,
        "paper_number": paper_number,
        "paper_type": paper_type,
    }


async def run(source_url: str, dry_run: bool) -> None:
    client = _get_client()

    # 1) Get scraped_file ids for this source
    r = (
        client.table("scraped_files")
        .select("id")
        .ilike("source_url", f"%{source_url}%")
        .execute()
    )
    sf_ids = [str(row["id"]) for row in (r.data or [])]
    if not sf_ids:
        print(f"No scraped_files found for source_url containing '{source_url}'.")
        return
    print(f"Found {len(sf_ids)} scraped_files with source_url containing '{source_url}'.")

    # 2) Get extractions (QP) and memo_extractions for those scraped_file_ids
    # Paginate if many
    ext_rows: list[dict] = []
    for i in range(0, len(sf_ids), 100):
        chunk = sf_ids[i : i + 100]
        r = client.table("extractions").select("id, scraped_file_id, subject, grade, year, session, syllabus").in_("scraped_file_id", chunk).execute()
        ext_rows.extend(r.data or [])

    memo_rows: list[dict] = []
    for i in range(0, len(sf_ids), 100):
        chunk = sf_ids[i : i + 100]
        r = client.table("memo_extractions").select("id, scraped_file_id, subject, grade, year, session").in_("scraped_file_id", chunk).execute()
        memo_rows.extend(r.data or [])

    print(f"  Extractions (QP): {len(ext_rows)}, Memo extractions: {len(memo_rows)}.")
    if not ext_rows and not memo_rows:
        print("No extractions or memo_extractions to match.")
        return

    if dry_run:
        print("[dry-run] Would run matching for these rows (creates/updates exam_sets). Run without --dry-run to apply.")
        return

    matched_qp = 0
    matched_memo = 0
    errors = 0

    for row in ext_rows:
        sid = row.get("scraped_file_id")
        if not sid:
            continue
        metadata = _extraction_to_metadata(row, is_memo=False)
        subject = normalize_subject(metadata["subject"])
        grade = normalize_grade(metadata["grade"])
        session = normalize_session(metadata["session"])
        if not subject or grade is None or not session:
            errors += 1
            print(f"  Skip QP {sid}: subject={subject!r} grade={grade} session={session!r}")
            continue
        try:
            exam_set_id = await match_document_to_exam_set(client, UUID(sid), metadata)
            if exam_set_id:
                matched_qp += 1
        except Exception as e:
            errors += 1
            print(f"  Error QP {sid}: {e}")

    for row in memo_rows:
        sid = row.get("scraped_file_id")
        if not sid:
            continue
        metadata = _extraction_to_metadata(row, is_memo=True)
        metadata.setdefault("syllabus", None)
        subject = normalize_subject(metadata["subject"])
        grade = normalize_grade(metadata["grade"])
        session = normalize_session(metadata["session"])
        if not subject or grade is None or not session:
            errors += 1
            print(f"  Skip memo {sid}: subject={subject!r} grade={grade} session={session!r}")
            continue
        try:
            exam_set_id = await match_document_to_exam_set(client, UUID(sid), metadata)
            if exam_set_id:
                matched_memo += 1
        except Exception as e:
            errors += 1
            print(f"  Error Memo {sid}: {e}")

    print(f"Done. Matched as QP: {matched_qp}, as Memo: {matched_memo}, errors: {errors}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Match existing extractions/memo_extractions into exam_sets by metadata.")
    parser.add_argument("--source-url", type=str, default=SOURCE_URL_SUBSTRING, help=f"Filter scraped_files by source_url containing this (default: {SOURCE_URL_SUBSTRING})")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")
    args = parser.parse_args()
    asyncio.run(run(source_url=args.source_url, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
