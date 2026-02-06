#!/usr/bin/env python3
"""
Download for each matched exam set: PDFs (QP + Memo), extraction JSON (QP + Memo), and flat table CSV.

Output per set (same stem for all files):
  {stem}-qp.pdf, {stem}-mg.pdf
  {stem}-qp.json, {stem}-memo.json
  {stem}-table.csv

Usage:
  python scripts/download_sets_pdf_json_csv.py
  python scripts/download_sets_pdf_json_csv.py --limit 5
  python scripts/download_sets_pdf_json_csv.py --source-url education.gov.za --status matched

Requires: .env with SUPABASE_* (SUPABASE_SERVICE_ROLE_KEY recommended so all exam_sets/extractions are visible).
For PDFs: FIREBASE_SERVICE_ACCOUNT_JSON or FIREBASE_CREDENTIALS_PATH.
"""

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

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


def _source_url_matches(source_url: str | None, substring: str) -> bool:
    if not substring or not (source_url or "").strip():
        return True
    return substring.lower() in (source_url or "").lower()


def _get_sb():
    """Supabase client; prefer service role for full access."""
    from supabase import create_client
    key = SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY
    if not SUPABASE_URL or not key:
        return None
    return create_client(SUPABASE_URL, key)


def _fetch_exam_sets(
    subject: str | None,
    status: str | None,
    limit: int | None,
    source_url: str | None,
) -> list[dict]:
    """Fetch matched exam_sets with storage info and ensure extractions exist."""
    sb = _get_sb()
    if sb is None:
        return []

    fetch_limit = limit if limit else 500
    q = sb.table("exam_sets").select("*")
    q = q.not_.is_("question_paper_id", "null").not_.is_("memo_id", "null")
    if status:
        q = q.eq("status", status)
    else:
        q = q.eq("status", "matched")
    if subject:
        q = q.ilike("subject", f"%{subject}%")
    q = q.order("created_at", desc=True).limit(fetch_limit)
    try:
        resp = q.execute()
        exam_sets = resp.data or []
    except Exception as e:
        print(f"exam_sets query failed: {e}")
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
        # Require extraction and memo_extraction to exist (for JSON + CSV)
        e_row = sb.table("extractions").select("id").eq("scraped_file_id", qp_id).eq("status", "completed").execute()
        m_row = sb.table("memo_extractions").select("id").eq("scraped_file_id", memo_id).eq("status", "completed").execute()
        if not (e_row.data and m_row.data):
            continue
        results.append({
            **es,
            "qp_bucket": qp_row.get("storage_bucket"),
            "qp_path": qp_row.get("storage_path"),
            "memo_bucket": memo_row.get("storage_bucket"),
            "memo_path": memo_row.get("storage_path"),
        })
    return results


def _to_serializable(obj):
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(type(obj))


def run(
    subject: str | None = None,
    status: str | None = None,
    limit: int | None = None,
    source_url: str | None = None,
    skip_pdf: bool = False,
) -> None:
    sb = _get_sb()
    if sb is None:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY/SUPABASE_KEY in .env")
        return

    pairs = _fetch_exam_sets(subject=subject, status=status, limit=limit, source_url=source_url)
    if not pairs:
        print("No matched exam sets found (with both QP and memo extractions and storage paths).")
        print("Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY) in .env.")
        return

    print(f"Processing {len(pairs)} matched set(s)...\n")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    download_as_bytes = None
    if not skip_pdf:
        try:
            from app.services.firebase_client import download_as_bytes
        except Exception as e:
            print(f"Firebase not available (PDF download disabled): {e}")
            skip_pdf = True

    for es in pairs:
        subj = es.get("subject") or "unknown"
        year = es.get("year") or 0
        paper = es.get("paper_number") or 0
        session = es.get("session") or "unknown"
        short_id = (es.get("id") or "x")[:8]
        stem = build_stem(subj, year, paper, session, short_id)
        exam_set_id = es.get("id")
        qp_sf_id = es.get("question_paper_id")
        memo_sf_id = es.get("memo_id")

        # 1) PDFs
        if not skip_pdf and download_as_bytes:
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
                    print(f"  PDF {out_name} ({len(content)} bytes)")
                except Exception as e:
                    print(f"  PDF FAIL {out_name}: {e}")

        # 2) JSON (QP + memo)
        e_row = sb.table("extractions").select("*").eq("scraped_file_id", qp_sf_id).maybe_single().execute()
        m_row = sb.table("memo_extractions").select("*").eq("scraped_file_id", memo_sf_id).maybe_single().execute()
        if e_row.data:
            qp_path = OUTPUT_DIR / f"{stem}-qp.json"
            with open(qp_path, "w", encoding="utf-8") as f:
                json.dump(e_row.data, f, indent=2, default=_to_serializable, ensure_ascii=False)
            print(f"  JSON {qp_path.name}")
        if m_row.data:
            memo_path = OUTPUT_DIR / f"{stem}-memo.json"
            with open(memo_path, "w", encoding="utf-8") as f:
                json.dump(m_row.data, f, indent=2, default=_to_serializable, ensure_ascii=False)
            print(f"  JSON {memo_path.name}")

        # 3) CSV (matched_paper_questions for this exam_set_id)
        rows = sb.table("matched_paper_questions").select("*").eq("exam_set_id", exam_set_id).order("group_id").order("question_id").execute()
        if rows.data:
            csv_path = OUTPUT_DIR / f"{stem}-table.csv"
            # Flatten for CSV: stringify JSONB columns
            cols = [
                "exam_set_id", "subject", "year", "grade", "session", "syllabus",
                "question_paper_file_name", "memo_file_name",
                "group_id", "group_title", "group_instructions",
                "question_id", "parent_id", "question_text", "marks", "scenario", "context",
                "options", "match_data", "guide_table",
                "memo_question_text", "marker_instruction", "model_answers", "sub_answers",
                "essay_structure", "memo_structured_answer", "memo_marks", "memo_max_marks", "memo_notes", "memo_topic",
            ]
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                for r in rows.data:
                    out = {}
                    for k in cols:
                        v = r.get(k)
                        if v is None:
                            out[k] = ""
                        elif isinstance(v, (dict, list)):
                            out[k] = json.dumps(v, ensure_ascii=False)
                        elif hasattr(v, "isoformat"):
                            out[k] = v.isoformat()
                        else:
                            out[k] = v
                    w.writerow(out)
            print(f"  CSV {csv_path.name} ({len(rows.data)} rows)")
        else:
            print(f"  CSV (no rows in matched_paper_questions for this set)")
        print()

    print(f"Done. Files in: {OUTPUT_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download PDF + JSON + CSV for each matched exam set.",
    )
    parser.add_argument("--source-url", type=str, default=None, help="Filter pairs by source_url containing this")
    parser.add_argument("--subject", type=str, default=None, help="Filter by subject (partial match)")
    parser.add_argument("--status", type=str, default=None, help="Exam set status (default: matched)")
    parser.add_argument("--limit", type=int, default=None, help="Max number of sets to process")
    parser.add_argument("--skip-pdf", action="store_true", help="Skip PDF download (JSON + CSV only)")
    args = parser.parse_args()
    run(
        subject=args.subject,
        status=args.status,
        limit=args.limit,
        source_url=args.source_url,
        skip_pdf=args.skip_pdf,
    )


if __name__ == "__main__":
    main()
