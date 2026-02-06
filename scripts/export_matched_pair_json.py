#!/usr/bin/env python3
"""
Export full extraction JSON for a matched QP+Memo pair so you can open and inspect it.

Usage:
  python scripts/export_matched_pair_json.py <exam_set_id>     # export this pair to JSON files
  python scripts/export_matched_pair_json.py --qp <extraction_id>  # export this QP (+ memo if linked)
  python scripts/export_matched_pair_json.py --list [N]        # list N matched pairs (default 20)

Output: writes to output_markdown/ (or current dir) as:
  <slug>_qp.json   - full extraction row (includes groups, tables, etc.)
  <slug>_memo.json - full memo_extraction row (includes sections, etc.)
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.supabase_client import get_supabase_client


def slug(s: str) -> str:
    """Safe filename slug."""
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"[-\s]+", "-", s).strip("-")[:80] or "export"


def list_matched_pairs(client, limit: int = 20):
    """List matched pairs so user can copy an exam_set_id."""
    r = client.table("exam_sets").select(
        "id, status, matched_at, question_paper_id, memo_id"
    ).eq("status", "matched").order("matched_at", desc=True).limit(limit).execute()
    if not r.data:
        print("No matched exam_sets found.")
        return
    ids_qp = [row["question_paper_id"] for row in r.data]
    ids_memo = [row["memo_id"] for row in r.data]
    # Fetch file names
    qp_rows = client.table("extractions").select("scraped_file_id, file_name").in_("scraped_file_id", ids_qp).execute()
    memo_rows = client.table("memo_extractions").select("scraped_file_id, file_name").in_("scraped_file_id", ids_memo).execute()
    qp_by_sf = {row["scraped_file_id"]: row["file_name"] for row in (qp_rows.data or [])}
    memo_by_sf = {row["scraped_file_id"]: row["file_name"] for row in (memo_rows.data or [])}
    print(f"Matched pairs (use exam_set_id with this script to export JSON):\n")
    for row in r.data:
        es_id = row["id"]
        qp_name = qp_by_sf.get(row["question_paper_id"]) or "(no extraction)"
        memo_name = memo_by_sf.get(row["memo_id"]) or "(no memo extraction)"
        print(f"  {es_id}")
        print(f"    QP:   {qp_name}")
        print(f"    Memo: {memo_name}\n")


def export_by_exam_set_id(client, exam_set_id: str, out_dir: Path):
    """Fetch full extraction + memo_extraction for this exam_set and write JSON files."""
    es = client.table("exam_sets").select("id, question_paper_id, memo_id").eq("id", exam_set_id).maybe_single().execute()
    if not es.data:
        print(f"No exam_set found for id: {exam_set_id}")
        return
    qp_sf_id = es.data.get("question_paper_id")
    memo_sf_id = es.data.get("memo_id")
    if not qp_sf_id or not memo_sf_id:
        print("This exam_set has no QP or Memo linked.")
        return
    e_row = client.table("extractions").select("*").eq("scraped_file_id", qp_sf_id).maybe_single().execute()
    m_row = client.table("memo_extractions").select("*").eq("scraped_file_id", memo_sf_id).maybe_single().execute()
    if not e_row.data:
        print(f"No extraction found for question_paper_id {qp_sf_id}")
        return
    if not m_row.data:
        print(f"No memo_extraction found for memo_id {memo_sf_id}")
        return
    qp_name = e_row.data.get("file_name") or "qp"
    memo_name = m_row.data.get("file_name") or "memo"
    base = slug(Path(qp_name).stem)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Serialize for JSON (convert any non-serializable)
    def to_serializable(obj):
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        raise TypeError(type(obj))
    qp_path = out_dir / f"{base}_qp.json"
    memo_path = out_dir / f"{base}_memo.json"
    with open(qp_path, "w", encoding="utf-8") as f:
        json.dump(e_row.data, f, indent=2, default=to_serializable, ensure_ascii=False)
    with open(memo_path, "w", encoding="utf-8") as f:
        json.dump(m_row.data, f, indent=2, default=to_serializable, ensure_ascii=False)
    print(f"Wrote:\n  {qp_path}\n  {memo_path}")
    print(f"Open in your editor to view the extraction JSON (groups, tables, memo sections).")


def export_by_qp_extraction_id(client, extraction_id: str, out_dir: Path):
    """Fetch this extraction's full row and optional linked memo; write JSON files."""
    e_row = client.table("extractions").select("*").eq("id", extraction_id).maybe_single().execute()
    if not e_row.data:
        print(f"No extraction found for id: {extraction_id}")
        return
    qp_name = e_row.data.get("file_name") or "qp"
    base = slug(Path(qp_name).stem)
    out_dir.mkdir(parents=True, exist_ok=True)

    def to_serializable(obj):
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        raise TypeError(type(obj))

    qp_path = out_dir / f"{base}_qp.json"
    with open(qp_path, "w", encoding="utf-8") as f:
        json.dump(e_row.data, f, indent=2, default=to_serializable, ensure_ascii=False)
    print(f"Wrote: {qp_path}")

    # Find exam_set that has this QP and get memo if any
    sf_id = e_row.data.get("scraped_file_id")
    if sf_id:
        es = client.table("exam_sets").select("memo_id").eq("question_paper_id", sf_id).limit(5).execute()
        memo_sf_id = None
        for row in (es.data or []):
            if row.get("memo_id"):
                memo_sf_id = row["memo_id"]
                break
        if memo_sf_id:
            m_row = client.table("memo_extractions").select("*").eq("scraped_file_id", memo_sf_id).maybe_single().execute()
            if m_row.data:
                memo_path = out_dir / f"{base}_memo.json"
                with open(memo_path, "w", encoding="utf-8") as f:
                    json.dump(m_row.data, f, indent=2, default=to_serializable, ensure_ascii=False)
                print(f"Wrote: {memo_path}")
    print("Open the file(s) in your editor to view the extraction JSON.")


def main():
    parser = argparse.ArgumentParser(description="Export matched pair extraction JSON to files.")
    parser.add_argument("exam_set_id", nargs="?", help="Exam set UUID to export")
    parser.add_argument("--qp", metavar="EXTRACTION_ID", help="Export by QP extraction id instead")
    parser.add_argument("--list", nargs="?", metavar="N", const=20, type=int, help="List N matched pairs (default 20)")
    parser.add_argument("--out-dir", type=Path, default=Path("output_markdown"), help="Output directory for JSON files")
    args = parser.parse_args()

    client = get_supabase_client()

    if args.list is not None:
        list_matched_pairs(client, limit=args.list)
        return
    if args.qp:
        export_by_qp_extraction_id(client, args.qp, args.out_dir)
        return
    if args.exam_set_id:
        export_by_exam_set_id(client, args.exam_set_id, args.out_dir)
        return
    print("Use: --list [N]  to list pairs, or <exam_set_id> / --qp <extraction_id> to export.")
    parser.print_help()


if __name__ == "__main__":
    main()
