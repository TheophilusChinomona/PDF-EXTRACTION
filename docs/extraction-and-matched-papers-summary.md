# Extraction & Matched Papers – Summary for Managers

**Last updated:** 2026-02-06

## What we have so far (overview)

| Table | What it holds | Current total |
|-------|----------------|---------------|
| **scraped_files** | Source PDFs (from scraping) | 36,017 |
| **extractions** | Structured question papers (QP) we’ve extracted | **299** |
| **memo_extractions** | Structured marking guidelines (memos) we’ve extracted | **225** |
| **exam_sets** | Linked QP–Memo pairs (matched papers) | **3,658** |
| **exam_sets (fully matched)** | Pairs where both QP and Memo are linked | **435** |
| **matched_paper_questions** | Flat table: one row per question for matched pairs (QP + memo columns) | See refresh below |

- **Extractions** = parsed, machine-readable content from each QP PDF.
- **Memo extractions** = same for each memo PDF.
- **Exam sets** = which QP and which memo belong to the same exam (subject, grade, year, paper).  
  **Matched** = both sides linked; **incomplete** = only QP or only memo; **duplicate_review** = multiple versions to review.

### Validation, extraction & linking — relationships and schema

Pipeline: **scraped_files** (source) → **validation_results** (validation) → **extractions** / **memo_extractions** (extraction) → **exam_sets** (linking) → **document_versions** (duplicates). Full ERD, table list, and column schema are in **`docs/exam-sets-overview.md`** (section **3b**). To get the schema for these six tables in one query, run **query D** in `scripts/manager_summary_queries.sql` in the Supabase SQL Editor.

---

## Extractions (question papers)

| Metric | Value |
|--------|--------|
| Total | 299 |
| Status | All **completed** |
| Top subjects (by count) | Geskiedenis, IsiXhosa (various), History, Hospitality, IT, English Literature, Further Maths, etc. |

---

## Memo extractions (marking guidelines)

| Metric | Value |
|--------|--------|
| Total | 225 |
| Status | All **completed** |
| Top subjects | Geskiedenis, Further Mathematics, IsiXhosa (various), History, English Language and Literature, etc. |

---

## Exam sets (matched papers)

| Status | Count | Meaning |
|--------|-------|---------|
| **matched** | 435 | Full pair: QP + Memo linked |
| **incomplete** | 2,042 | Only QP or only Memo linked so far |
| **duplicate_review** | 1,181 | Multiple versions of QP or Memo to review |
| **Total** | 3,658 | All exam_set rows |

---

## Education.gov.za (recent pipeline)

| Metric | Count |
|--------|--------|
| QP extractions (source = education.gov.za) | 37 |
| Memo extractions (source = education.gov.za) | 5 |
| Exam sets where *both* QP and Memo are from education.gov.za | 0 |

*(More memos need to be extracted and matched to get full pairs from this source.)*

---

## matched_paper_questions (flat table for matched pairs)

**matched_paper_questions** is a single table with one row per question for every matched exam set. Each row includes both question-paper columns (question_id, question_text, marks, options, etc.) and memo columns (marker_instruction, model_answers, memo_structured_answer, etc.) when the memo has a matching question_id.

- **Source:** Built from **exam_sets** + **extractions.groups** + **memo_extractions.sections** (only pairs where both QP and memo extractions exist and status = completed).
- **Refresh:** After new extractions or new matches, re-run the population so the table stays in sync. In Supabase SQL Editor:
  1. `TRUNCATE matched_paper_questions;`
  2. Run the `INSERT INTO matched_paper_questions SELECT ...` from `migrations/022_create_matched_paper_questions_table.sql` (the full INSERT with `ON CONFLICT (exam_set_id, group_id, question_id) DO NOTHING`).
- Alternatively, a Python script `scripts/populate_matched_paper_questions.py` can be added later to refresh from the app.

---

## How to show the tables side by side

1. **In Supabase (SQL Editor)**  
   Run the queries in `scripts/manager_summary_queries.sql` (see below).  
   Each query returns one result set; run them one by one and place the result panels side by side, or export to CSV/Excel.

2. **From the repo (terminal)**  
   Run:
   ```bash
   python scripts/manager_summary_queries.py
   ```
   This prints the same summary and table counts in a readable format for a meeting or screenshot.

---

## One-line takeaway

We have **299 extracted question papers** and **225 extracted memos**; **435** of these are linked as full QP–Memo pairs in **exam_sets** (matched papers). The rest are either single-sided (incomplete) or in duplicate_review.
