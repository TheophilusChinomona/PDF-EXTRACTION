"""
Command-line interface for PDF-Extraction app.

Usage:
    python -m app.cli batch-process [OPTIONS]
    python app/cli.py batch-process [OPTIONS]
"""

import argparse
import asyncio
import os
import sys

from app.config import get_settings
from app.services.batch_processor import process_directory


def create_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="pdf-extraction",
        description="PDF Extraction CLI - Process PDFs locally"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Batch process command
    batch_parser = subparsers.add_parser(
        "batch-process",
        help="Process multiple PDFs in a directory"
    )
    batch_parser.add_argument(
        "--directory",
        "-d",
        type=str,
        default=None,
        help="Directory containing PDFs (default: Sample PDFS/)"
    )
    batch_parser.add_argument(
        "--pattern",
        "-p",
        type=str,
        default="document_*.pdf",
        help="Glob pattern for PDF files (default: document_*.pdf)"
    )
    batch_parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=None,
        help="Number of PDFs to process in parallel (default: from env or 1)"
    )
    batch_parser.add_argument(
        "--api-limit",
        "-a",
        type=int,
        default=None,
        help="Max concurrent Gemini API calls (default: from env or 3)"
    )

    return parser


async def batch_process_command(args: argparse.Namespace) -> int:
    """
    Execute batch processing command.

    Args:
        args: Parsed command-line arguments

    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    # Load settings
    try:
        settings = get_settings()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("\nMake sure you have a .env file with:")
        print("  GEMINI_API_KEY=your_api_key")
        print("  SUPABASE_URL=https://your-project.supabase.co")
        print("  SUPABASE_KEY=your_anon_key")
        return 1

    # Determine directory
    if args.directory:
        directory = args.directory
    else:
        # Default to Sample PDFS in project root
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        directory = os.path.join(project_root, "Sample PDFS")

    if not os.path.exists(directory):
        print(f"Error: Directory not found: {directory}")
        return 1

    if not os.path.isdir(directory):
        print(f"Error: Not a directory: {directory}")
        return 1

    # Determine concurrency (CLI overrides env)
    workers = args.workers if args.workers is not None else settings.batch_workers
    api_limit = args.api_limit if args.api_limit is not None else settings.batch_api_limit

    # Validate
    if workers < 1 or workers > 50:
        print("Error: --workers must be between 1 and 50")
        return 1

    if api_limit < 1 or api_limit > 10:
        print("Error: --api-limit must be between 1 and 10")
        return 1

    # Process directory
    try:
        results = await process_directory(
            directory=directory,
            workers=workers,
            api_limit=api_limit,
            pattern=args.pattern
        )

        # Return success if at least one file succeeded
        succeeded = sum(1 for r in results if r["status"] == "ok")
        return 0 if succeeded > 0 else 1

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 1
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main() -> int:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Route to command handler
    if args.command == "batch-process":
        return asyncio.run(batch_process_command(args))
    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
