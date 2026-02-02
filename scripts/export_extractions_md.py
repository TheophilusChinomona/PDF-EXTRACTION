"""
Export extraction results to Markdown files with canonical naming.

Fetches extraction data from the API (extractions table) and directly from
Supabase (memo_extractions table), then converts to human-readable Markdown.

Filename convention matches the repo standard:
  {short_id}-{subject-slug}-gr{grade}-{session-slug}-{year}-{qp|mg}.md

Usage:
    python scripts/export_extractions_md.py
"""

import json
import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_BASE = os.getenv("TEST_API_BASE", "http://localhost:8000")
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output_markdown"

EXTRACTION_IDS = [
    "072b402f-5929-492a-919e-1e5daec62938",
    "b6f4fbb1-e35d-4620-9028-012e23a4eb13",
    "8cac1f77-f9bc-4a3f-a44b-19ff63562307",
    "4f401d40-2c1f-4cf2-b417-c69345ad83de",
    "c81ed85e-c1aa-479b-9d6e-8d010da1a111",
    "ae89a23c-2ce9-491a-bcfb-683a7573ebde",
    "cb29880c-cdef-40d3-aa4a-1c20b19b64b3",
    "ea53b066-15f1-4edf-a2e9-6b9249b524ab",
    "45a9ace8-c375-44bc-b858-89c6d3534538",
    "6f8fb315-6e2b-4a76-9c9f-329a4f2bd4bc",
]


# ---------------------------------------------------------------------------
# Canonical filename builder (mirrors FullExamPaper.build_canonical_filename)
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    """Normalise text into a URL/filename-safe slug."""
    text = text.lower()
    text = re.sub(r'[/\\]+', '-', text)
    text = re.sub(r'[^a-z0-9\-]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


def build_canonical_name(eid: str, subject: str, grade: str,
                         session: str, year: str | int,
                         suffix: str) -> str:
    """Build canonical filename stem (no extension).

    Format: {short_id}-{subject}-gr{grade}-{session}-{year}-{suffix}
    """
    short_id = eid.replace("-", "")[:12]
    parts = [
        short_id,
        _slug(subject or "unknown"),
        f"gr{_slug(str(grade or '0'))}",
        _slug(session or "unknown"),
        str(year or "0"),
        suffix,
    ]
    return "-".join(parts)


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_from_api(eid: str) -> dict | None:
    """Try GET /api/extractions/{id} (question paper extractions)."""
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(f"{API_BASE}/api/extractions/{eid}")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None


def fetch_from_supabase_memo(supabase, eid: str) -> dict | None:
    """Fetch from memo_extractions table directly."""
    try:
        r = supabase.table("memo_extractions").select("*").eq("id", eid).execute()
        if r.data:
            return r.data[0]
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------

def get_qp_meta(data: dict) -> dict:
    """Extract metadata dict from a question paper extraction record."""
    return {
        "subject": data.get("subject") or "",
        "grade": str(data.get("grade") or ""),
        "year": data.get("year") or "",
        "session": data.get("session") or "",
        "syllabus": data.get("syllabus") or "",
        "language": data.get("language") or "",
        "total_marks": data.get("total_marks") or "",
    }


def get_memo_meta(data: dict) -> dict:
    """Extract metadata dict from a memo extraction record.

    memo_extractions stores metadata as top-level columns, same as extractions.
    """
    return {
        "subject": data.get("subject") or "",
        "grade": str(data.get("grade") or ""),
        "year": data.get("year") or "",
        "session": data.get("session") or "",
        "syllabus": data.get("syllabus") or "",
        "language": data.get("language") or "",
        "total_marks": data.get("total_marks") or "",
    }


# ---------------------------------------------------------------------------
# Markdown conversion for Question Papers (extractions table)
# ---------------------------------------------------------------------------

def qp_to_markdown(data: dict, meta: dict, eid: str) -> str:
    """Convert a question paper extraction to Markdown."""
    lines: list[str] = []

    subject = meta["subject"] or "Unknown Subject"
    scraped_file_id = data.get("scraped_file_id")
    name_id = scraped_file_id if scraped_file_id else eid
    canonical = build_canonical_name(
        name_id, meta["subject"], meta["grade"],
        meta["session"], meta["year"], "qp"
    )

    lines.append(f"# {subject}")
    lines.append("")
    lines.append(f"**Document ID:** `{canonical}`")
    lines.append("")

    meta_parts = []
    if meta["grade"]:
        meta_parts.append(f"**Grade:** {meta['grade']}")
    if meta["year"]:
        meta_parts.append(f"**Year:** {meta['year']}")
    if meta["session"]:
        meta_parts.append(f"**Session:** {meta['session']}")
    if meta["syllabus"]:
        meta_parts.append(f"**Syllabus:** {meta['syllabus']}")
    if meta["language"]:
        meta_parts.append(f"**Language:** {meta['language']}")
    if meta["total_marks"]:
        meta_parts.append(f"**Total Marks:** {meta['total_marks']}")
    if meta_parts:
        lines.append(" | ".join(meta_parts))
        lines.append("")

    lines.append("---")
    lines.append("")

    # Groups / Sections
    groups = data.get("groups") or []
    for group in groups:
        title = group.get("title") or ""
        group_id = group.get("group_id") or ""
        instructions = group.get("instructions") or ""

        heading = f"{group_id}: {title}" if title else group_id
        lines.append(f"## {heading}")
        lines.append("")
        if instructions:
            lines.append(f"*{instructions}*")
            lines.append("")

        questions = group.get("questions") or []
        for q in questions:
            qid = q.get("id", "?")
            text = q.get("text") or ""
            marks = q.get("marks")
            context = q.get("context")
            scenario = q.get("scenario")
            options = q.get("options")
            match_data = q.get("match_data")
            guide_table = q.get("guide_table")

            marks_str = f" [{marks} marks]" if marks else ""
            lines.append(f"### Question {qid}{marks_str}")
            lines.append("")

            if scenario:
                lines.append("<details><summary>Scenario / Source Text</summary>")
                lines.append("")
                lines.append(scenario)
                lines.append("")
                lines.append("</details>")
                lines.append("")

            if context:
                lines.append(f"> {context}")
                lines.append("")

            if text:
                lines.append(text)
                lines.append("")

            if options:
                if isinstance(options, list):
                    for opt in options:
                        if isinstance(opt, dict):
                            label = opt.get("label", "")
                            value = opt.get("value", opt.get("text", ""))
                            lines.append(f"- **{label}** {value}")
                        else:
                            lines.append(f"- {opt}")
                    lines.append("")

            if match_data:
                if isinstance(match_data, dict):
                    col_a = match_data.get("column_a") or match_data.get("columnA") or []
                    col_b = match_data.get("column_b") or match_data.get("columnB") or []
                    lines.append("| Column A | Column B |")
                    lines.append("|----------|----------|")
                    max_len = max(len(col_a), len(col_b))
                    for i in range(max_len):
                        a = col_a[i] if i < len(col_a) else ""
                        b = col_b[i] if i < len(col_b) else ""
                        a_str = a if isinstance(a, str) else json.dumps(a)
                        b_str = b if isinstance(b, str) else json.dumps(b)
                        lines.append(f"| {a_str} | {b_str} |")
                    lines.append("")

            if guide_table:
                if isinstance(guide_table, list) and guide_table:
                    if isinstance(guide_table[0], dict):
                        headers = list(guide_table[0].keys())
                        lines.append("| " + " | ".join(headers) + " |")
                        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                        for row in guide_table:
                            vals = [str(row.get(h, "")) for h in headers]
                            lines.append("| " + " | ".join(vals) + " |")
                        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown conversion for Memos (memo_extractions table)
# ---------------------------------------------------------------------------

def memo_to_markdown(data: dict, meta: dict, eid: str) -> str:
    """Convert a memo extraction to Markdown."""
    lines: list[str] = []

    # Parse sections - may be stored as JSON string
    sections_raw = data.get("sections")
    if isinstance(sections_raw, str):
        sections_raw = json.loads(sections_raw)
    sections = sections_raw or []

    subject = meta["subject"] or "Unknown Subject"
    scraped_file_id = data.get("scraped_file_id")
    name_id = scraped_file_id if scraped_file_id else eid
    canonical = build_canonical_name(
        name_id, meta["subject"], meta["grade"],
        meta["session"], meta["year"], "mg"
    )

    lines.append(f"# {subject} — Marking Guideline")
    lines.append("")
    lines.append(f"**Document ID:** `{canonical}`")
    lines.append("")

    meta_parts = []
    if meta["grade"]:
        meta_parts.append(f"**Grade:** {meta['grade']}")
    if meta["year"]:
        meta_parts.append(f"**Year:** {meta['year']}")
    if meta["session"]:
        meta_parts.append(f"**Session:** {meta['session']}")
    if meta["syllabus"]:
        meta_parts.append(f"**Syllabus:** {meta['syllabus']}")
    if meta["language"]:
        meta_parts.append(f"**Language:** {meta['language']}")
    if meta["total_marks"]:
        meta_parts.append(f"**Total Marks:** {meta['total_marks']}")
    if meta_parts:
        lines.append(" | ".join(meta_parts))
        lines.append("")
    lines.append("---")
    lines.append("")

    for section in sections:
        section_id = section.get("section_id", "")
        lines.append(f"## {section_id}")
        lines.append("")

        questions = section.get("questions") or []
        for q in questions:
            qid = q.get("id", "?")
            qtype = q.get("type") or ""
            text = q.get("text") or ""
            marks = q.get("marks")
            max_marks = q.get("max_marks")
            marker_instruction = q.get("marker_instruction")
            notes = q.get("notes")
            topic = q.get("topic")

            marks_str = ""
            if marks:
                marks_str = f" [{marks} marks]"
            if max_marks and max_marks != marks:
                marks_str = f" [{marks}/{max_marks} marks]"

            type_str = f" ({qtype})" if qtype else ""
            lines.append(f"### Question {qid}{marks_str}{type_str}")
            lines.append("")

            if topic:
                lines.append(f"**Topic:** {topic}")
                lines.append("")

            if text:
                lines.append(f"**{text}**")
                lines.append("")

            if marker_instruction:
                lines.append(f"> **Marker instruction:** {marker_instruction}")
                lines.append("")

            # Model answers
            model_answers = q.get("model_answers")
            if model_answers:
                if isinstance(model_answers, list):
                    for ans in model_answers:
                        lines.append(f"- {ans}")
                elif isinstance(model_answers, dict):
                    for key, vals in model_answers.items():
                        lines.append(f"**{key}:**")
                        if isinstance(vals, list):
                            for v in vals:
                                lines.append(f"- {v}")
                        else:
                            lines.append(f"- {vals}")
                lines.append("")

            # Sub-question answers
            answers = q.get("answers")
            if answers:
                for ans in answers:
                    if isinstance(ans, dict):
                        sub_id = ans.get("sub_id", "")
                        value = ans.get("value", "")
                        lines.append(f"- **{sub_id}:** {value}")
                    else:
                        lines.append(f"- {ans}")
                lines.append("")

            # Structured answers
            structured = q.get("structured_answer")
            if structured:
                for item in structured:
                    if isinstance(item, dict):
                        parts = [f"**{k}:** {v}" for k, v in item.items()]
                        lines.append("- " + " | ".join(parts))
                    else:
                        lines.append(f"- {item}")
                lines.append("")

            # Essay structure
            essay = q.get("essay_structure")
            if essay:
                intro = essay.get("introduction") or []
                body = essay.get("body_sections") or []
                conclusion = essay.get("conclusion") or []

                if intro:
                    lines.append("**Introduction:**")
                    for pt in intro:
                        lines.append(f"- {pt}")
                    lines.append("")

                if body:
                    lines.append("**Body:**")
                    for sec in body:
                        sub_topic = sec.get("sub_topic", "")
                        if sub_topic:
                            lines.append(f"\n*{sub_topic}*")
                        for key in ["points", "positives", "negatives", "rights"]:
                            pts = sec.get(key)
                            if pts:
                                if key != "points":
                                    lines.append(f"  *{key.title()}:*")
                                for pt in pts:
                                    lines.append(f"  - {pt}")
                    lines.append("")

                if conclusion:
                    lines.append("**Conclusion:**")
                    for pt in conclusion:
                        lines.append(f"- {pt}")
                    lines.append("")

            if notes:
                lines.append(f"*Note: {notes}*")
                lines.append("")

    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    print(f"Exporting {len(EXTRACTION_IDS)} extractions to {OUTPUT_DIR}/\n")

    for i, eid in enumerate(EXTRACTION_IDS, 1):
        # Try extractions table via API first
        data = fetch_from_api(eid)
        doc_type = "qp"

        if data is None:
            # Try memo_extractions table
            data = fetch_from_supabase_memo(supabase, eid)
            doc_type = "memo"

        if data is None:
            print(f"  [{i}/10] {eid} -- NOT FOUND in either table")
            continue

        # Extract metadata from the appropriate location
        if doc_type == "memo":
            meta = get_memo_meta(data)
        else:
            meta = get_qp_meta(data)

        suffix = "mg" if doc_type == "memo" else "qp"
        # Prefer scraped_file_id for canonical naming (end-to-end traceability)
        scraped_file_id = data.get("scraped_file_id")
        name_id = scraped_file_id if scraped_file_id else eid
        canonical = build_canonical_name(
            name_id, meta["subject"], meta["grade"],
            meta["session"], meta["year"], suffix
        )

        # Build markdown
        if doc_type == "memo":
            md = memo_to_markdown(data, meta, eid)
        else:
            md = qp_to_markdown(data, meta, eid)

        out_name = f"{canonical}.md"
        out_path = OUTPUT_DIR / out_name
        out_path.write_text(md, encoding="utf-8")

        lang = meta["language"] or "N/A"
        subj = meta["subject"] or "N/A"
        status = data.get("status", "?")
        print(f"  [{i}/10] {out_name}")
        print(f"          subject={subj}  language={lang}  type={doc_type}  status={status}")

    print(f"\nDone. Markdown files saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
