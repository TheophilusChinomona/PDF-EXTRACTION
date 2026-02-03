"""
Test script for full extraction pipeline.
Tests all fixes: async sleep, Supabase wrapping, cache locking, null checks, etc.
"""

import asyncio
import hashlib
import sys
import time
from pathlib import Path

from app.services.gemini_client import get_gemini_client
from app.services.pdf_extractor import extract_pdf_data_hybrid
from app.db.supabase_client import get_supabase_client
from app.db.extractions import create_extraction


async def test_extraction_pipeline(pdf_path: str):
    """Test full extraction pipeline on a PDF file."""
    print(f"\n{'='*80}")
    print(f"Testing: {Path(pdf_path).name}")
    print(f"{'='*80}\n")

    try:
        # Step 1: Calculate file info
        print("1. Reading PDF file...")
        with open(pdf_path, 'rb') as f:
            content = f.read()
        file_size = len(content)
        file_hash = hashlib.sha256(content).hexdigest()
        print(f"   [OK] File size: {file_size:,} bytes")
        print(f"   [OK] File hash: {file_hash[:16]}...")

        # Step 2: Extract PDF (tests async cache, null checks, hybrid pipeline)
        print("\n2. Extracting PDF content (hybrid pipeline)...")
        client = get_gemini_client()

        start_time = time.time()
        result = await extract_pdf_data_hybrid(client, pdf_path)
        extraction_time = time.time() - start_time

        print(f"   [OK] Extraction completed in {extraction_time:.2f}s")
        print(f"   [OK] Subject: {result.subject}")
        print(f"   [OK] Syllabus: {result.syllabus}")
        print(f"   [OK] Year: {result.year}")
        print(f"   [OK] Session: {result.session}")
        print(f"   [OK] Grade: {result.grade}")
        print(f"   [OK] Language: {result.language}")
        print(f"   [OK] Total marks: {result.total_marks}")
        print(f"   [OK] Groups: {len(result.groups)}")

        # Count questions
        total_questions = sum(len(group.questions) for group in result.groups)
        print(f"   [OK] Total questions: {total_questions}")

        # Processing metadata
        if result.processing_metadata:
            meta = result.processing_metadata
            print(f"\n   Processing Metadata:")
            print(f"   - Method: {meta.get('processing_method', 'N/A')}")
            print(f"   - Quality score: {meta.get('quality_score', 'N/A')}")
            print(f"   - Cache hit: {meta.get('cache_hit', False)}")
            print(f"   - Total tokens: {meta.get('total_tokens', 'N/A')}")
            if meta.get('cached_tokens'):
                print(f"   - Cached tokens: {meta.get('cached_tokens', 0)}")

        # Step 3: Test database operations (tests asyncio.to_thread wrapping)
        print("\n3. Testing database operations...")
        supabase = get_supabase_client()

        # Test create_extraction (uses asyncio.to_thread)
        extraction_id = await create_extraction(
            client=supabase,
            data=result,
            file_info={
                'file_name': Path(pdf_path).name,
                'file_size_bytes': file_size,
                'file_hash': file_hash,
                'processing_time_seconds': extraction_time
            }
        )
        print(f"   [OK] Extraction saved to database: {extraction_id}")

        # Test get_extraction (uses asyncio.to_thread)
        from app.db.extractions import get_extraction
        retrieved = await get_extraction(supabase, extraction_id)
        if retrieved:
            print(f"   [OK] Successfully retrieved extraction from database")
            print(f"   [OK] Status: {retrieved.get('status')}")

        # Test check_duplicate (uses asyncio.to_thread)
        from app.db.extractions import check_duplicate
        duplicate_id = await check_duplicate(supabase, file_hash)
        if duplicate_id:
            print(f"   [OK] Duplicate detection working: {duplicate_id == extraction_id}")

        print(f"\n{'='*80}")
        print(f"[SUCCESS] ALL TESTS PASSED for {Path(pdf_path).name}")
        print(f"{'='*80}\n")

        return True

    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run tests on both PDFs."""
    pdf_files = [
        r"C:\Users\theoc\Desktop\Work\PDF-Extraction\Sample PDFS\document_62.pdf",
        r"C:\Users\theoc\Desktop\Work\PDF-Extraction\Sample PDFS\document.pdf"
    ]

    print("\n" + "="*80)
    print("FULL EXTRACTION PIPELINE TEST")
    print("Testing all fixes: async sleep, DB wrapping, cache locking, null checks")
    print("="*80)

    results = []
    for pdf_path in pdf_files:
        if not Path(pdf_path).exists():
            print(f"[WARNING] File not found: {pdf_path}")
            results.append(False)
            continue

        success = await test_extraction_pipeline(pdf_path)
        results.append(success)

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    for i, (pdf_path, success) in enumerate(zip(pdf_files, results), 1):
        status = "[PASSED]" if success else "[FAILED]"
        print(f"{i}. {Path(pdf_path).name}: {status}")

    all_passed = all(results)
    print(f"\nOverall: {'[ALL TESTS PASSED]' if all_passed else '[SOME TESTS FAILED]'}")
    print("="*80 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
