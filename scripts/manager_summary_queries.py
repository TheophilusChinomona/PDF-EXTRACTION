#!/usr/bin/env python3
"""
Print extraction and matched-papers summary for managers.
Run: python scripts/manager_summary_queries.py

Shows table totals and breakdowns side-by-side style for meetings/screenshots.
"""
import sys
from pathlib import Path

# project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.supabase_client import get_supabase_client


def run():
    client = get_supabase_client()

    print("=" * 70)
    print("EXTRACTION & MATCHED PAPERS – SUMMARY")
    print("=" * 70)

    # 1) Table totals
    print("\n--- 1) TABLE TOTALS ---\n")
    for name, table, extra in [
        ("scraped_files", "scraped_files", None),
        ("extractions (QP)", "extractions", None),
        ("memo_extractions", "memo_extractions", None),
        ("exam_sets (all)", "exam_sets", None),
        ("exam_sets (matched = QP+Memo)", "exam_sets", {"status": "matched"}),
    ]:
        q = client.table(table).select("*", count="exact", head=True)
        if extra:
            for k, v in extra.items():
                q = q.eq(k, v)
        r = q.execute()
        count = r.count if hasattr(r, "count") and r.count is not None else len(r.data or [])
        print(f"  {name}: {count}")

    # 2) Extractions by status
    print("\n--- 2) EXTRACTIONS (question papers) by status ---\n")
    r = client.table("extractions").select("status").execute()
    from collections import Counter
    counts = Counter(row.get("status") for row in (r.data or []))
    for status, cnt in counts.most_common():
        print(f"  {status}: {cnt}")

    # 3) Extractions by subject (top 10)
    print("\n--- 3) EXTRACTIONS – top 10 subjects ---\n")
    r = client.table("extractions").select("subject").execute()
    subj = Counter(row.get("subject") for row in (r.data or []) if row.get("subject"))
    for s, c in subj.most_common(10):
        print(f"  {c:4}  {s}")

    # 4) Memo extractions by status
    print("\n--- 4) MEMO_EXTRACTIONS by status ---\n")
    r = client.table("memo_extractions").select("status").execute()
    counts = Counter(row.get("status") for row in (r.data or []))
    for status, cnt in counts.most_common():
        print(f"  {status}: {cnt}")

    # 5) Memo extractions by subject (top 10)
    print("\n--- 5) MEMO_EXTRACTIONS – top 10 subjects ---\n")
    r = client.table("memo_extractions").select("subject").execute()
    subj = Counter(row.get("subject") for row in (r.data or []) if row.get("subject"))
    for s, c in subj.most_common(10):
        print(f"  {c:4}  {s}")

    # 6) Exam sets by status (exact counts)
    print("\n--- 6) EXAM_SETS (matched papers) by status ---\n")
    for status in ("matched", "incomplete", "duplicate_review"):
        r = client.table("exam_sets").select("*", count="exact", head=True).eq("status", status).execute()
        cnt = r.count if getattr(r, "count", None) is not None else 0
        print(f"  {status}: {cnt}")

    # 7) Education.gov.za (if any) – count via chunked in_ to avoid request size limits
    print("\n--- 7) EDUCATION.GOV.ZA (source filter) ---\n")
    sf_ed = client.table("scraped_files").select("id").ilike("source_url", "%education.gov.za%").execute()
    ed_ids = [row["id"] for row in (sf_ed.data or [])]
    if ed_ids:
        chunk = 400
        qp_n = 0
        mm_n = 0
        for i in range(0, len(ed_ids), chunk):
            part = ed_ids[i : i + chunk]
            r = client.table("extractions").select("id", count="exact", head=True).in_("scraped_file_id", part).execute()
            qp_n += r.count if getattr(r, "count", None) is not None else len(r.data or [])
            r = client.table("memo_extractions").select("id", count="exact", head=True).in_("scraped_file_id", part).execute()
            mm_n += r.count if getattr(r, "count", None) is not None else len(r.data or [])
        print(f"  QP extractions (source = education.gov.za):  {qp_n}")
        print(f"  Memo extractions (source = education.gov.za): {mm_n}")
    else:
        print("  No scraped_files with source_url containing education.gov.za")

    print("\n" + "=" * 70)
    print("For full SQL (Supabase): scripts/manager_summary_queries.sql")
    print("Doc: docs/extraction-and-matched-papers-summary.md")
    print("=" * 70)


if __name__ == "__main__":
    run()
