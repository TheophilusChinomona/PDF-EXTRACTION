## Plan: Thread `scraped_files.id` Through Extraction Pipeline

- [x] 1. Create SQL migration `migrations/008_add_scraped_file_id.sql`
- [x] 2. Update `app/routers/batch.py` — Add `source_ids` form field, pair with files
- [x] 3. Update `app/db/extractions.py` — Include `scraped_file_id` in insert record
- [x] 4. Update `app/db/memo_extractions.py` — Include `scraped_file_id` in insert record
- [x] 5. Update `scripts/test_batch_10.py` — Pass `source_ids` in batch request
- [x] 6. Update `scripts/export_extractions_md.py` — Use `scraped_file_id` for naming

## Changes Made

### Files Created
- `migrations/008_add_scraped_file_id.sql` — Adds `scraped_file_id UUID` column + index to both `extractions` and `memo_extractions`

### Files Modified
- `app/routers/batch.py` — New `source_ids` Form field (JSON array), parsed/validated, threaded into `file_info` per file
- `app/db/extractions.py` — Includes `scraped_file_id` in insert record when present in `file_info`
- `app/db/memo_extractions.py` — Same as above for memo table
- `scripts/test_batch_10.py` — Collects `id` from `scraped_files` rows, passes as `source_ids` JSON in batch POST
- `scripts/export_extractions_md.py` — Uses `scraped_file_id` (when available) instead of extraction UUID for canonical filenames
