# Academy Scrapper Integration Plan (US-020)

**Purpose:** After validation completes in Academy Scrapper, call the PDF-Extraction matcher and store `exam_set_id` in `scraped_files.metadata`.

**PRD reference:** [tasks/prd-paper-matching-reconstruction.md](prd-paper-matching-reconstruction.md) – US-020, "Integrate matching into validation flow"

**Codebase:** Academy Scrapper – `C:\Users\theoc\Desktop\Work\Academy Scrapper`  
**Scope:** 2 files in ValidationAgent

---

## Files to Modify (Academy Scrapper)

| File | Changes |
|------|---------|
| `ValidationAgent/validate_worker.py` | Call exam matching after validation completes |
| `ValidationAgent/supabase_client.py` | Add exam_set_id to scraped_files.metadata |

---

## 1. `ValidationAgent/validate_worker.py`

**Change:** After the validation result is saved (and you have `scraped_file_id` plus validation metadata), call the PDF-Extraction matcher so it can create/update an exam set and return `exam_set_id`.

**Options:**

- **Option A – HTTP call to PDF-Extraction API**
  - Add an endpoint in PDF-Extraction that accepts `scraped_file_id` and validation metadata, runs the existing matching logic, and returns `exam_set_id`.
  - In `validate_worker.py`, after writing to `validation_results`, POST to that URL with the same payload, parse `exam_set_id` from the response, then pass it to the code that updates `scraped_files` (e.g. `supabase_client`).

- **Option B – Call PDF-Extraction as a library**
  - If Academy Scrapper can depend on the PDF-Extraction package (or a shared package that contains the matcher), import and call the same `match_document_to_exam_set(client, scraped_file_id, metadata)` after creating the validation result, then use the returned `exam_set_id` when updating `scraped_files`.

**Concrete steps in `validate_worker.py`:**

1. Right after persisting the row to `validation_results` (you have `scraped_file_id` and the validation fields: subject, grade, year, paper_type, paper_number, session, syllabus).
2. Call the matcher (HTTP or in-process) with:
   - `scraped_file_id`
   - metadata dict: `subject`, `grade`, `year`, `paper_type`, `paper_number`, `session`, `syllabus`.
3. If the matcher returns an `exam_set_id`, pass it to the code that updates `scraped_files` (e.g. `supabase_client.update_scraped_file_metadata(...)` or equivalent).

---

## 2. `ValidationAgent/supabase_client.py` (or equivalent)

**Change:** When updating `scraped_files` after validation (or in a dedicated “post-validation” update), store the matcher’s `exam_set_id` in `scraped_files.metadata`.

- Ensure `metadata` is a JSONB object (or dict) and set e.g. `metadata["exam_set_id"] = str(exam_set_id)` (or merge that key into the existing metadata), then update the `scraped_files` row for that `scraped_file_id`.
- If there is already a function that updates `scraped_files` by ID and a metadata dict, add an optional `exam_set_id` argument and merge it into `metadata` before the update.

---

## 3. PDF-Extraction side (if using HTTP)

- Expose an endpoint that ValidationAgent can call, e.g.  
  `POST /api/exam-sets/match-after-validation`  
  Body: `{ "scraped_file_id": "uuid", "subject": "...", "grade": "...", "year": ..., "paper_type": "...", "paper_number": ..., "session": "...", "syllabus": "..." }`.  
  Handler: load Supabase client, call `match_document_to_exam_set(client, scraped_file_id, body)`, return `{ "exam_set_id": "uuid" }`.
- Ensure Academy Scrapper has the PDF-Extraction base URL (env var or config) and uses it for this POST.

---

## 4. Checklist

- [ ] In `validate_worker.py`: after saving validation result, call matcher (HTTP or in-process) with `scraped_file_id` and validation metadata.
- [ ] In `supabase_client.py` (or equivalent): when updating `scraped_files` after validation, set `metadata["exam_set_id"]` from the matcher response.
- [ ] If using HTTP: add the “match-after-validation” endpoint in PDF-Extraction and configure the URL in Academy Scrapper.

---

## Success criteria (from PRD)

- Matching runs after `validation_results` record is created.
- `exam_set_id` is stored in `scraped_files.metadata` for reference.
- Exam set status is updated based on match result.
- Duplicate detection triggers review queue entry (handled in PDF-Extraction).
