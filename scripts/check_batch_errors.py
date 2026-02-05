#!/usr/bin/env python3
"""Check batch job errors and details."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import get_supabase_client

def main():
    client = get_supabase_client()
    
    # Check updated batch jobs
    jobs = client.table("gemini_batch_jobs").select("*").execute()
    
    print("=" * 70)
    print("GEMINI BATCH JOBS - AFTER POLLING")
    print("=" * 70)
    
    for job in jobs.data:
        print("\n" + "-" * 50)
        print(f"Job ID: {job['id']}")
        print(f"Gemini Name: {job.get('gemini_job_name', 'N/A')}")
        print(f"Status: {job['status']}")
        print(f"Total Requests: {job['total_requests']}")
        print(f"Completed: {job.get('completed_requests', 0)}")
        print(f"Failed: {job.get('failed_requests', 0)}")
        print(f"Error: {job.get('error_message', 'None')}")
        print(f"Result File: {job.get('result_file_name', 'None')}")
        
        metadata = job.get("request_metadata", {})
        if metadata:
            print(f"Metadata keys: {list(metadata.keys()) if isinstance(metadata, dict) else 'N/A'}")
            if isinstance(metadata, dict):
                for k, v in metadata.items():
                    if isinstance(v, list):
                        print(f"  {k}: {len(v)} items")
                    else:
                        print(f"  {k}: {str(v)[:100]}")

if __name__ == "__main__":
    main()
