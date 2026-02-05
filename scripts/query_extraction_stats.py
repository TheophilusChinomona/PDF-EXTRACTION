#!/usr/bin/env python3
"""
Query Supabase for comprehensive validation and extraction statistics.
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import get_supabase_client


def main() -> None:
    client = get_supabase_client()
    
    print("=" * 70)
    print("EXTRACTION AGENT DATABASE STATUS")
    print(f"Queried at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # =========================================================================
    # VALIDATION RESULTS
    # =========================================================================
    print("\n[VALIDATION RESULTS]")
    print("-" * 50)
    
    for status in ['correct', 'rejected', 'review_required', 'pending', 'error']:
        result = (
            client.table("validation_results")
            .select("scraped_file_id", count="exact", head=True)
            .eq("status", status)
            .execute()
        )
        count = result.count if result.count is not None else 0
        print(f"  {status:20s}: {count:,}")
    
    # Total validation results
    total_val = (
        client.table("validation_results")
        .select("scraped_file_id", count="exact", head=True)
        .execute()
    )
    print(f"  {'TOTAL':20s}: {total_val.count if total_val.count else 0:,}")
    
    # =========================================================================
    # VALIDATION JOBS
    # =========================================================================
    print("\n[VALIDATION JOBS]")
    print("-" * 50)
    
    val_jobs = (
        client.table("validation_jobs")
        .select("*")
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )
    
    if val_jobs.data:
        for job in val_jobs.data:
            print(f"  Job {job['id'][:8]}...")
            print(f"    Status: {job['status']}")
            print(f"    Total: {job.get('total_files', 0):,}, Processed: {job.get('processed_files', 0):,}")
            print(f"    Accepted: {job.get('accepted_files', 0):,}, Rejected: {job.get('rejected_files', 0):,}")
            print(f"    Review Required: {job.get('review_required_files', 0):,}, Failed: {job.get('failed_files', 0):,}")
            print()
    else:
        print("  No validation jobs found")
    
    # =========================================================================
    # EXTRACTION JOBS
    # =========================================================================
    print("\n[EXTRACTION JOBS]")
    print("-" * 50)
    
    for status in ['pending', 'running', 'completed', 'failed']:
        result = (
            client.table("extraction_jobs")
            .select("id", count="exact", head=True)
            .eq("status", status)
            .execute()
        )
        count = result.count if result.count is not None else 0
        print(f"  {status:20s}: {count:,}")
    
    total_ext_jobs = (
        client.table("extraction_jobs")
        .select("id", count="exact", head=True)
        .execute()
    )
    print(f"  {'TOTAL':20s}: {total_ext_jobs.count if total_ext_jobs.count else 0:,}")
    
    # =========================================================================
    # EXTRACTIONS TABLE (actual extracted data)
    # =========================================================================
    print("\n[EXTRACTIONS - Extracted Documents]")
    print("-" * 50)
    
    for status in ['pending', 'completed', 'failed', 'partial']:
        result = (
            client.table("extractions")
            .select("id", count="exact", head=True)
            .eq("status", status)
            .execute()
        )
        count = result.count if result.count is not None else 0
        print(f"  {status:20s}: {count:,}")
    
    total_extractions = (
        client.table("extractions")
        .select("id", count="exact", head=True)
        .execute()
    )
    print(f"  {'TOTAL':20s}: {total_extractions.count if total_extractions.count else 0:,}")
    
    # =========================================================================
    # MEMO EXTRACTIONS
    # =========================================================================
    print("\n[MEMO EXTRACTIONS]")
    print("-" * 50)
    
    try:
        memo_extractions = (
            client.table("memo_extractions")
            .select("id", count="exact", head=True)
            .execute()
        )
        print(f"  Total memo extractions: {memo_extractions.count if memo_extractions.count else 0:,}")
    except Exception as e:
        print(f"  Could not query memo_extractions: {e}")
    
    # =========================================================================
    # GEMINI BATCH JOBS
    # =========================================================================
    print("\n[GEMINI BATCH JOBS]")
    print("-" * 50)
    
    try:
        for job_type in ['validation', 'extraction']:
            for status in ['pending', 'running', 'succeeded', 'failed']:
                result = (
                    client.table("gemini_batch_jobs")
                    .select("id", count="exact", head=True)
                    .eq("job_type", job_type)
                    .eq("status", status)
                    .execute()
                )
                count = result.count if result.count is not None else 0
                if count > 0:
                    print(f"  {job_type:12s} - {status:12s}: {count:,}")
        
        # Recent batch jobs
        recent_jobs = (
            client.table("gemini_batch_jobs")
            .select("id, gemini_job_name, job_type, status, total_requests, completed_requests, failed_requests, submitted_at, completed_at")
            .order("submitted_at", desc=True)
            .limit(5)
            .execute()
        )
        
        if recent_jobs.data:
            print("\n  Recent Batch Jobs:")
            for job in recent_jobs.data:
                print(f"    [{job['job_type']}] {job['status']}: {job.get('completed_requests', 0)}/{job.get('total_requests', 0)} requests")
                print(f"       Name: {job.get('gemini_job_name', 'N/A')[:40]}...")
    except Exception as e:
        print(f"  Could not query gemini_batch_jobs: {e}")
    
    # =========================================================================
    # SCRAPED FILES (source files)
    # =========================================================================
    print("\n[SCRAPED FILES - Source]")
    print("-" * 50)
    
    try:
        scraped_total = (
            client.table("scraped_files")
            .select("id", count="exact", head=True)
            .execute()
        )
        print(f"  Total scraped files: {scraped_total.count if scraped_total.count else 0:,}")
    except Exception as e:
        print(f"  Could not query scraped_files: {e}")
    
    # =========================================================================
    # EXAM SETS
    # =========================================================================
    print("\n[EXAM SETS]")
    print("-" * 50)
    
    try:
        exam_sets = (
            client.table("exam_sets")
            .select("id", count="exact", head=True)
            .execute()
        )
        print(f"  Total exam sets: {exam_sets.count if exam_sets.count else 0:,}")
    except Exception as e:
        print(f"  Could not query exam_sets: {e}")
    
    print("\n" + "=" * 70)
    print("Query complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
