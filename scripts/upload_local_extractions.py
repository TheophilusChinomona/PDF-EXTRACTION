#!/usr/bin/env python3
"""
Upload local JSON extractions to Supabase.
Looks up scraped_file_id from scraped_files (by filename or metadata) so
extractions link to Firebase storage paths.
"""

import os
import re
import sys
import json
import hashlib
import asyncio
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import get_supabase_client
from app.db.extractions import create_extraction, check_duplicate
from app.db.memo_extractions import create_memo_extraction, check_memo_duplicate
from app.models.extraction import FullExamPaper
from app.models.memo_extraction import MarkingGuideline


def _normalize_filename(file_name: str) -> str:
    """Remove hash prefix (12 hex chars + '-') from file_name."""
    return re.sub(r"^[a-f0-9]{12}-", "", file_name).strip()


async def find_scraped_file_id(
    client,
    file_name: str,
    document_type: str,
    subject: str | None = None,
    year: int | None = None,
    grade: str | None = None,
    session: str | None = None,
) -> str | None:
    """
    Look up scraped_files.id by normalized filename or metadata.
    document_type is 'Question Paper' or 'Memorandum'.
    Returns UUID string or None.
    """
    clean = _normalize_filename(file_name)
    stem = clean.replace(".pdf", "").replace(".PDF", "") if clean else ""
    try:
        if stem:
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
    if subject and year is not None:
        try:
            r = await asyncio.to_thread(
                lambda: client.table("scraped_files")
                .select("id, subject, year, grade, session")
                .eq("validation_status", "validated")
                .eq("document_type", document_type)
                .eq("year", int(year))
                .limit(15)
                .execute()
            )
            if r.data:
                subj_lower = (subject or "").strip().lower()
                candidates = [
                    row
                    for row in r.data
                    if subj_lower in ((row.get("subject") or "").strip().lower())
                    or ((row.get("subject") or "").strip().lower()) in subj_lower
                ]
                if grade is not None:
                    grade_s = str(grade).strip()
                    candidates = [c for c in candidates if c.get("grade") is not None and (str(c.get("grade")) == grade_s or c.get("grade") == grade)]
                if session:
                    session_lower = (session or "").strip().lower()
                    candidates = [c for c in candidates if session_lower in ((c.get("session") or "").lower())]
                if len(candidates) == 1:
                    return str(candidates[0]["id"])
        except Exception:
            pass
    return None


def is_memo(data: dict, filename: str) -> bool:
    """Check if the extraction is a memo/marking guideline."""
    # Check filename indicators
    fn_lower = filename.lower()
    if "-mg" in fn_lower or "_mg" in fn_lower or "memo" in fn_lower or "marking" in fn_lower:
        return True
    
    # Handle non-dict data
    if not isinstance(data, dict):
        return False
    
    # Check data indicators
    if data.get("document_type") == "marking_guideline":
        return True
    if "answers" in data and isinstance(data.get("answers"), list):
        return True
    
    # Check title for memo indicators
    title = data.get("title", "") or data.get("subject", "")
    if title and "marking" in title.lower() or "memorandum" in title.lower():
        return True
    
    return False


async def upload_single(client, json_path: Path, dry_run: bool = False) -> dict:
    """Upload a single JSON extraction to Supabase."""
    result = {
        "file": json_path.name,
        "status": "unknown",
        "id": None,
        "error": None
    }
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"Failed to read JSON: {e}"
        return result
    
    # Skip non-dict data (invalid format)
    if not isinstance(data, dict):
        result["status"] = "error"
        result["error"] = f"Invalid format: root is {type(data).__name__}, not dict"
        return result
    
    # Generate file info
    json_content = json.dumps(data, sort_keys=True)
    file_hash = hashlib.sha256(json_content.encode()).hexdigest()
    
    # The filename should be based on the JSON file (without .json)
    # Try to find corresponding PDF filename
    pdf_name = json_path.stem + ".pdf"
    
    file_info = {
        "file_name": pdf_name,
        "file_size_bytes": len(json_content),
        "file_hash": file_hash,
        "processing_time_seconds": 0,
        "error_message": None,
        "retry_count": 0,
    }
    
    is_memo_doc = is_memo(data, json_path.name)
    document_type = "Memorandum" if is_memo_doc else "Question Paper"
    subject = None
    year = None
    grade = None
    session = None
    if is_memo_doc:
        meta = data.get("meta") or {}
        subject = meta.get("subject")
        year = meta.get("year")
        grade = meta.get("grade")
        session = meta.get("session")
    else:
        subject = data.get("subject")
        year = data.get("year")
        grade = data.get("grade")
        session = data.get("session")
    scraped_id = await find_scraped_file_id(
        client, pdf_name, document_type, subject=subject, year=year, grade=grade, session=session
    )
    if scraped_id:
        file_info["scraped_file_id"] = scraped_id
    
    # Check for duplicates
    if is_memo_doc:
        existing = await check_memo_duplicate(client, file_hash)
    else:
        existing = await check_duplicate(client, file_hash)
    
    if existing:
        result["status"] = "duplicate"
        result["id"] = existing
        return result
    
    if dry_run:
        result["status"] = "dry_run"
        result["doc_type"] = "memo" if is_memo_doc else "question_paper"
        return result
    
    try:
        if is_memo_doc:
            # Try to parse as MarkingGuideline
            memo_data = MarkingGuideline.model_validate(data)
            memo_data.processing_metadata = memo_data.processing_metadata or {}
            memo_data.processing_metadata.setdefault("method", "local_upload")
            extraction_id = await create_memo_extraction(
                client, memo_data, file_info, status="completed"
            )
            result["status"] = "uploaded"
            result["id"] = extraction_id
            result["doc_type"] = "memo"
        else:
            # Parse as FullExamPaper
            exam_data = FullExamPaper.model_validate(data)
            exam_data.processing_metadata = exam_data.processing_metadata or {}
            exam_data.processing_metadata.setdefault("method", "local_upload")
            extraction_id = await create_extraction(
                client, exam_data, file_info, status="completed"
            )
            result["status"] = "uploaded"
            result["id"] = extraction_id
            result["doc_type"] = "question_paper"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    
    return result


async def main(dry_run: bool = False):
    client = get_supabase_client()
    
    # Find all local JSON files
    sample_pdfs_dir = Path("Sample PDFS")
    test_batch_dir = Path("test_batch")
    
    json_files = list(sample_pdfs_dir.glob("*.json")) + list(test_batch_dir.glob("*.json"))
    
    print("=" * 70)
    print(f"UPLOADING LOCAL EXTRACTIONS TO SUPABASE")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE UPLOAD'}")
    print(f"Total files: {len(json_files)}")
    print("=" * 70)
    
    stats = {
        "uploaded": 0,
        "duplicate": 0,
        "error": 0,
        "dry_run": 0,
        "memos": 0,
        "qps": 0,
    }
    
    for i, json_file in enumerate(sorted(json_files), 1):
        result = await upload_single(client, json_file, dry_run=dry_run)
        
        status = result["status"]
        stats[status] = stats.get(status, 0) + 1
        
        if result.get("doc_type") == "memo":
            stats["memos"] += 1
        elif result.get("doc_type") == "question_paper":
            stats["qps"] += 1
        
        # Print progress
        status_emoji = {
            "uploaded": "[OK]",
            "duplicate": "[DUP]",
            "error": "[ERR]",
            "dry_run": "[DRY]",
        }.get(status, "[???]")
        
        print(f"{i:3d}/{len(json_files)} {status_emoji} {result['file'][:50]}")
        if result.get("error"):
            print(f"         Error: {result['error'][:60]}")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Uploaded:     {stats.get('uploaded', 0)}")
    print(f"  Duplicates:   {stats.get('duplicate', 0)}")
    print(f"  Errors:       {stats.get('error', 0)}")
    if dry_run:
        print(f"  Dry run:      {stats.get('dry_run', 0)}")
    print(f"  Question Papers: {stats['qps']}")
    print(f"  Memos:          {stats['memos']}")
    print("=" * 70)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Don't actually upload, just check")
    args = parser.parse_args()
    
    asyncio.run(main(dry_run=args.dry_run))
