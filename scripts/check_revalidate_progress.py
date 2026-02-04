#!/usr/bin/env python3
"""
Query Supabase for revalidation progress.

Shows how many validation_results (status=correct, scraped_file_id set) still have grade IS NULL
vs how many now have grade set. Run from project root:
  python scripts/check_revalidate_progress.py

If this repo uses a different Supabase project than ValidationAgent, run the SQL below
in Supabase Dashboard → SQL Editor instead.
"""

import os
import sys

# Run from project root so app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import get_supabase_client


def main() -> None:
    client = get_supabase_client()

    # Eligible for revalidation: status=correct, scraped_file_id not null
    # Still need revalidation: those with grade IS NULL
    remaining = (
        client.table("validation_results")
        .select("id", count="exact", head=True)
        .eq("status", "correct")
        .not_.is_("scraped_file_id", "null")
        .is_("grade", "null")
        .execute()
    )
    remaining_count = remaining.count if remaining.count is not None else 0

    # Already have grade (either from before or updated by revalidation)
    with_grade = (
        client.table("validation_results")
        .select("id", count="exact", head=True)
        .eq("status", "correct")
        .not_.is_("scraped_file_id", "null")
        .not_.is_("grade", "null")
        .execute()
    )
    with_grade_count = with_grade.count if with_grade.count is not None else 0

    total_eligible = remaining_count + with_grade_count

    print("Revalidation progress (validation_results: status=correct, scraped_file_id set)")
    print("-" * 60)
    print(f"  Still to do (grade IS NULL):  {remaining_count:,}")
    print(f"  Have grade (grade set):       {with_grade_count:,}")
    print(f"  Total eligible:               {total_eligible:,}")
    if total_eligible > 0:
        pct_done = 100.0 * with_grade_count / total_eligible
        print(f"  Progress:                     {pct_done:.1f}% have grade")
    else:
        print("  (If you run revalidation from ValidationAgent, ensure this repo's")
        print("   SUPABASE_URL/SUPABASE_KEY point at the same project, or run the")
        print("   SQL in docs/revalidate_validation_instructions.md in Supabase SQL Editor.)")
    print()


if __name__ == "__main__":
    main()
