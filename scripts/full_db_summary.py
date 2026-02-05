#!/usr/bin/env python3
"""
Full database summary - query all tables in Supabase.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import get_supabase_client


def get_table_summary(client, table_name: str, select_cols: str = "*", sample_limit: int = 3):
    """Get count and sample from a table."""
    try:
        # Get count
        count_result = client.table(table_name).select("*", count="exact", head=True).execute()
        count = count_result.count if count_result.count is not None else 0
        
        # Get sample rows (try with created_at ordering, fall back to no ordering)
        try:
            sample = client.table(table_name).select(select_cols).order("created_at", desc=True).limit(sample_limit).execute()
        except:
            sample = client.table(table_name).select(select_cols).limit(sample_limit).execute()
        
        # Get columns from sample
        columns = list(sample.data[0].keys()) if sample.data else []
        
        return {"count": count, "sample": sample.data, "columns": columns, "error": None}
    except Exception as e:
        return {"count": 0, "sample": [], "columns": [], "error": str(e)}


def main():
    client = get_supabase_client()
    
    print("=" * 80)
    print("FULL SUPABASE DATABASE SUMMARY")
    print(f"Queried at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Define all tables to query (use * to discover schema)
    tables = [
        ("scraped_files", "*"),
        ("validation_results", "*"),
        ("validation_jobs", "*"),
        ("extraction_jobs", "*"),
        ("extractions", "*"),
        ("memo_extractions", "*"),
        ("gemini_batch_jobs", "*"),
        ("exam_sets", "*"),
        ("document_sections", "*"),
        ("document_versions", "*"),
        ("batch_jobs", "*"),
        ("review_queue", "*"),
        ("parser_jobs", "*"),
    ]
    
    for table_name, select_cols in tables:
        result = get_table_summary(client, table_name, select_cols)
        
        print(f"\n{'='*80}")
        print(f"TABLE: {table_name}")
        print(f"{'='*80}")
        
        if result["error"]:
            print(f"  ERROR: {result['error']}")
            continue
        
        print(f"  Total Records: {result['count']:,}")
        
        if result.get("columns"):
            print(f"  Columns: {', '.join(result['columns'][:15])}")
            if len(result['columns']) > 15:
                print(f"           ... and {len(result['columns']) - 15} more")
        
        if result["count"] == 0:
            print("  (empty table)")
            continue
        
        # Show sample data (limited fields for readability)
        print(f"\n  Sample Records (most recent {len(result['sample'])}):")
        print("-" * 70)
        
        # Key fields to show (varies by table)
        key_fields = ["id", "file_name", "filename", "status", "subject", "grade", "year", 
                      "session", "language", "job_type", "total_requests", "created_at",
                      "scraped_file_id", "confidence_score", "paper_type", "gemini_job_name"]
        
        for i, row in enumerate(result["sample"], 1):
            print(f"\n  [{i}]")
            shown = 0
            for key, value in row.items():
                # Only show key fields and limit to 10 per record
                if key not in key_fields and shown >= 10:
                    continue
                if value is None or (isinstance(value, (list, dict)) and not value):
                    continue
                # Truncate long values and handle encoding
                str_val = str(value)
                if len(str_val) > 60:
                    str_val = str_val[:57] + "..."
                # Replace non-ASCII characters for Windows console
                str_val = str_val.encode('ascii', 'replace').decode('ascii')
                print(f"      {key}: {str_val}")
                shown += 1
    
    # Additional stats
    print("\n" + "=" * 80)
    print("AGGREGATE STATISTICS")
    print("=" * 80)
    
    # Extractions by subject
    try:
        extractions = client.table("extractions").select("subject, language, grade").execute()
        if extractions.data:
            subjects = {}
            languages = {}
            grades = {}
            for ext in extractions.data:
                subj = ext.get("subject", "Unknown") or "Unknown"
                lang = ext.get("language", "Unknown") or "Unknown"
                grade = ext.get("grade", "Unknown") or "Unknown"
                subjects[subj] = subjects.get(subj, 0) + 1
                languages[lang] = languages.get(lang, 0) + 1
                grades[grade] = grades.get(grade, 0) + 1
            
            print("\n  Extractions by Subject (top 10):")
            for subj, cnt in sorted(subjects.items(), key=lambda x: -x[1])[:10]:
                subj_safe = subj[:50].encode('ascii', 'replace').decode('ascii')
                print(f"    {subj_safe}: {cnt}")
            
            print("\n  Extractions by Language:")
            for lang, cnt in sorted(languages.items(), key=lambda x: -x[1]):
                print(f"    {lang}: {cnt}")
            
            print("\n  Extractions by Grade:")
            for grade, cnt in sorted(grades.items(), key=lambda x: -x[1]):
                print(f"    Grade {grade}: {cnt}")
    except Exception as e:
        print(f"  Error getting extraction stats: {e}")
    
    # Memo extractions by subject
    try:
        memos = client.table("memo_extractions").select("subject, language, grade").execute()
        if memos.data:
            subjects = {}
            for memo in memos.data:
                subj = memo.get("subject", "Unknown") or "Unknown"
                subjects[subj] = subjects.get(subj, 0) + 1
            
            print("\n  Memo Extractions by Subject (top 10):")
            for subj, cnt in sorted(subjects.items(), key=lambda x: -x[1])[:10]:
                subj_safe = subj[:50].encode('ascii', 'replace').decode('ascii')
                print(f"    {subj_safe}: {cnt}")
    except Exception as e:
        print(f"  Error getting memo stats: {e}")
    
    # Scraped files by file_type
    try:
        scraped = client.table("scraped_files").select("file_type").limit(1000).execute()
        if scraped.data:
            file_types = {}
            for sf in scraped.data:
                ft = sf.get("file_type", "Unknown") or "Unknown"
                file_types[ft] = file_types.get(ft, 0) + 1
            
            print("\n  Scraped Files by Type (sample of 1000):")
            for ft, cnt in sorted(file_types.items(), key=lambda x: -x[1]):
                print(f"    {ft}: {cnt}")
    except Exception as e:
        print(f"  Error getting scraped file stats: {e}")
    
    print("\n" + "=" * 80)
    print("Summary complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
