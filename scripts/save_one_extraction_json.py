#!/usr/bin/env python3
"""
Save one full extraction row (QP) as JSON for building the flat table from a single file.

Usage:
  python scripts/save_one_extraction_json.py [--out FILE]

Output: sample_jsons/one_extraction_qp.json (or --out path) with the same structure
as one row from the extractions table (id, file_name, subject, groups, etc.).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.supabase_client import get_supabase_client


def to_serializable(obj):
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(type(obj))


def main():
    parser = argparse.ArgumentParser(description="Save one extraction as JSON for table-from-one-json use.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("sample_jsons/one_extraction_qp.json"),
        help="Output path (default: sample_jsons/one_extraction_qp.json)",
    )
    args = parser.parse_args()

    client = get_supabase_client()
    r = (
        client.table("extractions")
        .select("*")
        .eq("status", "completed")
        .not_.is_("groups", "null")
        .limit(1)
        .execute()
    )
    if not r.data:
        print("No completed extraction with groups found.", file=sys.stderr)
        sys.exit(1)

    row = r.data[0]
    out = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(row, f, indent=2, default=to_serializable, ensure_ascii=False)
    print(f"Wrote: {out}")
    print(f"  file_name: {row.get('file_name')}, subject: {row.get('subject')}, year: {row.get('year')}")
    print(f"  groups: {len(row.get('groups') or [])} group(s)")


if __name__ == "__main__":
    main()
