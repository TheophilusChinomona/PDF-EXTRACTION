#!/usr/bin/env python3
"""
Simple test without emoji characters for Windows terminal compatibility.
"""

import asyncio
import sys
from pathlib import Path

from app.config import get_settings
from app.services.gemini_client import get_gemini_client
from app.services.pdf_extractor import extract_pdf_data_hybrid


async def test_extraction(pdf_path: str) -> None:
    """Test PDF extraction."""
    pdf_file = Path(pdf_path)

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
        print(f"  Confidence Score: {result.confidence_score:.2%}")

        if result.metadata:
            print(f"\nTitle: {result.metadata.title}")
        print(f"Sections: {len(result.sections)}")
        print(f"Tables: {len(result.tables)}")
        print(f"References: {len(result.references)}")

        print("\n" + "=" * 80)
        print("TEST PASSED")
        print("=" * 80)

    except Exception as e:
        print(f"\n[ERROR] Extraction failed: {type(e).__name__}: {e}")

        if hasattr(e, 'partial_result'):
            print("\nPartial extraction available")
            print(f"  Tables: {len(e.partial_result.tables)}")

        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_simple.py <pdf_path>")
        sys.exit(1)

    asyncio.run(test_extraction(sys.argv[1]))
