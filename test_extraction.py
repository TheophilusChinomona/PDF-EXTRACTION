#!/usr/bin/env python3
"""
Simple test script for PDF extraction.

Usage:
    python test_extraction.py "Sample PDFS/Business Studies P1 May-June 2025 Eng.pdf"
    python test_extraction.py "Sample PDFS/English FAL P1 May-June 2025.pdf" --output results.json
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.services.gemini_client import get_gemini_client
from app.services.pdf_extractor import extract_pdf_data_hybrid


def print_divider(title: str = "") -> None:
    """Print a visual divider with optional title."""
    if title:
        print(f"\n{'=' * 80}")
        print(f"  {title}")
        print(f"{'=' * 80}\n")
    else:
        print(f"{'=' * 80}\n")


def print_extraction_results(result) -> None:
    """Pretty print extraction results for exam papers."""
    print_divider("EXTRACTION RESULTS")

    # Exam Paper Metadata
    print("EXAM PAPER METADATA:")
    print(f"  Subject: {result.subject}")
    print(f"  Syllabus: {result.syllabus}")
    print(f"  Year: {result.year}")
    print(f"  Session: {result.session}")
    print(f"  Grade: {result.grade}")
    print(f"  Total Marks: {result.total_marks}")

    # Question Groups Summary
    print(f"\nQUESTION GROUPS ({len(result.groups)}):")
    total_questions = 0
    total_marks_found = 0
    for group in result.groups:
        q_count = len(group.questions)
        group_marks = sum(q.marks or 0 for q in group.questions)
        total_questions += q_count
        total_marks_found += group_marks
        print(f"  {group.group_id}: {group.title}")
        print(f"    Questions: {q_count}, Marks: {group_marks}")
        if group.instructions:
            instr_preview = group.instructions[:60] + "..." if len(group.instructions) > 60 else group.instructions
            print(f"    Instructions: {instr_preview}")

    print(f"\nTOTAL QUESTIONS: {total_questions}")
    print(f"MARKS EXTRACTED: {total_marks_found}/{result.total_marks}")

    # Sample questions preview
    print(f"\nSAMPLE QUESTIONS (first 5):")
    question_count = 0
    for group in result.groups:
        for q in group.questions:
            if question_count >= 5:
                break
            text_preview = q.text[:80] + "..." if len(q.text) > 80 else q.text
            marks_str = f"({q.marks} marks)" if q.marks else "(marks unknown)"
            print(f"  {q.id}: {text_preview} {marks_str}")
            if q.options:
                print(f"    [MCQ with {len(q.options)} options]")
            if q.scenario:
                print(f"    [Has scenario attached]")
            question_count += 1
        if question_count >= 5:
            break
    if total_questions > 5:
        print(f"  ... and {total_questions - 5} more questions")

    # Processing metadata
    print(f"\nPROCESSING METADATA:")
    print(f"  Method: {result.processing_metadata.get('method', 'unknown')}")
    if "opendataloader_quality" in result.processing_metadata:
        print(f"  OpenDataLoader Quality: {result.processing_metadata['opendataloader_quality']:.2%}")
    if "cost_savings_percent" in result.processing_metadata:
        print(f"  Cost Savings: {result.processing_metadata['cost_savings_percent']}%")
    if "element_count" in result.processing_metadata:
        print(f"  Elements Extracted: {result.processing_metadata['element_count']}")

    # Cache statistics (if available)
    if result.processing_metadata.get('cache_hit'):
        print(f"\nCACHE STATISTICS:")
        print(f"  Cache Hit: Yes")
        print(f"  Cached Tokens: {result.processing_metadata.get('cached_tokens', 0):,}")
        print(f"  Total Tokens: {result.processing_metadata.get('total_tokens', 0):,}")
        cached_pct = (result.processing_metadata.get('cached_tokens', 0) /
                     max(result.processing_metadata.get('total_tokens', 1), 1)) * 100
        print(f"  Cached Percentage: {cached_pct:.1f}%")

    print_divider()


async def test_extraction(pdf_path: str, output_file: Optional[str] = None) -> None:
    """
    Test PDF extraction on a single file.

    Args:
        pdf_path: Path to the PDF file
        output_file: Optional path to save JSON results. If not provided,
                    saves to Sample PDFS/outputs/ folder automatically.
    """
    # Validate file exists
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"[ERROR] File not found: {pdf_path}")
        sys.exit(1)

    if not pdf_file.suffix.lower() == '.pdf':
        print(f"[ERROR] File is not a PDF: {pdf_path}")
        sys.exit(1)

    # Create output folder and determine output path
    output_dir = Path("Sample PDFS") / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    # If no output file specified, auto-generate filename in outputs folder
    if output_file is None:
        output_filename = pdf_file.stem + "_result.json"
        output_file = str(output_dir / output_filename)

    print_divider("PDF EXTRACTION TEST")
    print(f"File: {pdf_file.name}")
    print(f"Path: {pdf_file.absolute()}")
    print(f"Size: {pdf_file.stat().st_size / 1024:.1f} KB")

    # Load configuration
    print("\nLoading configuration...")
    try:
        settings = get_settings()
        print(f"  Model: {settings.model_name}")
        print(f"  Hybrid Mode: {'Enabled' if settings.enable_hybrid_mode else 'Disabled'}")
    except Exception as e:
        print(f"[ERROR] Configuration error: {e}")
        sys.exit(1)

    # Initialize Gemini client
    print("\nConnecting to Gemini API...")
    try:
        client = get_gemini_client()
        print("  Connected")
    except Exception as e:
        print(f"[ERROR] Connection error: {e}")
        sys.exit(1)

    # Run extraction
    print("\nStarting extraction...")
    print("  (This may take 10-30 seconds depending on PDF size)")

    try:
        result = await extract_pdf_data_hybrid(
            client=client,
            file_path=str(pdf_file.absolute()),
            raise_on_partial=False  # Return partial results on error
        )
        print("  Extraction complete!")

        # Print results
        print_extraction_results(result)

        # Save to file (always saves, either to specified path or auto-generated)
        print(f"\nSaving results to {output_file}...")
        output_path = Path(output_file)

        # Convert result to dict for JSON serialization
        result_dict = result.model_dump()

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result_dict, f, indent=2, ensure_ascii=False)

        print(f"  Saved to {output_path.absolute()}")

        print("\nTest completed successfully!")

    except Exception as e:
        print(f"\n[ERROR] Extraction error: {type(e).__name__}: {e}")

        # Check if it's a partial extraction error
        if hasattr(e, 'partial_result'):
            print("\nPartial extraction available:")
            print(f"  Subject: {e.partial_result.subject}")
            print(f"  Groups: {len(e.partial_result.groups)}")

            # Save partial results (always saves)
            print(f"\nSaving partial results to {output_file}...")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(e.partial_result.model_dump(), f, indent=2, ensure_ascii=False)
            print("  Saved partial results")

        sys.exit(1)


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python test_extraction.py <pdf_path> [--output <output_file.json>]")
        print("\nResults are automatically saved to 'Sample PDFS/outputs/' folder.")
        print("Use --output to specify a custom location.\n")
        print("Examples:")
        print('  python test_extraction.py "Sample PDFS/Business Studies P1 May-June 2025 Eng.pdf"')
        print('  # Saves to: Sample PDFS/outputs/Business Studies P1 May-June 2025 Eng_result.json\n')
        print('  python test_extraction.py "Sample PDFS/English FAL P1 May-June 2025.pdf" --output custom.json')
        print('  # Saves to: custom.json')
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_file = None

    # Parse optional --output argument
    if len(sys.argv) >= 4 and sys.argv[2] == "--output":
        output_file = sys.argv[3]

    # Run extraction
    asyncio.run(test_extraction(pdf_path, output_file))


if __name__ == "__main__":
    main()
