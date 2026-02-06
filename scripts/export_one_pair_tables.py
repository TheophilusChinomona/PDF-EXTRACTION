#!/usr/bin/env python3
"""
Export ONE question paper + ONE memo as flattened tables (extracted JSON as rows).

Usage:
  python scripts/export_one_pair_tables.py <exam_set_id>   # this pair as tables
  python scripts/export_one_pair_tables.py                 # first matched pair
  python scripts/export_one_pair_tables.py --list 5        # list 5 pairs, then run without args for first

Output: prints two markdown tables to stdout and writes to output_markdown/<slug>_tables.md
  - Table 1: Questions (from extraction.groups) — group_id, group_title, question_id, text, marks
  - Table 2: Memo answers (from memo_extractions.sections) — section_id, question_id, type, text, answer_summary, marks
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


def _summarize_answer(val) -> str:
    """Short string for model_answers/answers/essay_structure in a table cell."""
    if val is None:
        return ""
    if isinstance(val, list):
        if not val:
            return ""
        if len(val) <= 2 and all(isinstance(x, str) for x in val):
            return " | ".join(val[:2])
        return f"{len(val)} items"
    if isinstance(val, dict):
        keys = list(val.keys())[:3]
        return ", ".join(keys) + ("..." if len(val) > 3 else "")
    return str(val)[:120]


def flatten_qp_groups(extraction_row: dict) -> list[dict]:
    """Flatten extraction.groups into one row per question."""
    groups = extraction_row.get("groups") or []
    if isinstance(groups, str):
        groups = json.loads(groups) if groups else []
    rows = []
    for g in groups:
        group_id = g.get("group_id") or ""
        title = g.get("title") or ""
        instructions = (g.get("instructions") or "")[:80]
        for q in g.get("questions") or []:
            text = (q.get("text") or "")[:200]
            if len((q.get("text") or "")) > 200:
                text += "..."
            rows.append({
                "group_id": group_id,
                "group_title": title,
                "instructions": instructions,
                "question_id": q.get("id") or "",
                "question_text": text,
                "marks": q.get("marks"),
                "parent_id": q.get("parent_id") or "",
            })
    return rows


def flatten_memo_sections(memo_row: dict) -> list[dict]:
    """Flatten memo_extractions.sections into one row per memo question."""
    sections_raw = memo_row.get("sections") or []
    if isinstance(sections_raw, str):
        sections_raw = json.loads(sections_raw) if sections_raw else []
    rows = []
    for sec in sections_raw:
        section_id = sec.get("section_id") or ""
        for q in sec.get("questions") or []:
            qid = q.get("id") or ""
            qtype = q.get("type") or ""
            text = (q.get("text") or "")[:150]
            if len((q.get("text") or "")) > 150:
                text += "..."
            model = _summarize_answer(q.get("model_answers"))
            answers = _summarize_answer(q.get("answers"))
            structured = _summarize_answer(q.get("structured_answer"))
            essay = ""
            if q.get("essay_structure"):
                es = q["essay_structure"]
                intro = len(es.get("introduction") or [])
                body = len(es.get("body_sections") or [])
                conc = len(es.get("conclusion") or [])
                essay = f"intro:{intro} body:{body} conc:{conc}"
            answer_cell = model or answers or structured or essay or "—"
            rows.append({
                "section_id": section_id,
                "question_id": qid,
                "type": qtype,
                "text": text,
                "answer_summary": answer_cell,
                "marks": q.get("marks"),
                "marker_instruction": (q.get("marker_instruction") or "")[:80],
            })
    return rows


def rows_to_markdown_table(rows: list[dict], headers: list[str]) -> str:
    """Render list of dicts as a markdown table."""
    if not rows:
        return "(no rows)"
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for r in rows:
        cells = [str(r.get(h, "")) for h in headers]
        # Escape pipe in cell so it doesn't break table
        cells = [c.replace("|", "\\|") for c in cells]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def fetch_one_pair(client, exam_set_id: str | None):
    """Get one extraction row and one memo_extraction row for a matched pair."""
    if exam_set_id:
        es = client.table("exam_sets").select("id, question_paper_id, memo_id").eq("id", exam_set_id).eq("status", "matched").maybe_single().execute()
    else:
        es = client.table("exam_sets").select("id, question_paper_id, memo_id").eq("status", "matched").order("matched_at", desc=True).limit(1).execute()
        if es.data and len(es.data) > 0:
            es.data = es.data[0]
    if not es.data:
        return None, None, None
    row = es.data if isinstance(es.data, dict) else (es.data[0] if es.data else None)
    qp_sf_id = row.get("question_paper_id")
    memo_sf_id = row.get("memo_id")
    if not qp_sf_id or not memo_sf_id:
        return None, None, row.get("id")
    e_res = client.table("extractions").select("*").eq("scraped_file_id", qp_sf_id).maybe_single().execute()
    m_res = client.table("memo_extractions").select("*").eq("scraped_file_id", memo_sf_id).maybe_single().execute()
    e_row = e_res.data if e_res and hasattr(e_res, "data") else None
    m_row = m_res.data if m_res and hasattr(m_res, "data") else None
    if not e_row or not m_row:
        return None, None, row.get("id")
    return e_row, m_row, row.get("id")


def list_pairs(client, limit: int = 10):
    """List matched pairs so user can pick exam_set_id."""
    r = client.table("exam_sets").select("id, question_paper_id, memo_id, matched_at").eq("status", "matched").order("matched_at", desc=True).limit(limit).execute()
    if not r.data:
        print("No matched exam_sets.")
        return
    ids_qp = [row["question_paper_id"] for row in r.data]
    qp_rows = client.table("extractions").select("scraped_file_id, file_name").in_("scraped_file_id", ids_qp).execute()
    qp_by_sf = {row["scraped_file_id"]: row["file_name"] for row in (qp_rows.data or [])}
    print("Matched pairs (use exam_set_id with this script):\n")
    for row in r.data:
        print(f"  {row['id']}")
        print(f"    QP:   {qp_by_sf.get(row['question_paper_id']) or '(no extraction)'}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Export one QP + one memo as tables (extracted JSON flattened).")
    parser.add_argument("exam_set_id", nargs="?", help="Exam set UUID (optional; uses first matched if omitted)")
    parser.add_argument("--list", nargs="?", metavar="N", const=10, type=int, help="List N matched pairs then exit")
    parser.add_argument("--out-dir", type=Path, default=Path("output_markdown"), help="Output directory for .md file")
    parser.add_argument("--no-file", action="store_true", help="Only print tables, do not write file")
    args = parser.parse_args()

    client = get_supabase_client()

    if args.list is not None:
        list_pairs(client, limit=args.list)
        return

    e_row, m_row, es_id = fetch_one_pair(client, args.exam_set_id)
    if not e_row or not m_row:
        print("No matched pair found. Use --list to see available exam_set_id values.")
        if args.exam_set_id:
            print(f"Requested exam_set_id: {args.exam_set_id}")
        sys.exit(1)

    qp_rows = flatten_qp_groups(e_row)
    memo_rows = flatten_memo_sections(m_row)

    qp_headers = ["group_id", "group_title", "question_id", "question_text", "marks"]
    memo_headers = ["section_id", "question_id", "type", "text", "answer_summary", "marks"]

    qp_name = e_row.get("file_name") or "qp"
    base = slug(Path(qp_name).stem)
    title = f"# One pair: QP + Memo (exam_set_id: {es_id})\n"
    qp_table = "## Questions (from extraction.groups)\n\n" + rows_to_markdown_table(qp_rows, qp_headers)
    memo_table = "\n\n## Memo answers (from memo_extractions.sections)\n\n" + rows_to_markdown_table(memo_rows, memo_headers)
    body = title + qp_table + memo_table

    print(body)

    if not args.no_file:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        out_path = args.out_dir / f"{base}_tables.md"
        out_path.write_text(body, encoding="utf-8")
        print(f"\nWrote: {out_path}")


if __name__ == "__main__":
    main()
