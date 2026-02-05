# Database Summary – PDF-Extraction Project

**Queried:** Feb 2026 (Supabase public schema + migrations + extensions)

---

## 1. Public Schema – Table Counts (26 tables)

| Table | Count | Notes |
|-------|--------|--------|
| **scraped_files** | 36,017 | Source PDFs; Firebase storage_path, validation_status |
| **validation_results** | 10,554 | Validation outcomes (correct / rejected / review_required) |
| **file_registry** | 2,841 | All validated |
| **extractions** | 70 | All completed; all have scraped_file_id |
| **memo_extractions** | 62 | All completed; all have scraped_file_id |
| **batch_jobs** | 11 | completed: 7, pending: 3, partial: 1 |
| **gemini_batch_jobs** | 2 | Both extraction, both succeeded |
| **extraction_documents** | 2 | OCR pipeline docs |
| **extraction_pages** | 31 | Pages from those docs |
| **validation_jobs** | 0 | Validation job tracking |
| **extraction_jobs** | 0 | Per-file extraction jobs |
| **exam_sets** | 0 | QP+memo pairs |
| **review_queue** | 0 | Manual review queue |
| **document_sections** | 0 | Cover, instructions, etc. |
| **document_versions** | 0 | Duplicate/version tracking |
| **extraction_elements** | 0 | Detected elements |
| **extraction_spatial_links** | 0 | Element links |
| **preprocessed_images** | 0 | Vision OCR cache |
| **layout_maps** | 0 | Layout detection cache |
| **extracted_elements** | 0 | Pass 2 extracted content |
| **question_groups** | 0 | QUESTION 1, 2, etc. |
| **questions** | 0 | Hierarchical questions |
| **question_media** | 0 | Images/diagrams linked to questions |
| **question_options** | 0 | MCQ options |
| **question_answers** | 0 | Answers from memos |
| **parsed_questions** | 0 | Firestore-compatible parsed questions |

---

## 2. scraped_files (36,017 rows)

- **Validation status:** validated: 10,312 | unvalidated: 25,390 | rejected: 264 | review_required: 51
- **Status (workflow):** queued_for_extraction: 10,312 (validated) | pending: 25,677 | completed: 28
- **Document type:** Question Paper: 3,097 | Memorandum: 2,938 | Other: 198 | Study Guide: 10 | Needs Manual Review: 1
- **Storage:** With storage_path: 35,999 | Without: 18
- **Year range:** 2008–2025
- **Validated by year (sample):** 2025: 75, 2024: 418, 2023: 292, 2022: 707, 2021: 333, 2020: 346, 2019: 729, 2018: 589, 2017: 403, 2016: 391, 2015: 283, 2014: 298

---

## 3. validation_results (10,554 rows)

| Status | Count |
|--------|--------|
| correct | 10,239 |
| rejected | 264 |
| review_required | 51 |

---

## 4. Extractions and Memos (linkage)

- **extractions:** 70 total, all status `completed`, **70 with scraped_file_id** (100% linked).
- **memo_extractions:** 62 total, all status `completed`, **62 with scraped_file_id** (100% linked).

---

## 5. Batch and Gemini Jobs

- **batch_jobs:** completed: 7, pending: 3, partial: 1
- **gemini_batch_jobs:** 2 rows, both job_type `extraction`, status `succeeded`

---

## 6. file_registry (2,841 rows)

- validation_status: **validated: 2,841** (all validated)

---

## 7. Top Subjects (scraped_files, validated only)

| Subject | Count |
|---------|--------|
| Mathematics | 1,027 |
| Chemistry | 487 |
| Physics | 450 |
| Biology | 362 |
| History | 312 |
| English Literature | 282 |
| English Language | 250 |
| Further Mathematics | 217 |
| Unknown | 176 |
| English Language and Literature | 141 |
| Geography | 140 |
| IsiZulu | 127 |
| Psychology | 108 |
| Mathematical Literacy | 96 |
| Combined Science | 90 |

---

## 8. Migrations (Supabase)

30 migrations applied, from `create_validation_jobs` through `add_level_column` (includes validation_results, file_registry, RLS, PGMQ wrappers, extraction/memo tables, scraped_files, exam_sets, document_sections/versions, validation→scraped_files link, level column).

---

## 9. Extensions (relevant)

- **pgmq** (schema pgmq) 1.5.1 – message queues (e.g. validation/extraction queues).
- **pgcrypto**, **pg_stat_statements**, **pg_net**, **uuid-ossp**, **pg_graphql**, **supabase_vault**, **plpgsql** – in use.

---

## 10. Coverage vs. Available Content

- Validated question papers (in scraped_files): ~2,829+ (from validated + QP document_type).
- **Extracted:** 70 → ~2.5% of validated QPs.
- Validated memos: ~2,674+ (validated + Memorandum).
- **Memo extracted:** 62 → ~2.3% of validated memos.

---

## 11. Cross-Project Context

- **Academy Scrapper** (C# scraper + Python ValidationAgent + React): populates Firebase Storage and `scraped_files`; writes `validation_results`; uses PGMQ.
- **PDF-Extraction** (this repo): reads paths from `scraped_files`, writes `extractions` and `memo_extractions`; all 70 + 62 are linked to `scraped_files` via `scraped_file_id`.
- **Storage:** Firebase (GCS) only; `scraped_files.storage_path` and `storage_bucket` are the source of truth for PDF locations.
