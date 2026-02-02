"""
Local batch PDF processing service.

Processes multiple PDFs from a directory with configurable parallel processing.
Separate from the API batch endpoint (/api/batch) which handles uploads.
"""

import asyncio
import glob
import hashlib
import json
import os
import shutil
import time
import traceback
from typing import List, Optional

from app.config import get_settings
from app.services.opendataloader_extractor import extract_pdf_structure
from app.services.document_classifier import classify_document
from app.services.gemini_client import get_gemini_client
from app.services.memo_extractor import extract_memo_data_hybrid
from app.services.pdf_extractor import extract_pdf_data_hybrid


async def process_single_pdf(
    file_path: str,
    client,
    idx: int,
    total: int,
    api_semaphore: asyncio.Semaphore
) -> dict:
    """
    Process a single PDF through classify -> extract -> rename pipeline.

    Args:
        file_path: Path to the PDF file
        client: Gemini API client
        idx: Current file index (for progress display)
        total: Total number of files to process
        api_semaphore: Semaphore to control concurrent API calls

    Returns:
        dict: Processing result with status, doc_type, timings, etc.
    """
    basename = os.path.basename(file_path)
    t0 = time.time()
    info = {"file": basename, "status": "ok"}

    try:
        # Step 1: OpenDataLoader (local, fast, free)
        doc = extract_pdf_structure(file_path)
        info["quality"] = doc.quality_score

        # Step 2: Classify document type
        classification = classify_document(
            filename=basename,
            markdown_text=doc.markdown,
            gemini_client=client,
        )
        info["doc_type"] = classification.doc_type
        info["classify_method"] = classification.method
        info["classify_confidence"] = classification.confidence

        # Step 3: Extract (with API rate limiting)
        async with api_semaphore:
            if classification.doc_type == "memo":
                result = await extract_memo_data_hybrid(
                    client=client, file_path=file_path, doc_structure=doc
                )
            else:
                result = await extract_pdf_data_hybrid(
                    client=client, file_path=file_path, doc_structure=doc
                )

        info["extraction_method"] = result.processing_metadata.get("method")

        # Step 4: Generate canonical filename and rename
        with open(file_path, "rb") as fh:
            document_id = hashlib.sha256(fh.read()).hexdigest()[:12]

        suffix = "mg" if classification.doc_type == "memo" else "qp"
        canonical_stem = result.build_canonical_filename(document_id, suffix=suffix)

        input_dir = os.path.dirname(file_path)
        json_path = os.path.join(input_dir, f"{canonical_stem}.json")
        pdf_path = os.path.join(input_dir, f"{canonical_stem}.pdf")

        # Save JSON result
        json_str = json.dumps(result.model_dump(), indent=2, ensure_ascii=False)
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(json_str)

        # Move PDF to canonical name (shutil.move works across filesystems; check target exists)
        if os.path.exists(pdf_path) and os.path.abspath(file_path) != os.path.abspath(pdf_path):
            # Target already exists and is different file; skip move to avoid overwriting
            info["pdf"] = os.path.basename(file_path)
        else:
            shutil.move(file_path, pdf_path)
            info["pdf"] = os.path.basename(pdf_path)

        info["canonical"] = canonical_stem
        info["json"] = os.path.basename(json_path)

    except Exception as e:
        info["status"] = "FAILED"
        info["error"] = str(e)
        traceback.print_exc()

    elapsed = time.time() - t0
    info["elapsed_s"] = round(elapsed, 1)

    # Print progress
    tag = "OK" if info["status"] == "ok" else "FAILED"
    print(
        f"[{idx+1}/{total}] {tag} {basename} -> "
        f"doc_type={info.get('doc_type','?')} "
        f"method={info.get('classify_method','?')} "
        f"extraction={info.get('extraction_method','?')} "
        f"({info['elapsed_s']}s)"
    )
    if info["status"] == "ok":
        print(f"         -> {info.get('pdf', '?')}")

    return info


async def process_directory(
    directory: str,
    workers: int,
    api_limit: int,
    pattern: str = "document_*.pdf"
) -> List[dict]:
    """
    Process all PDFs in a directory matching the given pattern.

    Args:
        directory: Directory containing PDF files
        workers: Number of PDFs to process concurrently (1=sequential)
        api_limit: Max concurrent Gemini API calls (prevents rate limits)
        pattern: Glob pattern for PDF files (default: "document_*.pdf")

    Returns:
        List[dict]: Processing results for all files
    """
    # Find PDFs
    pdfs = sorted(glob.glob(os.path.join(directory, pattern)))
    total = len(pdfs)

    if total == 0:
        print(f"No PDFs found matching pattern: {pattern}")
        return []

    print(f"Found {total} PDFs to process")
    print(f"Concurrency: {workers} workers, {api_limit} API calls max\n")

    # Create Gemini client and API semaphore
    client = get_gemini_client()
    api_semaphore = asyncio.Semaphore(api_limit)

    # Process PDFs
    results = []

    if workers == 1:
        # Sequential processing (easier debugging, deterministic order)
        for idx, pdf in enumerate(pdfs):
            info = await process_single_pdf(pdf, client, idx, total, api_semaphore)
            results.append(info)
    else:
        # Parallel processing with asyncio.gather
        tasks = [
            process_single_pdf(pdf, client, idx, total, api_semaphore)
            for idx, pdf in enumerate(pdfs)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions (convert to failed result dicts)
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                results[idx] = {
                    "file": os.path.basename(pdfs[idx]),
                    "status": "FAILED",
                    "error": str(result),
                    "elapsed_s": 0,
                }

    # Print summary
    ok = [r for r in results if r["status"] == "ok"]
    failed = [r for r in results if r["status"] != "ok"]
    memos = [r for r in ok if r.get("doc_type") == "memo"]
    qps = [r for r in ok if r.get("doc_type") == "question_paper"]

    print(f"\n{'='*60}")
    print(f"DONE: {len(ok)}/{total} succeeded, {len(failed)} failed")
    print(f"  Memos: {len(memos)}, Question Papers: {len(qps)}")

    if failed:
        print(f"\nFailed files:")
        for r in failed:
            print(f"  - {r['file']}: {r.get('error','unknown')}")

    # Save summary
    summary_path = os.path.join(directory, "_batch_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nSummary saved to {summary_path}")

    return results
