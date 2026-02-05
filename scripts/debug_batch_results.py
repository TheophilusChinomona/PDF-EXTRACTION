#!/usr/bin/env python3
"""
Debug batch job results - fetch raw data from Gemini API.
"""

import os
import sys
import asyncio
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import get_supabase_client
from app.services.gemini_client import get_gemini_client


async def main():
    client = get_supabase_client()
    gemini = get_gemini_client()
    
    # Get batch jobs
    jobs = client.table("gemini_batch_jobs").select("*").execute()
    
    for job in jobs.data:
        print("=" * 70)
        print(f"Job: {job['id']}")
        print(f"Gemini Name: {job['gemini_job_name']}")
        print(f"DB Status: {job['status']}")
        print("-" * 50)
        
        # Fetch from Gemini API
        try:
            batch_job = await asyncio.to_thread(
                gemini.batches.get, 
                name=job['gemini_job_name']
            )
            
            # Check state
            state = getattr(batch_job, "state", None)
            if state is not None and hasattr(state, "name"):
                state_str = state.name
            else:
                state_str = str(state)
            
            print(f"Gemini State: {state_str}")
            
            # Check error
            err = getattr(batch_job, "error", None)
            if err:
                print(f"Gemini Error: {err}")
            
            # Check dest (results)
            dest = getattr(batch_job, "dest", None)
            if dest:
                print(f"Dest type: {type(dest)}")
                print(f"Dest attributes: {[a for a in dir(dest) if not a.startswith('_')]}")
                
                # Check inlined_responses
                inlined = getattr(dest, "inlined_responses", None)
                if inlined:
                    print(f"Inlined responses count: {len(inlined)}")
                    
                    # Check first few
                    for i, resp in enumerate(inlined[:3]):
                        print(f"\n  Response {i}:")
                        resp_err = getattr(resp, "error", None)
                        if resp_err:
                            print(f"    Error: {resp_err}")
                        
                        r = getattr(resp, "response", None)
                        if r:
                            print(f"    Response type: {type(r)}")
                            text = getattr(r, "text", None)
                            if text:
                                print(f"    Text preview: {text[:200]}...")
                            else:
                                # Try candidates
                                candidates = getattr(r, "candidates", None)
                                if candidates:
                                    print(f"    Candidates: {len(candidates)}")
                                    if candidates:
                                        c = candidates[0]
                                        content = getattr(c, "content", None)
                                        if content:
                                            parts = getattr(content, "parts", None)
                                            if parts:
                                                print(f"    Parts: {len(parts)}")
                                                for p in parts[:2]:
                                                    pt = getattr(p, "text", None)
                                                    if pt:
                                                        print(f"      Text preview: {pt[:100]}...")
                                else:
                                    print(f"    Response attrs: {[a for a in dir(r) if not a.startswith('_')]}")
                        else:
                            print(f"    No response, attrs: {[a for a in dir(resp) if not a.startswith('_')]}")
                else:
                    print("No inlined responses")
                
                # Check file_name
                file_name = getattr(dest, "file_name", None)
                if file_name:
                    print(f"Result file: {file_name}")
                    
                    # Download and check
                    try:
                        content = await asyncio.to_thread(gemini.files.download, file=file_name)
                        if isinstance(content, bytes):
                            content = content.decode("utf-8")
                        lines = content.splitlines()
                        print(f"File has {len(lines)} lines")
                        
                        # Parse first few
                        for i, line in enumerate(lines[:3]):
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                parsed = json.loads(line)
                                print(f"\n  Line {i}:")
                                print(f"    Key: {parsed.get('key')}")
                                if "error" in parsed:
                                    print(f"    Error: {parsed['error']}")
                                resp = parsed.get("response", {})
                                if resp and "candidates" in resp and resp["candidates"]:
                                    parts = resp["candidates"][0].get("content", {}).get("parts", [])
                                    if parts and "text" in parts[0]:
                                        print(f"    Text preview: {parts[0]['text'][:100]}...")
                                else:
                                    print(f"    Response keys: {list(resp.keys()) if resp else 'None'}")
                            except json.JSONDecodeError as e:
                                print(f"  Line {i}: JSON error: {e}")
                    except Exception as e:
                        print(f"Failed to download file: {e}")
            else:
                print("No dest/results")
            
            # Check all attributes
            print(f"\nBatch job attributes: {[a for a in dir(batch_job) if not a.startswith('_')]}")
            
        except Exception as e:
            print(f"Error fetching from Gemini: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
