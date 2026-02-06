# Sample extraction JSON (one QP)

**one_extraction_qp.json** – One full row from the `extractions` table (same structure as in Supabase), including the `groups` array used to build the flat question table.

Use this file to build or test “the table for ONE json” (one row per question from this extraction’s `groups`).

Regenerate with:
```bash
python scripts/save_one_extraction_json.py
```
Optional: `python scripts/save_one_extraction_json.py --out path/to/other.json`
