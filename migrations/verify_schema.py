"""
Verify database schema matches expected structure.
Tests that all migrations have been applied correctly.
"""

import os
import sys
from typing import List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import get_supabase_client


def check_table_exists(client, table_name: str) -> bool:
    """Check if a table exists."""
    try:
        # Query information_schema
        response = client.table('information_schema.tables').select('table_name').eq('table_name', table_name).eq('table_schema', 'public').execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"Error checking table {table_name}: {e}")
        return False


def check_column_exists(client, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    try:
        response = client.table('information_schema.columns').select('column_name').eq('table_name', table_name).eq('column_name', column_name).eq('table_schema', 'public').execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"Error checking column {table_name}.{column_name}: {e}")
        return False


def verify_extractions_table(client) -> bool:
    """Verify extractions table has correct schema."""
    print("\n1. Verifying 'extractions' table...")

    # Check table exists
    if not check_table_exists(client, 'extractions'):
        print("   [FAIL] Table 'extractions' does not exist")
        return False
    print("   [OK] Table exists")

    # Check exam paper columns
    required_columns = [
        'id', 'file_name', 'file_size_bytes', 'file_hash', 'status',
        'processing_method', 'quality_score',
        'subject', 'syllabus', 'year', 'session', 'grade', 'language', 'total_marks',
        'groups', 'processing_metadata',
        'error_message', 'retry_count', 'processing_time_seconds', 'cost_estimate_usd',
        'created_at', 'updated_at', 'webhook_url'
    ]

    missing_columns = []
    for col in required_columns:
        if not check_column_exists(client, 'extractions', col):
            missing_columns.append(col)

    if missing_columns:
        print(f"   [FAIL] Missing columns: {', '.join(missing_columns)}")
        print(f"   [INFO] Run migration 005_update_extractions_for_exam_papers.sql")
        return False

    print(f"   [OK] All {len(required_columns)} required columns present")
    return True


def verify_memo_extractions_table(client) -> bool:
    """Verify memo_extractions table has correct schema."""
    print("\n2. Verifying 'memo_extractions' table...")

    if not check_table_exists(client, 'memo_extractions'):
        print("   [FAIL] Table 'memo_extractions' does not exist")
        print("   [INFO] Run migration 004_create_memo_extractions_table.sql")
        return False
    print("   [OK] Table exists")

    required_columns = [
        'id', 'file_name', 'file_size_bytes', 'file_hash', 'status',
        'processing_method', 'quality_score',
        'subject', 'year', 'session', 'grade', 'total_marks',
        'sections', 'processing_metadata',
        'error_message', 'retry_count', 'processing_time_seconds', 'cost_estimate_usd',
        'created_at', 'updated_at', 'webhook_url'
    ]

    missing_columns = []
    for col in required_columns:
        if not check_column_exists(client, 'memo_extractions', col):
            missing_columns.append(col)

    if missing_columns:
        print(f"   [FAIL] Missing columns: {', '.join(missing_columns)}")
        return False

    print(f"   [OK] All {len(required_columns)} required columns present")
    return True


def verify_batch_jobs_table(client) -> bool:
    """Verify batch_jobs table has correct schema."""
    print("\n3. Verifying 'batch_jobs' table...")

    if not check_table_exists(client, 'batch_jobs'):
        print("   [FAIL] Table 'batch_jobs' does not exist")
        print("   [INFO] Run migration 003_create_batch_jobs_table.sql")
        return False
    print("   [OK] Table exists")

    required_columns = [
        'id', 'status', 'total_files', 'completed_files', 'failed_files',
        'routing_stats', 'extraction_ids',
        'cost_estimate_usd', 'cost_savings_usd',
        'created_at', 'updated_at', 'estimated_completion', 'webhook_url'
    ]

    missing_columns = []
    for col in required_columns:
        if not check_column_exists(client, 'batch_jobs', col):
            missing_columns.append(col)

    if missing_columns:
        print(f"   [FAIL] Missing columns: {', '.join(missing_columns)}")
        return False

    print(f"   [OK] All {len(required_columns)} required columns present")
    return True


def verify_review_queue_table(client) -> bool:
    """Verify review_queue table has correct schema."""
    print("\n4. Verifying 'review_queue' table...")

    if not check_table_exists(client, 'review_queue'):
        print("   [FAIL] Table 'review_queue' does not exist")
        print("   [INFO] Run migration 002_create_review_queue_table.sql")
        return False
    print("   [OK] Table exists")

    required_columns = [
        'id', 'extraction_id', 'error_type', 'error_message',
        'processing_method', 'quality_score', 'retry_count',
        'resolution', 'reviewer_notes',
        'queued_at', 'reviewed_at'
    ]

    missing_columns = []
    for col in required_columns:
        if not check_column_exists(client, 'review_queue', col):
            missing_columns.append(col)

    if missing_columns:
        print(f"   [FAIL] Missing columns: {', '.join(missing_columns)}")
        return False

    print(f"   [OK] All {len(required_columns)} required columns present")
    return True


def main():
    """Run all verification checks."""
    print("=" * 80)
    print("DATABASE SCHEMA VERIFICATION")
    print("=" * 80)

    try:
        client = get_supabase_client()
        print("[OK] Connected to Supabase")
    except Exception as e:
        print(f"[FAIL] Could not connect to Supabase: {e}")
        print("\nPlease check:")
        print("1. SUPABASE_URL is set in .env")
        print("2. SUPABASE_KEY is set in .env")
        print("3. Supabase project is active")
        return 1

    # Run all verification checks
    checks = [
        verify_extractions_table(client),
        verify_memo_extractions_table(client),
        verify_batch_jobs_table(client),
        verify_review_queue_table(client),
    ]

    print("\n" + "=" * 80)
    if all(checks):
        print("[SUCCESS] All schema checks passed!")
        print("=" * 80)
        print("\nYour database is ready for use.")
        print("\nNext steps:")
        print("1. Run tests: pytest tests/ -v")
        print("2. Test extraction: python -m app.cli batch-process")
        return 0
    else:
        failed_count = len([c for c in checks if not c])
        print(f"[FAILED] {failed_count} schema check(s) failed")
        print("=" * 80)
        print("\nPlease apply missing migrations:")
        print("1. Go to Supabase Dashboard → SQL Editor")
        print("2. Copy and execute migration files in order (001 → 005)")
        print("3. Run this script again to verify")
        return 1


if __name__ == "__main__":
    exit(main())
