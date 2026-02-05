#!/usr/bin/env python3
"""
Debug file upload to see what URI format we get.
"""

import os
import sys
import asyncio
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.gemini_client import get_gemini_client


async def main():
    gemini = get_gemini_client()
    
    # Create a small test PDF
    test_pdf = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n193\n%%EOF"
    
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(test_pdf)
        path = f.name
    
    try:
        uploaded = await asyncio.to_thread(gemini.files.upload, file=path)
        
        print("Uploaded file object:")
        print(f"  Type: {type(uploaded)}")
        print(f"  Attributes: {[a for a in dir(uploaded) if not a.startswith('_')]}")
        print()
        
        # Check various attributes
        name = getattr(uploaded, "name", None)
        print(f"  name: {name}")
        
        uri = getattr(uploaded, "uri", None)
        print(f"  uri: {uri}")
        
        # Try to get dict representation
        if hasattr(uploaded, "model_dump"):
            dump = uploaded.model_dump()
            print(f"\n  model_dump keys: {list(dump.keys())}")
            for k, v in dump.items():
                print(f"    {k}: {v}")
        
        # Cleanup - delete the uploaded file
        try:
            await asyncio.to_thread(gemini.files.delete, name=name)
            print(f"\n  Deleted test file: {name}")
        except Exception as e:
            print(f"\n  Could not delete test file: {e}")
            
    finally:
        os.unlink(path)


if __name__ == "__main__":
    asyncio.run(main())
