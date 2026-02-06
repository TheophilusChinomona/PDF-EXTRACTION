#!/usr/bin/env python3
"""
Download source PDFs for exported exam-set pairs from Firebase Storage and save
them in output_markdown alongside the extracted .md files (same stem: -qp.pdf / -mg.pdf).

Usage:
    # Use hardcoded English pairs (current behaviour)
    python scripts/download_matched_pairs_pdfs.py

    # Query DB by filters (same logic as export); downloads PDFs for matched pairs
    python scripts/download_matched_pairs_pdfs.py --source-url education.gov.za --status matched
    python scripts/download_matched_pairs_pdfs.py --subject english --status matched --limit 20

Requires: Firebase credentials in .env (FIREBASE_SERVICE_ACCOUNT_JSON or FIREBASE_CREDENTIALS_PATH).
For DB mode: SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY) in .env.
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.services.firebase_client import download_as_bytes

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output_markdown"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _slug(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[/\\]+", "-", text)
    text = re.sub(r"[^a-z0-9\-]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-") or "unknown"


def build_stem(subject: str, year: int, paper_number: int, session: str, short_id: str) -> str:
    return f"{_slug(subject)}-{year}-p{paper_number}-{_slug(str(session))}-{short_id}"


# Pairs we exported (from DB query): short_id, subject, year, paper_number, session, doc_type, storage_bucket, storage_path
FILES = [
    ("2576e630", "English Language", 12, 2, 2021, "Unknown", "qp", "scrapperdb-f854d.firebasestorage.app", "pdfs/Unknown-Grade/Unknown-Subject/OCR-A-Level-English-Language-Paper-2-November-2021-Insert.pdf"),
    ("2576e630", "English Language", 12, 2, 2021, "Unknown", "mg", "scrapperdb-f854d.firebasestorage.app", "pdfs/Unknown-Grade/Unknown-Subject/OCR-A-Level-English-Language-Paper-2-November-2021-Mark-Scheme.pdf"),
    ("a8c8ee34", "English Language And Literature", 12, 2, 2019, "Unknown", "qp", "scrapperdb-f854d.firebasestorage.app", "pdfs/Unknown-Grade/Unknown-Subject/OCR-A-Level-English-Language-and-Literature-Paper-2-QP.pdf"),
    ("a8c8ee34", "English Language And Literature", 12, 2, 2019, "Unknown", "mg", "scrapperdb-f854d.firebasestorage.app", "pdfs/Unknown-Grade/Unknown-Subject/OCR-A-Level-English-Language-and-Literature-Paper-2-MS.pdf"),
    ("bc2c3424", "English Language And Literature", 12, 3, 2019, "Unknown", "qp", "scrapperdb-f854d.firebasestorage.app", "pdfs/Unknown-Grade/Unknown-Subject/OCR-A-Level-English-Language-and-Literature-Paper-3-QP.pdf"),
    ("bc2c3424", "English Language And Literature", 12, 3, 2019, "Unknown", "mg", "scrapperdb-f854d.firebasestorage.app", "pdfs/Unknown-Grade/Unknown-Subject/OCR-A-Level-English-Language-and-Literature-Paper-3-MS.pdf"),
    ("07129f9e", "English Language And Literature", 12, 2, 2022, "Unknown", "qp", "scrapperdb-f854d.firebasestorage.app", "pdfs/Unknown-Grade/Unknown-Subject/OCR-A-Level-English-Language-and-Literature-Paper-2-June-2022-QP.pdf"),
    ("07129f9e", "English Language And Literature", 12, 2, 2022, "Unknown", "mg", "scrapperdb-f854d.firebasestorage.app", "pdfs/Unknown-Grade/Unknown-Subject/OCR-A-Level-English-Language-and-Literature-Paper-2-June-2022-MS.pdf"),
    ("f2fef143", "English Literature", 12, 2, 2019, "Unknown", "qp", "scrapperdb-f854d.firebasestorage.app", "pdfs/Unknown-Grade/Unknown-Subject/OCR-A-Level-English-Literature-Paper-2-QP.pdf"),
    ("f2fef143", "English Literature", 12, 2, 2019, "Unknown", "mg", "scrapperdb-f854d.firebasestorage.app", "pdfs/Unknown-Grade/Unknown-Subject/OCR-A-Level-English-Literature-Paper-2-MS.pdf"),
    ("2c46f2c0", "English Literature", 12, 2, 2022, "Unknown", "qp", "scrapperdb-f854d.firebasestorage.app", "pdfs/Unknown-Grade/Unknown-Subject/OCR-A-Level-English-Literature-Paper-2-June-2022-QP.pdf"),
    ("2c46f2c0", "English Literature", 12, 2, 2022, "Unknown", "mg", "scrapperdb-f854d.firebasestorage.app", "pdfs/Unknown-Grade/Unknown-Subject/OCR-A-Level-English-Literature-Paper-2-June-2022-MS.pdf"),
]


def _source_url_matches(source_url: str | None, substring: str) -> bool:
    """True if source_url contains substring (case-insensitive)."""
    if not substring or not (source_url or "").strip():
        return True
    return substring.lower() in (source_url or "").lower()


def _fetch_exam_sets_for_download(
    subject: str | None,
    status: str | None,
    limit: int | None,
    source_url: str | None,
) -> list[dict]:
    """Fetch exam_sets with storage info for QP and Memo. Filter by source_url when set."""
    from supabase import create_client

    key = SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY
    if not SUPABASE_URL or not key:
        return []
    sb = create_client(SUPABASE_URL, key)

    fetch_limit = limit if limit else 500
    q = sb.table("exam_sets").select("*")
    q = q.not_.is_("question_paper_id", "null").not_.is_("memo_id", "null")
    if status:
        q = q.eq("status", status)
    if subject:
        q = q.ilike("subject", f"%{subject}%")
    q = q.order("created_at", desc=True).limit(fetch_limit)
    try:
        resp = q.execute()
        exam_sets = resp.data or []
    except Exception:
        return []

    results = []
    for es in exam_sets:
        qp_id = es.get("question_paper_id")
        memo_id = es.get("memo_id")
        qp_row = None
        memo_row = None
        if qp_id:
            r = sb.table("scraped_files").select("storage_bucket, storage_path, source_url").eq("id", qp_id).execute()
            if r.data:
                qp_row = r.data[0]
        if memo_id:
            r = sb.table("scraped_files").select("storage_bucket, storage_path, source_url").eq("id", memo_id).execute()
            if r.data:
                memo_row = r.data[0]
        if source_url:
            qp_ok = _source_url_matches(qp_row.get("source_url") if qp_row else None, source_url)
            memo_ok = _source_url_matches(memo_row.get("source_url") if memo_row else None, source_url)
            if not (qp_ok and memo_ok):
                continue
        if not qp_row or not memo_row:
            continue
        results.append({
            **es,
            "qp_bucket": qp_row.get("storage_bucket"),
            "qp_path": qp_row.get("storage_path"),
            "memo_bucket": memo_row.get("storage_bucket"),
            "memo_path": memo_row.get("storage_path"),
            "qp_source_url": qp_row.get("source_url") if qp_row else None,
            "memo_source_url": memo_row.get("source_url") if memo_row else None,
        })
    return results


def _download_from_db(
    subject: str | None,
    status: str | None,
    limit: int | None,
    source_url: str | None,
) -> None:
    pairs = _fetch_exam_sets_for_download(subject=subject, status=status, limit=limit, source_url=source_url)
    if not pairs:
        print("No exam_sets found for the given filters.")
        return
    print(f"Downloading {len(pairs)} matched pairs...")
    OUTPUT_DIR.mkdir(exist_ok=True)
    links_lines = []
    if source_url:
        source_slug = _slug(source_url)
        links_lines.append(f"# Source links ({source_url})")
        links_lines.append("")
    for es in pairs:
        subj = es.get("subject") or "unknown"
        year = es.get("year") or 0
        paper = es.get("paper_number") or 0
        session = es.get("session") or "unknown"
        short_id = (es.get("id") or "x")[:8]
        stem = build_stem(subj, year, paper, session, short_id)
        for label, bucket, path, suffix in (
            ("qp", es.get("qp_bucket"), es.get("qp_path"), "qp"),
            ("mg", es.get("memo_bucket"), es.get("memo_path"), "mg"),
        ):
            if not bucket or not path:
                continue
            out_name = f"{stem}-{suffix}.pdf"
            out_path = OUTPUT_DIR / out_name
            gs_url = f"gs://{bucket}/{path}"
            try:
                content = download_as_bytes(gs_url)
                out_path.write_bytes(content)
                print(f"  OK {out_name} ({len(content)} bytes)")
            except Exception as e:
                print(f"  FAIL {out_name}: {e}")
        if source_url and links_lines is not None:
            qp_url = es.get("qp_source_url")
            memo_url = es.get("memo_source_url")
            if qp_url or memo_url:
                links_lines.append(f"## {stem}")
                if qp_url:
                    links_lines.append(f"- QP: {qp_url}")
                if memo_url:
                    links_lines.append(f"- Memo: {memo_url}")
                links_lines.append("")
    if links_lines:
        links_name = f"SOURCE-LINKS-{source_slug}.md"
        (OUTPUT_DIR / links_name).write_text("\n".join(links_lines), encoding="utf-8")
        print(f"\nSource links written to: {OUTPUT_DIR / links_name}")
    print(f"\nDone. PDFs saved to: {OUTPUT_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download source PDFs for exam-set pairs from Firebase Storage.",
    )
    parser.add_argument("--source-url", type=str, default=None, help="Filter to pairs where both QP and Memo have source_url containing this (e.g. education.gov.za). When set, query DB and write SOURCE-LINKS-<slug>.md")
    parser.add_argument("--subject", type=str, default=None, help="Filter by subject (partial match). Use with DB mode.")
    parser.add_argument("--status", type=str, default=None, help="Filter by exam_set status (e.g. matched). Use with DB mode.")
    parser.add_argument("--limit", type=int, default=None, help="Max pairs to download when using DB mode.")
    args = parser.parse_args()

    use_db = any([args.source_url, args.subject, args.status, args.limit is not None])
    if use_db:
        _download_from_db(
            subject=args.subject,
            status=args.status,
            limit=args.limit,
            source_url=args.source_url,
        )
        return

    OUTPUT_DIR.mkdir(exist_ok=True)
    for short_id, subject, grade, paper_number, year, session, doc_type, bucket, path in FILES:
        stem = build_stem(subject, year, paper_number, session, short_id)
        suffix = "qp" if doc_type == "qp" else "mg"
        out_name = f"{stem}-{suffix}.pdf"
        out_path = OUTPUT_DIR / out_name
        gs_url = f"gs://{bucket}/{path}"
        try:
            content = download_as_bytes(gs_url)
            out_path.write_bytes(content)
            print(f"  OK {out_name} ({len(content)} bytes)")
        except Exception as e:
            print(f"  FAIL {out_name}: {e}")
    print(f"\nDone. PDFs saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
