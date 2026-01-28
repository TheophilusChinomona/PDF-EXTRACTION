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
    """Pretty print extraction results."""
    print_divider("EXTRACTION RESULTS")

    # Metadata
    print("📄 METADATA:")
    print(f"  Title: {result.metadata.title}")
    if result.metadata.authors:
        print(f"  Authors: {', '.join(result.metadata.authors)}")
    if result.metadata.journal:
        print(f"  Journal: {result.metadata.journal}")
    if result.metadata.year:
        print(f"  Year: {result.metadata.year}")
    if result.metadata.doi:
        print(f"  DOI: {result.metadata.doi}")

    # Abstract
    if result.abstract:
        print(f"\n📝 ABSTRACT:")
        abstract_preview = result.abstract[:200] + "..." if len(result.abstract) > 200 else result.abstract
        print(f"  {abstract_preview}")

    # Sections
    print(f"\n📑 SECTIONS ({len(result.sections)}):")
    for i, section in enumerate(result.sections[:5], 1):
        heading = section.get("heading", "Untitled")
        page = section.get("page_number", "?")
        print(f"  {i}. {heading} (Page {page})")
    if len(result.sections) > 5:
        print(f"  ... and {len(result.sections) - 5} more sections")

    # Tables
    print(f"\n📊 TABLES ({len(result.tables)}):")
    for i, table in enumerate(result.tables, 1):
        caption = table.caption or "Untitled Table"
        page = table.page_number
        rows = len(table.data) if table.data else 0
        print(f"  {i}. {caption} (Page {page}, {rows} rows)")

    # References
    print(f"\n📚 REFERENCES ({len(result.references)}):")
    for i, ref in enumerate(result.references[:3], 1):
        citation = ref.get("citation_text", "")[:80]
        print(f"  {i}. {citation}...")
    if len(result.references) > 3:
        print(f"  ... and {len(result.references) - 3} more references")

    # Bounding Boxes
    print(f"\n📍 BOUNDING BOXES ({len(result.bounding_boxes)}):")
    bbox_types = {}
    for element_id in result.bounding_boxes.keys():
        element_type = element_id.split("_")[0]
        bbox_types[element_type] = bbox_types.get(element_type, 0) + 1
    for element_type, count in bbox_types.items():
        print(f"  - {element_type}: {count}")

    # Processing metadata
    print(f"\n⚙️ PROCESSING METADATA:")
    print(f"  Method: {result.processing_metadata.get('method', 'unknown')}")
    print(f"  Confidence Score: {result.confidence_score:.2%}")
    if "opendataloader_quality" in result.processing_metadata:
        print(f"  OpenDataLoader Quality: {result.processing_metadata['opendataloader_quality']:.2%}")
    if "cost_savings_percent" in result.processing_metadata:
        print(f"  Cost Savings: {result.processing_metadata['cost_savings_percent']}%")
    if "element_count" in result.processing_metadata:
        print(f"  Elements Extracted: {result.processing_metadata['element_count']}")

    # Cache statistics (if available)
    if result.processing_metadata.get('cache_hit'):
        print(f"\n💾 CACHE STATISTICS:")
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
        print(f"❌ Error: File not found: {pdf_path}")
        sys.exit(1)

    if not pdf_file.suffix.lower() == '.pdf':
        print(f"❌ Error: File is not a PDF: {pdf_path}")
        sys.exit(1)

    # Create output folder and determine output path
    output_dir = Path("Sample PDFS") / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    # If no output file specified, auto-generate filename in outputs folder
    if output_file is None:
        output_filename = pdf_file.stem + "_result.json"
        output_file = str(output_dir / output_filename)

    print_divider("PDF EXTRACTION TEST")
    print(f"📄 File: {pdf_file.name}")
    print(f"📂 Path: {pdf_file.absolute()}")
    print(f"📦 Size: {pdf_file.stat().st_size / 1024:.1f} KB")

    # Load configuration
    print("\n🔧 Loading configuration...")
    try:
        settings = get_settings()
        print(f"  Model: {settings.model_name}")
        print(f"  Hybrid Mode: {'Enabled' if settings.enable_hybrid_mode else 'Disabled'}")
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        sys.exit(1)

    # Initialize Gemini client
    print("\n🔌 Connecting to Gemini API...")
    try:
        client = get_gemini_client()
        print("  ✅ Connected")
    except Exception as e:
        print(f"❌ Connection error: {e}")
        sys.exit(1)

    # Run extraction
    print("\n🚀 Starting extraction...")
    print("  (This may take 10-30 seconds depending on PDF size)")

    try:
        result = await extract_pdf_data_hybrid(
            client=client,
            file_path=str(pdf_file.absolute()),
            raise_on_partial=False  # Return partial results on error
        )
        print("  ✅ Extraction complete!")

        # Print results
        print_extraction_results(result)

        # Save to file (always saves, either to specified path or auto-generated)
        print(f"\n💾 Saving results to {output_file}...")
        output_path = Path(output_file)

        # Convert result to dict for JSON serialization
        result_dict = result.model_dump()

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result_dict, f, indent=2, ensure_ascii=False)

        print(f"  ✅ Saved to {output_path.absolute()}")

        print("\n✅ Test completed successfully!")

    except Exception as e:
        print(f"\n❌ Extraction error: {type(e).__name__}: {e}")

        # Check if it's a partial extraction error
        if hasattr(e, 'partial_result'):
            print("\n⚠️ Partial extraction available:")
            print_extraction_results(e.partial_result)

            # Save partial results (always saves)
            print(f"\n💾 Saving partial results to {output_file}...")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(e.partial_result.model_dump(), f, indent=2, ensure_ascii=False)
            print("  ✅ Saved partial results")

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
