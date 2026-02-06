-- =============================================================================
-- Manager summary: run these in Supabase SQL Editor to show tables side by side
-- Run each block separately and place result panels side by side (or export CSV)
-- =============================================================================


-- ========== PRESENTATION: TABLES & SCHEMA ==========

-- A) ALL TABLES IN PUBLIC SCHEMA (list for presentation)
SELECT table_name AS "Table"
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;


-- B) FULL SCHEMA – every table and column with type (for presentation/slides)
SELECT
  c.table_name   AS "Table",
  c.column_name  AS "Column",
  c.data_type    AS "Type",
  c.is_nullable  AS "Nullable"
FROM information_schema.columns c
WHERE c.table_schema = 'public'
ORDER BY c.table_name, c.ordinal_position;


-- C) KEY TABLES ONLY – schema for extraction/matching story (cleaner for slides)
SELECT
  c.table_name   AS "Table",
  c.column_name  AS "Column",
  c.data_type    AS "Type",
  c.is_nullable  AS "Nullable"
FROM information_schema.columns c
WHERE c.table_schema = 'public'
  AND c.table_name IN (
    'scraped_files', 'extractions', 'memo_extractions', 'exam_sets',
    'validation_results', 'document_versions', 'batch_jobs', 'gemini_batch_jobs'
  )
ORDER BY c.table_name, c.ordinal_position;


-- D) VALIDATION, EXTRACTION & LINKING – schema (pipeline tables only)
--    Use this to show how validation → extraction → linking tables relate.
--    Relationships: scraped_files.id = validation_results.scraped_file_id;
--                   scraped_files.id = extractions.scraped_file_id = memo_extractions.scraped_file_id;
--                   exam_sets.question_paper_id / exam_sets.memo_id → scraped_files.id
SELECT
  c.table_name   AS "Table",
  c.column_name  AS "Column",
  c.data_type    AS "Type",
  c.is_nullable  AS "Nullable"
FROM information_schema.columns c
WHERE c.table_schema = 'public'
  AND c.table_name IN (
    'scraped_files',
    'validation_results',
    'extractions',
    'memo_extractions',
    'exam_sets',
    'document_versions'
  )
ORDER BY
  CASE c.table_name
    WHEN 'scraped_files'       THEN 1
    WHEN 'validation_results' THEN 2
    WHEN 'extractions'         THEN 3
    WHEN 'memo_extractions'    THEN 4
    WHEN 'exam_sets'           THEN 5
    WHEN 'document_versions'   THEN 6
    ELSE 7
  END,
  c.ordinal_position;


-- ========== COUNTS & BREAKDOWNS ==========

-- 1) TABLE TOTALS (overview)
SELECT 'scraped_files'     AS "Table", COUNT(*) AS "Total" FROM scraped_files
UNION ALL
SELECT 'extractions',       COUNT(*) FROM extractions
UNION ALL
SELECT 'memo_extractions',  COUNT(*) FROM memo_extractions
UNION ALL
SELECT 'exam_sets',         COUNT(*) FROM exam_sets
UNION ALL
SELECT 'exam_sets (matched)', COUNT(*) FROM exam_sets WHERE status = 'matched'
ORDER BY "Table";


-- 2) EXTRACTIONS (question papers) – by status
SELECT status AS "Status", COUNT(*) AS "Count"
FROM extractions
GROUP BY status
ORDER BY "Count" DESC;


-- 3) EXTRACTIONS – by subject (top 15)
SELECT subject AS "Subject", COUNT(*) AS "Count"
FROM extractions
GROUP BY subject
ORDER BY "Count" DESC
LIMIT 15;


-- 4) MEMO_EXTRACTIONS – by status
SELECT status AS "Status", COUNT(*) AS "Count"
FROM memo_extractions
GROUP BY status
ORDER BY "Count" DESC;


-- 5) MEMO_EXTRACTIONS – by subject (top 15)
SELECT subject AS "Subject", COUNT(*) AS "Count"
FROM memo_extractions
GROUP BY subject
ORDER BY "Count" DESC
LIMIT 15;


-- 6) EXAM_SETS (matched papers) – by status
SELECT status AS "Status", COUNT(*) AS "Count"
FROM exam_sets
GROUP BY status
ORDER BY "Count" DESC;


-- 7) SAMPLE MATCHED PAIRS (scraped_files only) – 10 rows
SELECT
  es.id AS exam_set_id,
  es.status,
  es.matched_at,
  qp.subject   AS qp_subject,
  qp.grade     AS qp_grade,
  qp.year      AS qp_year,
  qp.file_name AS qp_file_name,
  mm.subject   AS memo_subject,
  mm.file_name AS memo_file_name
FROM exam_sets es
JOIN scraped_files qp ON qp.id = es.question_paper_id
JOIN scraped_files mm ON mm.id = es.memo_id
WHERE es.status = 'matched'
ORDER BY es.matched_at DESC NULLS LAST
LIMIT 10;


-- 8) EXTRACTIONS + MEMO_EXTRACTIONS LINKED (QP and Memo tables side by side)
--    One row per exam_set: extraction (QP) columns left, memo_extraction columns right
SELECT
  es.id              AS exam_set_id,
  es.status          AS exam_set_status,
  es.matched_at,
  -- QP extraction (left)
  e.id               AS qp_extraction_id,
  e.file_name        AS qp_file_name,
  e.subject          AS qp_subject,
  e.grade            AS qp_grade,
  e.year             AS qp_year,
  e.session          AS qp_session,
  e.status           AS qp_status,
  e.scraped_file_id  AS qp_scraped_file_id,
  -- Memo extraction (right)
  m.id               AS memo_extraction_id,
  m.file_name        AS memo_file_name,
  m.subject          AS memo_subject,
  m.grade            AS memo_grade,
  m.year             AS memo_year,
  m.session          AS memo_session,
  m.status           AS memo_status,
  m.scraped_file_id  AS memo_scraped_file_id
FROM exam_sets es
JOIN extractions e       ON e.scraped_file_id = es.question_paper_id
JOIN memo_extractions m ON m.scraped_file_id = es.memo_id
WHERE es.question_paper_id IS NOT NULL AND es.memo_id IS NOT NULL
ORDER BY es.matched_at DESC NULLS LAST, es.id
LIMIT 100;


-- 8b) Same as 8 but only fully MATCHED pairs (optional, smaller result)
-- SELECT
--   es.id AS exam_set_id, es.status, es.matched_at,
--   e.id AS qp_extraction_id,  e.file_name AS qp_file_name,  e.subject AS qp_subject,  e.grade AS qp_grade,  e.year AS qp_year,  e.status AS qp_status,
--   m.id AS memo_extraction_id, m.file_name AS memo_file_name, m.subject AS memo_subject, m.grade AS memo_grade, m.year AS memo_year, m.status AS memo_status
-- FROM exam_sets es
-- JOIN extractions e       ON e.scraped_file_id = es.question_paper_id
-- JOIN memo_extractions m ON m.scraped_file_id = es.memo_id
-- WHERE es.status = 'matched'
-- ORDER BY es.matched_at DESC NULLS LAST
-- LIMIT 100;


-- 9) MATCHED PAIRS WITH FULL JSON (see the extraction content)
--    Returns multiple rows: QP + memo file names and the JSON columns (groups, tables, sections).
--    Change LIMIT to see more/fewer pairs. Click into json cells in Supabase to expand.
--    (To see many pairs without JSON, use query 8 instead.)
SELECT
  es.id              AS exam_set_id,
  e.file_name        AS qp_file_name,
  m.file_name        AS memo_file_name,
  e.groups           AS qp_groups_json,
  e.tables           AS qp_tables_json,
  m.sections         AS memo_sections_json
FROM exam_sets es
JOIN extractions e       ON e.scraped_file_id = es.question_paper_id
JOIN memo_extractions m ON m.scraped_file_id = es.memo_id
WHERE es.question_paper_id IS NOT NULL AND es.memo_id IS NOT NULL
ORDER BY es.matched_at DESC NULLS LAST, es.id
LIMIT 20;


-- 10) EDUCATION.GOV.ZA – counts (optional)
SELECT
  (SELECT COUNT(*) FROM extractions e
   JOIN scraped_files sf ON sf.id = e.scraped_file_id
   WHERE sf.source_url ILIKE '%education.gov.za%') AS qp_extractions,
  (SELECT COUNT(*) FROM memo_extractions m
   JOIN scraped_files sf ON sf.id = m.scraped_file_id
   WHERE sf.source_url ILIKE '%education.gov.za%') AS memo_extractions,
  (SELECT COUNT(*) FROM exam_sets es
   JOIN scraped_files qp ON qp.id = es.question_paper_id
   JOIN scraped_files mm ON mm.id = es.memo_id
   WHERE qp.source_url ILIKE '%education.gov.za%'
     AND mm.source_url ILIKE '%education.gov.za%')   AS exam_sets_both_education_gov_za;


-- 11) MATCHED_PAPER_QUESTIONS – flat table (one row per question for matched pairs)
--    Count and sample. To refresh this table after new extractions/matches:
--    1) TRUNCATE matched_paper_questions;
--    2) Run the INSERT from migrations/022_create_matched_paper_questions_table.sql
SELECT COUNT(*) AS "matched_paper_questions total" FROM matched_paper_questions;

-- 11b) Sample rows from matched_paper_questions (one exam_set)
-- SELECT exam_set_id, subject, year, question_id, LEFT(question_text, 60) AS question_text, marks,
--        marker_instruction IS NOT NULL AS has_memo
-- FROM matched_paper_questions
-- WHERE exam_set_id = (SELECT id FROM exam_sets WHERE status = 'matched' LIMIT 1)
-- ORDER BY group_id, question_id
-- LIMIT 20;


-- 12) ALL QUESTIONS FROM ALL EXTRACTED QPs (same shape as single-exam-set query, for every extraction)
--     scraped_file_id and file_name identify which paper each row belongs to.
--     Optional: add WHERE scraped_file_id IN (SELECT question_paper_id FROM exam_sets WHERE status = 'matched' AND question_paper_id IS NOT NULL) to restrict to matched pairs only.
SELECT
  scraped_file_id,
  file_name,
  question_id,
  parent_id,
  group_id,
  group_title,
  question_text,
  marks,
  scenario,
  context,
  options,
  match_data,
  guide_table
FROM v_questions
ORDER BY scraped_file_id, group_id, question_id;


-- =============================================================================
-- To export full extraction JSON to files you can open (e.g. in VS Code), run:
--   python scripts/export_matched_pair_json.py <exam_set_id>
--   python scripts/export_matched_pair_json.py --qp <extraction_id>
--   python scripts/export_matched_pair_json.py --list 5   (list 5 matched pairs)
-- =============================================================================
