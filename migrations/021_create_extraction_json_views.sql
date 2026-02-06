-- Migration: 021_create_extraction_json_views.sql
-- Description: Create flat SQL views over extractions.groups and memo_extractions.sections JSONB
-- So JSON can be queried as relational tables without moving data.

-- 1. v_questions: one row per question from extractions.groups[*].questions[*]
CREATE OR REPLACE VIEW v_questions AS
SELECT
  e.id AS extraction_id,
  e.scraped_file_id,
  e.file_name,
  e.subject,
  e.syllabus,
  e.year,
  e.session,
  e.grade,
  e.language,
  e.total_marks,
  g.value->>'group_id' AS group_id,
  g.value->>'title' AS group_title,
  g.value->>'instructions' AS group_instructions,
  q.value->>'id' AS question_id,
  q.value->>'parent_id' AS parent_id,
  q.value->>'text' AS question_text,
  (q.value->>'marks')::integer AS marks,
  q.value->>'scenario' AS scenario,
  q.value->>'context' AS context,
  CASE WHEN jsonb_typeof(q.value->'options') = 'array' THEN q.value->'options' ELSE NULL END AS options,
  CASE WHEN jsonb_typeof(q.value->'match_data') = 'object' THEN q.value->'match_data' ELSE NULL END AS match_data,
  CASE WHEN jsonb_typeof(q.value->'guide_table') = 'array' THEN q.value->'guide_table' ELSE NULL END AS guide_table
FROM extractions e,
  jsonb_array_elements(e.groups) AS g(value),
  jsonb_array_elements(g.value->'questions') AS q(value)
WHERE e.status = 'completed';

COMMENT ON VIEW v_questions IS 'Flat view of questions from extractions.groups JSONB; one row per question.';

-- 2. v_question_options: one row per MCQ option (A, B, C, D)
CREATE OR REPLACE VIEW v_question_options AS
SELECT
  e.id AS extraction_id,
  e.scraped_file_id,
  e.file_name,
  e.subject,
  e.year,
  e.session,
  e.grade,
  g.value->>'group_id' AS group_id,
  q.value->>'id' AS question_id,
  q.value->>'text' AS question_text,
  (q.value->>'marks')::integer AS marks,
  opt.value->>'label' AS option_label,
  opt.value->>'text' AS option_text
FROM extractions e,
  jsonb_array_elements(e.groups) AS g(value),
  jsonb_array_elements(g.value->'questions') AS q(value),
  jsonb_array_elements(CASE WHEN jsonb_typeof(q.value->'options') = 'array' THEN q.value->'options' ELSE '[]'::jsonb END) AS opt(value)
WHERE e.status = 'completed'
  AND jsonb_typeof(q.value->'options') = 'array';

COMMENT ON VIEW v_question_options IS 'Flat view of MCQ options from extractions.groups; one row per option.';

-- 3. v_memo_answers: one row per memo answer from memo_extractions.sections[*].questions[*]
CREATE OR REPLACE VIEW v_memo_answers AS
SELECT
  me.id AS memo_extraction_id,
  me.scraped_file_id,
  me.file_name,
  me.subject,
  me.year,
  me.session,
  me.grade,
  me.total_marks,
  s.value->>'section_id' AS section_id,
  q.value->>'id' AS question_id,
  q.value->>'text' AS question_text,
  q.value->>'type' AS question_type,
  (q.value->>'marks')::integer AS marks,
  (q.value->>'max_marks')::integer AS max_marks,
  q.value->>'marker_instruction' AS marker_instruction,
  q.value->>'notes' AS notes,
  q.value->>'topic' AS topic,
  CASE WHEN jsonb_typeof(q.value->'model_answers') = 'array' THEN q.value->'model_answers' ELSE NULL END AS model_answers,
  CASE WHEN jsonb_typeof(q.value->'answers') = 'array' THEN q.value->'answers' ELSE NULL END AS sub_answers,
  CASE WHEN jsonb_typeof(q.value->'essay_structure') = 'object' THEN q.value->'essay_structure' ELSE NULL END AS essay_structure,
  q.value->'structured_answer' AS structured_answer
FROM memo_extractions me,
  jsonb_array_elements(me.sections) AS s(value),
  jsonb_array_elements(s.value->'questions') AS q(value)
WHERE me.status = 'completed';

COMMENT ON VIEW v_memo_answers IS 'Flat view of memo answers from memo_extractions.sections JSONB; one row per answer.';

-- 4. v_questions_with_answers: questions joined to memo answers via exam_sets (matched QP–Memo pairs)
CREATE OR REPLACE VIEW v_questions_with_answers AS
SELECT
  q.extraction_id,
  q.scraped_file_id AS question_paper_scraped_file_id,
  q.file_name AS question_paper_file_name,
  q.subject,
  q.syllabus,
  q.year,
  q.session,
  q.grade,
  q.language,
  q.total_marks,
  q.group_id,
  q.group_title,
  q.group_instructions,
  q.question_id,
  q.parent_id,
  q.question_text,
  q.marks,
  q.scenario,
  q.context,
  q.options,
  q.match_data,
  q.guide_table,
  a.memo_extraction_id,
  a.scraped_file_id AS memo_scraped_file_id,
  a.file_name AS memo_file_name,
  a.section_id AS memo_section_id,
  a.question_text AS memo_question_text,
  a.question_type AS memo_question_type,
  a.marks AS memo_marks,
  a.max_marks AS memo_max_marks,
  a.marker_instruction,
  a.notes AS memo_notes,
  a.topic AS memo_topic,
  a.model_answers,
  a.sub_answers,
  a.essay_structure,
  a.structured_answer AS memo_structured_answer,
  es.id AS exam_set_id
FROM v_questions q
JOIN exam_sets es ON es.question_paper_id = q.scraped_file_id
JOIN v_memo_answers a ON a.scraped_file_id = es.memo_id AND a.question_id = q.question_id;

COMMENT ON VIEW v_questions_with_answers IS 'Questions joined to memo answers via exam_sets; only rows where QP and Memo are matched and question_id aligns.';
