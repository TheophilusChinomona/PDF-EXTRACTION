"""
Export extraction results to Markdown files with canonical naming.

Fetches extraction data from the API (extractions table) and directly from
Supabase (memo_extractions table), then converts to human-readable Markdown.

Filename convention matches the repo standard:
  {short_id}-{subject-slug}-gr{grade}-{session-slug}-{year}-{qp|mg}.md

Usage:
    python scripts/export_extractions_md.py                  # hardcoded IDs
    python scripts/export_extractions_md.py --all            # all completed
    python scripts/export_extractions_md.py --all --limit 50
    python scripts/export_extractions_md.py --all --since 2026-02-01

    # Export matched exam_sets pairs
    python scripts/export_extractions_md.py --exam-sets                     # all matched pairs
    python scripts/export_extractions_md.py --exam-sets --subject english   # filter by subject
    python scripts/export_extractions_md.py --exam-sets --limit 50          # limit results
    python scripts/export_extractions_md.py --exam-sets --status matched    # filter by status
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
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


# ---------------------------------------------------------------------------
# Exam Sets (matched QP-Memo pairs) export
# ---------------------------------------------------------------------------

def _source_url_matches(source_url: str | None, substring: str) -> bool:
    """True if source_url contains substring (case-insensitive)."""
    if not substring or not (source_url or "").strip():
        return True
    return substring.lower() in (source_url or "").lower()


def _fetch_exam_sets(
    supabase,
    limit: int | None,
    subject: str | None,
    status: str | None,
    source_url: str | None,
) -> list[dict]:
    """Fetch matched exam_sets with QP and Memo filenames.
    When source_url is set, only include pairs where both QP and Memo scraped_files have source_url containing it.
    Returns list of dicts with exam_set metadata and linked filenames.
    """
    # Use service role key if available for RLS bypass
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if service_key:
        sb = create_client(SUPABASE_URL, service_key)
    else:
        sb = supabase

    fetch_limit = limit if limit else 500

    q = sb.table("exam_sets").select("*")
    q = q.not_.is_("question_paper_id", "null")
    q = q.not_.is_("memo_id", "null")
    if status:
        q = q.eq("status", status)
    if subject:
        q = q.ilike("subject", f"%{subject}%")
    q = q.order("created_at", desc=True).limit(fetch_limit)

    try:
        resp = q.execute()
        exam_sets = resp.data or []
    except Exception as e:
        print(f"  WARNING: Failed to fetch exam_sets: {e}")
        return []

    results = []
    for es in exam_sets:
        qp_id = es.get("question_paper_id")
        memo_id = es.get("memo_id")

        qp_filename = None
        memo_filename = None
        qp_storage_path = None
        memo_storage_path = None
        qp_source_url = None
        memo_source_url = None

        if qp_id:
            try:
                r = sb.table("scraped_files").select("filename, storage_path, source_url").eq("id", qp_id).execute()
                if r.data:
                    qp_filename = r.data[0].get("filename")
                    qp_storage_path = r.data[0].get("storage_path")
                    qp_source_url = r.data[0].get("source_url")
            except Exception:
                pass

        if memo_id:
            try:
                r = sb.table("scraped_files").select("filename, storage_path, source_url").eq("id", memo_id).execute()
                if r.data:
                    memo_filename = r.data[0].get("filename")
                    memo_storage_path = r.data[0].get("storage_path")
                    memo_source_url = r.data[0].get("source_url")
            except Exception:
                pass

        if source_url:
            if not (_source_url_matches(qp_source_url, source_url) and _source_url_matches(memo_source_url, source_url)):
                continue

        results.append({
            **es,
            "qp_filename": qp_filename,
            "memo_filename": memo_filename,
            "qp_storage_path": qp_storage_path,
            "memo_storage_path": memo_storage_path,
        })

    return results


def _exam_sets_to_markdown(exam_sets: list[dict], subject_filter: str | None) -> str:
    """Convert exam_sets list to a formatted Markdown document."""
    lines: list[str] = []
    
    # Title
    if subject_filter:
        lines.append(f"# Exam Sets - {subject_filter.title()} Matched Pairs Export")
    else:
        lines.append("# Exam Sets - Matched Pairs Export")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Total Pairs:** {len(exam_sets)}")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Summary by subject
    subject_counts: dict[str, int] = {}
    for es in exam_sets:
        subj = es.get("subject") or "Unknown"
        subject_counts[subj] = subject_counts.get(subj, 0) + 1
    
    lines.append("## Summary by Subject")
    lines.append("")
    lines.append("| Subject | Count |")
    lines.append("|---------|-------|")
    for subj, count in sorted(subject_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {subj} | {count} |")
    lines.append("")
    
    # Summary by year
    year_counts: dict[int, int] = {}
    for es in exam_sets:
        year = es.get("year") or 0
        year_counts[year] = year_counts.get(year, 0) + 1
    
    lines.append("## Summary by Year")
    lines.append("")
    lines.append("| Year | Count |")
    lines.append("|------|-------|")
    for year, count in sorted(year_counts.items(), key=lambda x: -x[0]):
        if year > 0:
            lines.append(f"| {year} | {count} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Group by year
    by_year: dict[int, list[dict]] = {}
    for es in exam_sets:
        year = es.get("year") or 0
        if year not in by_year:
            by_year[year] = []
        by_year[year].append(es)
    
    lines.append("## Complete Matched Pairs")
    lines.append("")
    
    for year in sorted(by_year.keys(), reverse=True):
        if year == 0:
            continue
        lines.append(f"### {year}")
        lines.append("")
        lines.append("| Subject | Grade | Paper | Syllabus | Status | Question Paper | Memorandum |")
        lines.append("|---------|-------|-------|----------|--------|----------------|------------|")
        
        for es in sorted(by_year[year], key=lambda x: (x.get("subject") or "", x.get("paper_number") or 0)):
            subj = es.get("subject") or "Unknown"
            grade = es.get("grade") or "?"
            paper = es.get("paper_number") or "?"
            syllabus = es.get("syllabus") or "—"
            status = es.get("status") or "?"
            qp = es.get("qp_filename") or "—"
            memo = es.get("memo_filename") or "—"
            
            # Truncate long filenames
            if len(qp) > 50:
                qp = qp[:47] + "..."
            if len(memo) > 50:
                memo = memo[:47] + "..."
            
            lines.append(f"| {subj} | {grade} | {paper} | {syllabus} | {status} | `{qp}` | `{memo}` |")
        
        lines.append("")
    
    # Full data table
    lines.append("---")
    lines.append("")
    lines.append("## Full Data Table")
    lines.append("")
    lines.append("| # | Subject | Grade | Paper | Year | Session | Syllabus | Status | Confidence | QP Filename | Memo Filename |")
    lines.append("|---|---------|-------|-------|------|---------|----------|--------|------------|-------------|---------------|")
    
    for i, es in enumerate(exam_sets, 1):
        subj = es.get("subject") or "Unknown"
        grade = es.get("grade") or "?"
        paper = es.get("paper_number") or "?"
        year = es.get("year") or "?"
        session = es.get("session") or "—"
        syllabus = es.get("syllabus") or "—"
        status = es.get("status") or "?"
        confidence = es.get("match_confidence") or "—"
        qp = es.get("qp_filename") or "—"
        memo = es.get("memo_filename") or "—"
        
        lines.append(f"| {i} | {subj} | {grade} | {paper} | {year} | {session} | {syllabus} | {status} | {confidence} | {qp} | {memo} |")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Export generated by export_extractions_md.py --exam-sets*")
    
    return "\n".join(lines)


def _fetch_extraction_by_scraped_file_id(sb, scraped_file_id: str, table: str) -> dict | None:
    """Fetch one completed extraction or memo_extraction by scraped_file_id."""
    try:
        q = sb.table(table).select("*").eq("scraped_file_id", scraped_file_id).eq("status", "completed").limit(1)
        r = q.execute()
        if r.data and len(r.data) > 0:
            return r.data[0]
    except Exception:
        pass
    return None


def _export_exam_sets_extractions(supabase, exam_sets: list[dict]) -> int:
    """
    For each exam_set, fetch linked extraction and memo_extraction (by scraped_file_id),
    convert to markdown with qp_to_markdown/memo_to_markdown, and write paired .md files.
    Returns count of markdown files written.
    """
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    sb = create_client(SUPABASE_URL, service_key) if service_key else supabase
    written = 0
    for es in exam_sets:
        qp_id = es.get("question_paper_id")
        memo_id = es.get("memo_id")
        if not qp_id and not memo_id:
            continue
        subject = es.get("subject") or "unknown"
        year = es.get("year") or 0
        paper = es.get("paper_number") or 0
        session = es.get("session") or "unknown"
        short_id = (es.get("id") or "x")[:8]
        stem = f"{_slug(subject)}-{year}-p{paper}-{_slug(str(session))}-{short_id}"
        if qp_id:
            qp_row = _fetch_extraction_by_scraped_file_id(sb, str(qp_id), "extractions")
            if qp_row:
                meta = get_qp_meta(qp_row)
                md = qp_to_markdown(qp_row, meta, str(qp_row.get("id", "")))
                out_name = f"{stem}-qp.md"
                (OUTPUT_DIR / out_name).write_text(md, encoding="utf-8")
                written += 1
                print(f"  [QP]  {out_name}")
        if memo_id:
            memo_row = _fetch_extraction_by_scraped_file_id(sb, str(memo_id), "memo_extractions")
            if memo_row:
                meta = get_memo_meta(memo_row)
                md = memo_to_markdown(memo_row, meta, str(memo_row.get("id", "")))
                out_name = f"{stem}-mg.md"
                (OUTPUT_DIR / out_name).write_text(md, encoding="utf-8")
                written += 1
                print(f"  [MG]  {out_name}")
    return written


def _fetch_all_completed(supabase, limit: int | None, since: str | None) -> list[tuple[dict, str]]:
    """Fetch all completed extractions from both tables.

    Returns list of (row_dict, doc_type) tuples where doc_type is 'qp' or 'memo'.
    """
    results: list[tuple[dict, str]] = []

    # Use service role key if available for RLS bypass
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if service_key:
        sb = create_client(SUPABASE_URL, service_key)
    else:
        sb = supabase

    # Fetch from both tables (apply limit to each, then merge and trim)
    fetch_limit = limit if limit else 1000

    q = sb.table("extractions").select("*").eq("status", "completed")
    if since:
        q = q.gte("created_at", since)
    q = q.order("created_at", desc=True).limit(fetch_limit)
    try:
        resp = q.execute()
        for row in resp.data or []:
            results.append((row, "qp"))
    except Exception as e:
        print(f"  WARNING: Failed to fetch extractions: {e}")

    q2 = sb.table("memo_extractions").select("*").eq("status", "completed")
    if since:
        q2 = q2.gte("created_at", since)
    q2 = q2.order("created_at", desc=True).limit(fetch_limit)
    try:
        resp2 = q2.execute()
        for row in resp2.data or []:
            results.append((row, "memo"))
    except Exception as e:
        print(f"  WARNING: Failed to fetch memo_extractions: {e}")

    # Sort combined results by created_at descending, then trim to limit
    results.sort(key=lambda x: x[0].get("created_at", ""), reverse=True)
    if limit:
        results = results[:limit]

    return results


def _export_record(data: dict, doc_type: str, supabase, index: int, total: int) -> str | None:
    """Export a single extraction record to markdown. Returns output filename or None."""
    eid = str(data.get("id", "unknown"))

    if doc_type == "memo":
        meta = get_memo_meta(data)
    else:
        meta = get_qp_meta(data)

    suffix = "mg" if doc_type == "memo" else "qp"
    scraped_file_id = data.get("scraped_file_id")
    name_id = scraped_file_id if scraped_file_id else eid
    canonical = build_canonical_name(
        name_id, meta["subject"], meta["grade"],
        meta["session"], meta["year"], suffix,
    )

    if doc_type == "memo":
        md = memo_to_markdown(data, meta, eid)
    else:
        md = qp_to_markdown(data, meta, eid)

    out_name = f"{canonical}.md"
    out_path = OUTPUT_DIR / out_name
    out_path.write_text(md, encoding="utf-8")

    subj = meta["subject"] or "N/A"
    lang = meta["language"] or "N/A"
    status = data.get("status", "?")
    print(f"  [{index}/{total}] {out_name}")
    print(f"          subject={subj}  language={lang}  type={doc_type}  status={status}")
    return out_name


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export extraction results to Markdown files.",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Export all completed extractions from both tables.",
    )
    parser.add_argument(
        "--exam-sets", action="store_true",
        help="Export matched exam_sets (QP-Memo pairs) instead of extractions.",
    )
    parser.add_argument(
        "--subject", type=str, default=None,
        help="Filter by subject (case-insensitive, partial match). Use with --exam-sets.",
    )
    parser.add_argument(
        "--status", type=str, default=None,
        help="Filter by status (e.g., 'matched', 'duplicate_review'). Use with --exam-sets.",
    )
    parser.add_argument(
        "--source-url", type=str, default=None,
        help="Filter to pairs where both QP and Memo scraped_files have source_url containing this (e.g. education.gov.za). Use with --exam-sets.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max records to export.",
    )
    parser.add_argument(
        "--since", type=str, default=None,
        help="Only records created after this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output filename for --exam-sets mode (default: auto-generated).",
    )
    args = parser.parse_args()

    # Validate --since format
    if args.since:
        try:
            datetime.strptime(args.since, "%Y-%m-%d")
        except ValueError:
            parser.error("--since must be in YYYY-MM-DD format")

    OUTPUT_DIR.mkdir(exist_ok=True)
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Exam sets mode
    if args.exam_sets:
        print(f"Fetching exam_sets (matched QP-Memo pairs)...")
        if args.subject:
            print(f"  Subject filter: {args.subject}")
        if args.status:
            print(f"  Status filter: {args.status}")
        if args.source_url:
            print(f"  Source URL filter: {args.source_url}")
        if args.limit:
            print(f"  Limit: {args.limit}")

        exam_sets = _fetch_exam_sets(
            supabase,
            limit=args.limit,
            subject=args.subject,
            status=args.status,
            source_url=args.source_url,
        )

        if not exam_sets:
            print("No matching exam_sets found.")
            return

        print(f"Found {len(exam_sets)} matched pairs.")

        # Generate markdown
        md_content = _exam_sets_to_markdown(exam_sets, args.subject)

        # Determine output filename
        if args.output:
            out_name = args.output
        else:
            subject_slug = _slug(args.subject) if args.subject else "all"
            status_slug = _slug(args.status) if args.status else "pairs"
            source_slug = _slug(args.source_url or "") if args.source_url else ""
            parts = [f"exam-sets-{subject_slug}-{status_slug}"]
            if source_slug:
                parts.append(source_slug)
            parts.append("export.md")
            out_name = "-".join(parts)
        
        out_path = OUTPUT_DIR / out_name
        out_path.write_text(md_content, encoding="utf-8")
        
        print(f"\nSummary exported to: {out_path}")
        
        # Rebuild extraction JSON to markdown for pairs that have extraction data
        print(f"\nExporting extraction content to markdown (paired QP + Memo files)...")
        count = _export_exam_sets_extractions(supabase, exam_sets)
        print(f"\nDone. {count} markdown file(s) written from extraction content to: {OUTPUT_DIR}")
        return

    if args.all:
        records = _fetch_all_completed(supabase, limit=args.limit, since=args.since)
        total = len(records)
        print(f"Exporting {total} completed extraction(s) to {OUTPUT_DIR}/\n")
        exported = 0
        for i, (data, doc_type) in enumerate(records, 1):
            result = _export_record(data, doc_type, supabase, i, total)
            if result:
                exported += 1
        print(f"\nDone. {exported} Markdown files saved to: {OUTPUT_DIR}")
    else:
        # Legacy: hardcoded EXTRACTION_IDS
        ids = EXTRACTION_IDS
        total = len(ids)
        print(f"Exporting {total} extractions to {OUTPUT_DIR}/\n")

        for i, eid in enumerate(ids, 1):
            data = fetch_from_api(eid)
            doc_type = "qp"

            if data is None:
                data = fetch_from_supabase_memo(supabase, eid)
                doc_type = "memo"

            if data is None:
                print(f"  [{i}/{total}] {eid} -- NOT FOUND in either table")
                continue

            _export_record(data, doc_type, supabase, i, total)

        print(f"\nDone. Markdown files saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
