#!/usr/bin/env python3
"""
Simple test without emoji characters for Windows terminal compatibility.
Automatically saves JSON output to Sample PDFS/outputs/ folder.
"""

import asyncio
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.services.gemini_client import get_gemini_client
from app.services.pdf_extractor import extract_pdf_data_hybrid


async def test_extraction(pdf_path: str) -> None:
    """Test PDF extraction."""
    pdf_file = Path(pdf_path)

    # Create output folder in Sample PDFS directory
    output_dir = Path("Sample PDFS") / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate output filename based on PDF name
    output_filename = pdf_file.stem + "_result.json"
    output_path = output_dir / output_filename

    print("=" * 80)
    print("PDF EXTRACTION TEST")
    print("=" * 80)
    print(f"File: {pdf_file.name}")
    print(f"Path: {pdf_file.absolute()}")
    print(f"Size: {pdf_file.stat().st_size / 1024:.1f} KB")

    print("\nLoading configuration...")
    settings = get_settings()
    print(f"  Model: {settings.model_name}")
    print(f"  Hybrid Mode: {'Enabled' if settings.enable_hybrid_mode else 'Disabled'}")

    print("\nConnecting to Gemini API...")
    client = get_gemini_client()
    print("  Connected")

    print("\nStarting extraction...")
    print("  (This may take 10-30 seconds)")

    try:
        result = await extract_pdf_data_hybrid(
            client=client,
            file_path=str(pdf_file.absolute()),
            raise_on_partial=False
        )

        print("\n[SUCCESS] Extraction complete!")
        print("\nProcessing Metadata:")
        print(f"  Method: {result.processing_metadata.get('method', 'unknown')}")
        print(f"  Cache Eligible: {result.processing_metadata.get('cache_eligible', False)}")
        print(f"  Cache Hit: {result.processing_metadata.get('cache_hit', False)}")

        # Exam paper metadata
        print(f"\nExam Paper Details:")
        print(f"  Subject: {result.subject}")
        print(f"  Language: {result.language}")
        print(f"  Syllabus: {result.syllabus}")
        print(f"  Year: {result.year}")
        print(f"  Session: {result.session}")
        print(f"  Grade: {result.grade}")
        print(f"  Total Marks: {result.total_marks}")

        # Question groups summary
        print(f"\nQuestion Groups: {len(result.groups)}")
        total_questions = 0
        match_questions = 0
        guide_table_questions = 0
        context_questions = 0
        for group in result.groups:
            q_count = len(group.questions)
            total_questions += q_count
            for q in group.questions:
                if q.match_data:
                    match_questions += 1
                if q.guide_table:
                    guide_table_questions += 1
                if q.context:
                    context_questions += 1
            print(f"  {group.group_id}: {q_count} questions")
        print(f"\nTotal Questions: {total_questions}")
        if match_questions > 0:
            print(f"  Match Column Questions: {match_questions}")
        if guide_table_questions > 0:
            print(f"  Guide Table Questions: {guide_table_questions}")
        if context_questions > 0:
            print(f"  Questions with Context: {context_questions}")

        # Save JSON output
        print(f"\nSaving results to: {output_path}")
        result_dict = result.model_dump()
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result_dict, f, indent=2, ensure_ascii=False)
        print(f"  Saved successfully!")

        print("\n" + "=" * 80)
        print("TEST PASSED")
        print("=" * 80)

    except Exception as e:
        print(f"\n[ERROR] Extraction failed: {type(e).__name__}: {e}")

        if hasattr(e, 'partial_result'):
            print("\nPartial extraction available")
            print(f"  Subject: {e.partial_result.subject}")
            print(f"  Groups: {len(e.partial_result.groups)}")

            # Save partial results
            print(f"\nSaving partial results to: {output_path}")
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(e.partial_result.model_dump(), f, indent=2, ensure_ascii=False)
            print("  Partial results saved")

        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_simple.py <pdf_path>")
        sys.exit(1)

    asyncio.run(test_extraction(sys.argv[1]))
