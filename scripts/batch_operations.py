"""
Batch Operations CLI for Supabase scraped_files
================================================

Query, export, update, and analyze papers stored in Supabase.

Usage:
    python scripts/batch_operations.py stats
    python scripts/batch_operations.py list --subject "Mathematics" --grade 12
    python scripts/batch_operations.py export-csv --output papers.csv
    python scripts/batch_operations.py update-metadata --filter-subject "Maths" --set-subject "Mathematics"
    python scripts/batch_operations.py rename --file-id abc123 --new-filename "Paper1.pdf"

Created: 2026-02-02
"""

import os
import sys
import csv
import json
import argparse
import logging
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TABLE = "scraped_files"


def get_supabase():
    """Initialize Supabase client."""
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        logger.error("SUPABASE_URL and SUPABASE_KEY must be set in .env")
        sys.exit(1)
    return create_client(url, key)


def apply_filters(query, args):
    """Apply common filter arguments to a Supabase query."""
    if getattr(args, "subject", None):
        query = query.ilike("subject", f"%{args.subject}%")
    if getattr(args, "grade", None):
        query = query.eq("grade", args.grade)
    if getattr(args, "year", None):
        query = query.eq("year", args.year)
    if getattr(args, "document_type", None):
        query = query.eq("document_type", args.document_type)
    if getattr(args, "session", None):
        query = query.ilike("session", f"%{args.session}%")
    if getattr(args, "status", None):
        query = query.eq("status", args.status)
    if getattr(args, "syllabus", None):
        query = query.ilike("syllabus", f"%{args.syllabus}%")
    return query


def add_filter_args(parser):
    """Add common filter arguments to a subcommand parser."""
    parser.add_argument("--subject", help="Filter by subject (partial match)")
    parser.add_argument("--grade", type=int, help="Filter by grade (1-12)")
    parser.add_argument("--year", type=int, help="Filter by exam year")
    parser.add_argument("--document-type", dest="document_type", help="Filter by document type (QP, MG, etc.)")
    parser.add_argument("--session", help="Filter by session (MAY/JUNE, NOV, etc.)")
    parser.add_argument("--status", help="Filter by status")
    parser.add_argument("--syllabus", help="Filter by syllabus (NSC, IEB)")


# ============================================================================
# Subcommands
# ============================================================================


def cmd_stats(args) -> None:
    """Show summary statistics for papers in Supabase."""
    sb = get_supabase()

    # Total count
    resp = sb.table(TABLE).select("id", count="exact").execute()
    total = resp.count or 0

    print("\n" + "=" * 60)
    print("SCRAPED FILES STATISTICS")
    print("=" * 60)
    print(f"\nTotal records: {total}")

    if total == 0:
        print("No records found.")
        return

    # Fetch all records for aggregation (paginated)
    all_records = _fetch_all(sb)

    # Aggregate
    by_subject: Dict[str, int] = {}
    by_grade: Dict[int, int] = {}
    by_year: Dict[int, int] = {}
    by_type: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    by_session: Dict[str, int] = {}
    by_syllabus: Dict[str, int] = {}
    has_storage = 0
    has_source = 0

    for rec in all_records:
        subj = rec.get("subject") or "Unknown"
        by_subject[subj] = by_subject.get(subj, 0) + 1

        g = rec.get("grade")
        if g:
            by_grade[g] = by_grade.get(g, 0) + 1

        y = rec.get("year")
        if y:
            by_year[y] = by_year.get(y, 0) + 1

        dt = rec.get("document_type") or "Unknown"
        by_type[dt] = by_type.get(dt, 0) + 1

        st = rec.get("status") or "Unknown"
        by_status[st] = by_status.get(st, 0) + 1

        sess = rec.get("session") or "Unknown"
        by_session[sess] = by_session.get(sess, 0) + 1

        syl = rec.get("syllabus") or "Unknown"
        by_syllabus[syl] = by_syllabus.get(syl, 0) + 1

        if rec.get("storage_path"):
            has_storage += 1
        if rec.get("source_url"):
            has_source += 1

    def print_dist(title: str, dist: dict, sort_key=None, limit: int = 15):
        print(f"\n{title}:")
        items = sorted(dist.items(), key=sort_key or (lambda x: -x[1]))[:limit]
        for val, count in items:
            pct = count / total * 100
            print(f"  {str(val):>30}: {count:>5} ({pct:.1f}%)")
        if len(dist) > limit:
            print(f"  ... and {len(dist) - limit} more")

    print_dist("By Subject", by_subject)
    print_dist("By Grade", by_grade, sort_key=lambda x: x[0])
    print_dist("By Year", by_year, sort_key=lambda x: x[0])
    print_dist("By Document Type", by_type)
    print_dist("By Status", by_status)
    print_dist("By Session", by_session)
    print_dist("By Syllabus", by_syllabus)

    print(f"\nField Coverage:")
    print(f"  Has storage_path: {has_storage:>5} / {total} ({has_storage/total*100:.1f}%)")
    print(f"  Has source_url:   {has_source:>5} / {total} ({has_source/total*100:.1f}%)")
    print("=" * 60 + "\n")


def cmd_list(args) -> None:
    """List papers matching filters."""
    sb = get_supabase()

    query = sb.table(TABLE).select(
        "file_id, filename, subject, grade, year, document_type, session, status"
    )
    query = apply_filters(query, args)

    limit = getattr(args, "limit", 50) or 50
    query = query.limit(limit).order("filename")

    resp = query.execute()
    records = resp.data

    if not records:
        print("No records match the given filters.")
        return

    # Print as table
    print(f"\n{'Filename':<50} {'Subject':<20} {'Gr':<3} {'Year':<5} {'Type':<5} {'Session':<12} {'Status':<12}")
    print("-" * 110)
    for rec in records:
        fn = (rec.get("filename") or "")[:49]
        subj = (rec.get("subject") or "")[:19]
        gr = str(rec.get("grade") or "")
        yr = str(rec.get("year") or "")
        dt = (rec.get("document_type") or "")[:4]
        sess = (rec.get("session") or "")[:11]
        st = (rec.get("status") or "")[:11]
        print(f"{fn:<50} {subj:<20} {gr:<3} {yr:<5} {dt:<5} {sess:<12} {st:<12}")

    print(f"\nShowing {len(records)} records (limit: {limit})")


def cmd_export_csv(args) -> None:
    """Export papers to CSV file."""
    sb = get_supabase()

    query = sb.table(TABLE).select("*")
    query = apply_filters(query, args)

    records = _fetch_all_query(sb, query, args)

    if not records:
        print("No records to export.")
        return

    output = args.output or "scraped_files_export.csv"

    # Determine columns from first record
    columns = list(records[0].keys())
    # Move metadata to end (it's large JSONB)
    if "metadata" in columns:
        columns.remove("metadata")
        columns.append("metadata")

    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            # Convert metadata dict to JSON string for CSV
            if "metadata" in rec and isinstance(rec["metadata"], dict):
                rec["metadata"] = json.dumps(rec["metadata"])
            writer.writerow(rec)

    print(f"Exported {len(records)} records to {output}")


def cmd_update_metadata(args) -> None:
    """Bulk update metadata fields based on filters."""
    sb = get_supabase()

    # Build update payload from --set-* arguments
    updates = {}
    for field in ["subject", "grade", "document_type", "year", "session", "syllabus", "language", "status"]:
        val = getattr(args, f"set_{field}", None)
        if val is not None:
            if field in ("grade", "year"):
                updates[field] = int(val)
            else:
                updates[field] = val

    if not updates:
        print("No --set-* arguments provided. Nothing to update.")
        print("Available: --set-subject, --set-grade, --set-document-type, --set-year,")
        print("           --set-session, --set-syllabus, --set-language, --set-status")
        return

    # Count matching records first
    count_query = sb.table(TABLE).select("id", count="exact")
    count_query = apply_filters(count_query, args)
    count_resp = count_query.execute()
    match_count = count_resp.count or 0

    if match_count == 0:
        print("No records match the given filters. Nothing to update.")
        return

    print(f"\nWill update {match_count} records with: {updates}")

    if not args.yes:
        confirm = input("Proceed? (y/N): ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return

    # Apply update with filters
    query = sb.table(TABLE).update(updates)
    query = apply_filters(query, args)
    resp = query.execute()

    updated = len(resp.data) if resp.data else 0
    print(f"Updated {updated} records.")


def cmd_rename(args) -> None:
    """Rename a file in Supabase (and optionally in Firebase Storage)."""
    sb = get_supabase()

    if not args.file_id or not args.new_filename:
        print("Both --file-id and --new-filename are required.")
        return

    # Fetch current record
    resp = sb.table(TABLE).select("*").eq("file_id", args.file_id).execute()
    if not resp.data:
        print(f"No record found with file_id: {args.file_id}")
        return

    record = resp.data[0]
    old_filename = record["filename"]
    print(f"Renaming: {old_filename} -> {args.new_filename}")

    # Update Supabase
    update_resp = (
        sb.table(TABLE)
        .update({"filename": args.new_filename})
        .eq("file_id", args.file_id)
        .execute()
    )

    if update_resp.data:
        print(f"Supabase record updated.")
    else:
        print("Failed to update Supabase record.")
        return

    # Optionally rename in Firebase Storage
    if args.rename_storage and record.get("storage_path"):
        try:
            from google.cloud import storage as gcs

            cred_path = os.environ.get("FIREBASE_CREDENTIALS_PATH")
            if not cred_path:
                print("FIREBASE_CREDENTIALS_PATH not set. Skipping storage rename.")
                return

            client = gcs.Client.from_service_account_json(cred_path)
            bucket_name = record.get("storage_bucket", "scrapperdb-f854d.firebasestorage.app")
            bucket = client.bucket(bucket_name)

            old_blob = bucket.blob(record["storage_path"])
            # Compute new storage path
            old_dir = "/".join(record["storage_path"].split("/")[:-1])
            new_path = f"{old_dir}/{args.new_filename}" if old_dir else args.new_filename

            bucket.rename_blob(old_blob, new_path)

            # Update storage_path in Supabase
            sb.table(TABLE).update({"storage_path": new_path}).eq("file_id", args.file_id).execute()
            print(f"Firebase Storage renamed: {record['storage_path']} -> {new_path}")

        except ImportError:
            print("google-cloud-storage not installed. Skipping storage rename.")
        except Exception as e:
            print(f"Storage rename failed: {e}")
            print("Supabase record was updated but storage file was NOT renamed.")


# ============================================================================
# Helpers
# ============================================================================


def _fetch_all(sb, table: str = TABLE) -> List[Dict[str, Any]]:
    """Fetch all records from a table, handling pagination."""
    all_records = []
    offset = 0
    page_size = 1000

    while True:
        resp = sb.table(table).select("*").range(offset, offset + page_size - 1).execute()
        if not resp.data:
            break
        all_records.extend(resp.data)
        if len(resp.data) < page_size:
            break
        offset += page_size

    return all_records


def _fetch_all_query(sb, base_query, args, table: str = TABLE) -> List[Dict[str, Any]]:
    """Fetch all records with filters applied, handling pagination."""
    all_records = []
    offset = 0
    page_size = 1000

    while True:
        query = sb.table(table).select("*")
        query = apply_filters(query, args)
        query = query.range(offset, offset + page_size - 1)
        resp = query.execute()
        if not resp.data:
            break
        all_records.extend(resp.data)
        if len(resp.data) < page_size:
            break
        offset += page_size

    return all_records


# ============================================================================
# CLI Setup
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Batch operations for Supabase scraped_files"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # stats
    stats_parser = subparsers.add_parser("stats", help="Show summary statistics")

    # list
    list_parser = subparsers.add_parser("list", help="List papers matching filters")
    add_filter_args(list_parser)
    list_parser.add_argument("--limit", type=int, default=50, help="Max records to show (default: 50)")

    # export-csv
    export_parser = subparsers.add_parser("export-csv", help="Export papers to CSV")
    add_filter_args(export_parser)
    export_parser.add_argument("--output", "-o", help="Output CSV file (default: scraped_files_export.csv)")

    # update-metadata
    update_parser = subparsers.add_parser("update-metadata", help="Bulk update metadata fields")
    add_filter_args(update_parser)
    update_parser.add_argument("--set-subject", dest="set_subject", help="Set subject")
    update_parser.add_argument("--set-grade", dest="set_grade", help="Set grade")
    update_parser.add_argument("--set-document-type", dest="set_document_type", help="Set document type")
    update_parser.add_argument("--set-year", dest="set_year", help="Set year")
    update_parser.add_argument("--set-session", dest="set_session", help="Set session")
    update_parser.add_argument("--set-syllabus", dest="set_syllabus", help="Set syllabus")
    update_parser.add_argument("--set-language", dest="set_language", help="Set language")
    update_parser.add_argument("--set-status", dest="set_status", help="Set status")
    update_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

    # rename
    rename_parser = subparsers.add_parser("rename", help="Rename a file")
    rename_parser.add_argument("--file-id", required=True, help="File ID to rename")
    rename_parser.add_argument("--new-filename", required=True, help="New filename")
    rename_parser.add_argument(
        "--rename-storage", action="store_true",
        help="Also rename in Firebase Storage (requires google-cloud-storage)"
    )

    args = parser.parse_args()

    commands = {
        "stats": cmd_stats,
        "list": cmd_list,
        "export-csv": cmd_export_csv,
        "update-metadata": cmd_update_metadata,
        "rename": cmd_rename,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
