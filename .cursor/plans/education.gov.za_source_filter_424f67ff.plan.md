---
name: Education.gov.za Source Filter
overview: Add optional filtering by source URL (e.g. education.gov.za) to the matched-pairs pipeline (extract, export, download) so that once education.gov.za papers are validated and matched into exam_sets, the same workflow can be run for them. Document the current data gap (0 validation_results for those files) and the prerequisite steps.
todos: []
isProject: false
---

# Same Pipeline for education.gov.za Papers

## Current data

- **scraped_files.source_url** exists; 1,123 rows have `source_url ILIKE '%education.gov.za%'`.
- **None** of those 1,123 have a row in **validation_results** (so they are not validated).
- **exam_sets** are built from validation_results via the batch matcher; so **0** matched pairs currently involve education.gov.za.

So we cannot run “the same” end-to-end (extract → export → download) for education.gov.za **until** those files are validated and then matched. The plan is to add **source-url filtering** to the pipeline so it is ready when that data exists, and to document the prerequisite.

---

## 1. Add `--source-url` to the pipeline

Use a single optional filter: e.g. `--source-url education.gov.za` (substring, case-insensitive). For any exam_set we only keep it if **both** the QP and Memo `scraped_files` have `source_url ILIKE '%' || value || '%'`.

### 1.1 [scripts/extract_matched_pairs.py](scripts/extract_matched_pairs.py)

- Add `--source-url VALUE` (optional).
- After fetching exam_sets (and subject/status/limit), filter: for each exam_set load scraped_files for `question_paper_id` and `memo_id`; keep only rows where both have `source_url ILIKE '%' + value + '%'`. (Reuse the same scraped_files fetch you already do for storage paths; add a check on `source_url`.)
- If no rows remain, exit with “No exam_sets found for source_url=...” (and other filters).

### 1.2 [scripts/export_extractions_md.py](scripts/export_extractions_md.py)

- In **exam-sets mode**, add `--source-url VALUE` (optional).
- After `_fetch_exam_sets`, filter the list: for each exam_set, get scraped_files for `question_paper_id` and `memo_id` (you may already have filenames; add one query or join to get `source_url`), and keep only exam_sets where both URLs match the filter.
- Summary output filename can include the source slug when `--source-url` is set (e.g. `exam-sets-english-matched-education-gov-za-export.md`).

### 1.3 Download script

- **Option A (recommended):** Extend [scripts/download_matched_pairs_pdfs.py](scripts/download_matched_pairs_pdfs.py) to accept optional `--source-url` and optional `--subject`/`--status`/`--limit`. When provided, **query the DB** for exam_sets (with the same filters as export: subject, status, limit, and source_url filter on both scraped_files), then for each pair build stem, gs URL, and download to `output_markdown` (same naming as now). When no args, keep current behaviour (hardcoded list of the English pairs we already use).
- **Option B:** Add a separate script that only does “download by source_url” (query exam_sets + scraped_files, then download). Same behaviour, different file.

Use **Option A** so one script handles both “this list” and “by source_url (and optional subject/status/limit)”.

### 1.4 SOURCE-LINKS.md

- When generating links (e.g. in the download script or a small helper), support a `--source-url` run and write a dedicated `SOURCE-LINKS-education-gov-za.md` (or append a section to SOURCE-LINKS.md) so education.gov.za links are clearly separated.

---

## 2. Document prerequisite and usage

### 2.1 [docs/exam-sets-overview.md](docs/exam-sets-overview.md)

- Add a short subsection **“Papers from education.gov.za”**:
  - Today: 1,123 scraped_files have `source_url` containing `education.gov.za`; **0** have validation_results, so **0** are in exam_sets. So there are no matched pairs from that source yet.
  - To get pairs: run validation (Academy Scrapper / ValidationAgent) for those files so they get validation_results; then run the batch matcher (e.g. `python scripts/run_batch_matcher.py`). Optionally document that a future “match only education.gov.za” option would require changing the matcher to filter by `scraped_files.source_url` when selecting validation_results.
  - Once you have matched pairs from education.gov.za, use the same CLI with `--source-url education.gov.za`:
    - Extract: `python scripts/extract_matched_pairs.py --source-url education.gov.za --status matched --limit 20`
    - Export: `python scripts/export_extractions_md.py --exam-sets --source-url education.gov.za --status matched`
    - Download PDFs: `python scripts/download_matched_pairs_pdfs.py --source-url education.gov.za --status matched`

### 2.2 [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md) or [AGENTS.md](AGENTS.md)

- Mention that `--source-url` is supported for the matched-pairs pipeline and that education.gov.za papers need to be validated and matched before they appear in that pipeline.

---

## 3. Optional: batch matcher filter by source_url

- **Goal:** When validation_results exist for education.gov.za scraped_files, run the batch matcher only on those (so we don’t mix with other sources).
- **Change:** In [app/services/batch_matcher.py](app/services/batch_matcher.py), add an optional parameter `source_url_substring: Optional[str] = None`. When set, after getting validation_results (e.g. by status=correct), for each row get the corresponding scraped_file and keep only rows where `source_url ILIKE '%' || value || '%'`. That may require an extra query per batch (e.g. fetch scraped_files for the scraped_file_ids in the page) or a different list_validation_results that joins scraped_files and filters by source_url (if Supabase supports that). Lower priority; can be a follow-up once validation for education.gov.za is running.

---

## 4. Files to touch (summary)


| File                                                                             | Action                                                                                                                                                                               |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [scripts/extract_matched_pairs.py](scripts/extract_matched_pairs.py)             | Add `--source-url`, filter exam_sets by both QP and Memo scraped_files.source_url                                                                                                    |
| [scripts/export_extractions_md.py](scripts/export_extractions_md.py)             | In exam-sets mode add `--source-url`, filter list by source_url after fetch                                                                                                          |
| [scripts/download_matched_pairs_pdfs.py](scripts/download_matched_pairs_pdfs.py) | Add optional `--source-url`, `--subject`, `--status`, `--limit`; when set, query DB for exam_sets (with source_url filter) and download those PDFs; else keep current hardcoded list |
| [docs/exam-sets-overview.md](docs/exam-sets-overview.md)                         | Add “Papers from education.gov.za” and CLI examples with `--source-url education.gov.za`                                                                                             |
| [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md) or [AGENTS.md](AGENTS.md)       | Note support for `--source-url` and education.gov.za prerequisite                                                                                                                    |


---

## 5. Verification

- With current DB:  
`python scripts/extract_matched_pairs.py --source-url education.gov.za --status matched`  
should report 0 pairs and exit cleanly.
- After (hypothetical) validation + matching for education.gov.za:  
same commands with `--source-url education.gov.za` should list and process only those pairs, and downloaded PDFs + SOURCE-LINKS should be alongside their extracts in `output_markdown`.

