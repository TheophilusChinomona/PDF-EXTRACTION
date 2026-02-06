-- Migration: 022_create_matched_paper_questions_table.sql
-- Description: One flat table per question for matched exam sets (QP + memo columns in one row).
-- Source: exam_sets + extractions.groups + memo_extractions.sections.

CREATE TABLE IF NOT EXISTS matched_paper_questions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  exam_set_id UUID NOT NULL REFERENCES exam_sets(id) ON DELETE CASCADE,
  subject TEXT,
  year INTEGER,
  grade TEXT,
  session TEXT,
  syllabus TEXT,
  question_paper_file_name TEXT,
  memo_file_name TEXT,
  group_id TEXT,
  group_title TEXT,
  group_instructions TEXT,
  question_id TEXT NOT NULL,
  parent_id TEXT,
  question_text TEXT,
  marks INTEGER,
  scenario TEXT,
  context TEXT,
  options JSONB,
  match_data JSONB,
  guide_table JSONB,
  memo_question_text TEXT,
  marker_instruction TEXT,
  model_answers JSONB,
  sub_answers JSONB,
  essay_structure JSONB,
  memo_structured_answer JSONB,
  memo_marks INTEGER,
  memo_max_marks INTEGER,
  memo_notes TEXT,
  memo_topic TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (exam_set_id, group_id, question_id)
);

COMMENT ON TABLE matched_paper_questions IS 'One row per question for matched QP–Memo pairs; QP and memo columns in same row. Refresh via TRUNCATE + INSERT or scripts/populate_matched_paper_questions.py';

CREATE INDEX IF NOT EXISTS idx_matched_paper_questions_exam_set_id ON matched_paper_questions(exam_set_id);
CREATE INDEX IF NOT EXISTS idx_matched_paper_questions_subject ON matched_paper_questions(subject);
CREATE INDEX IF NOT EXISTS idx_matched_paper_questions_year ON matched_paper_questions(year);

-- Populate from exam_sets + extractions.groups + memo_extractions.sections (matched pairs only)
INSERT INTO matched_paper_questions (
  exam_set_id, subject, year, grade, session, syllabus,
  question_paper_file_name, memo_file_name,
  group_id, group_title, group_instructions,
  question_id, parent_id, question_text, marks, scenario, context,
  options, match_data, guide_table,
  memo_question_text, marker_instruction, model_answers, sub_answers,
  essay_structure, memo_structured_answer, memo_marks, memo_max_marks, memo_notes, memo_topic
)
SELECT
  es.id,
  e.subject,
  e.year,
  e.grade,
  e.session,
  COALESCE(e.syllabus, es.syllabus),
  e.file_name,
  me.file_name,
  g.value->>'group_id',
  g.value->>'title',
  g.value->>'instructions',
  q.value->>'id',
  q.value->>'parent_id',
  q.value->>'text',
  (q.value->>'marks')::integer,
  q.value->>'scenario',
  q.value->>'context',
  CASE WHEN jsonb_typeof(q.value->'options') = 'array' THEN q.value->'options' ELSE NULL END,
  CASE WHEN jsonb_typeof(q.value->'match_data') = 'object' THEN q.value->'match_data' ELSE NULL END,
  CASE WHEN jsonb_typeof(q.value->'guide_table') = 'array' THEN q.value->'guide_table' ELSE NULL END,
  memo_row.memo_q->>'text',
  memo_row.memo_q->>'marker_instruction',
  CASE WHEN jsonb_typeof(memo_row.memo_q->'model_answers') = 'array' THEN memo_row.memo_q->'model_answers' ELSE NULL END,
  CASE WHEN jsonb_typeof(memo_row.memo_q->'answers') = 'array' THEN memo_row.memo_q->'answers' ELSE NULL END,
  CASE WHEN jsonb_typeof(memo_row.memo_q->'essay_structure') = 'object' THEN memo_row.memo_q->'essay_structure' ELSE NULL END,
  memo_row.memo_q->'structured_answer',
  (memo_row.memo_q->>'marks')::integer,
  (memo_row.memo_q->>'max_marks')::integer,
  memo_row.memo_q->>'notes',
  memo_row.memo_q->>'topic'
FROM exam_sets es
JOIN extractions e ON e.scraped_file_id = es.question_paper_id AND e.status = 'completed'
JOIN memo_extractions me ON me.scraped_file_id = es.memo_id AND me.status = 'completed',
  jsonb_array_elements(e.groups) AS g(value),
  jsonb_array_elements(g.value->'questions') AS q(value)
LEFT JOIN LATERAL (
  SELECT mq.val AS memo_q
  FROM jsonb_array_elements(me.sections) AS sec(sec_val),
       jsonb_array_elements(sec.sec_val->'questions') AS mq(val)
  WHERE mq.val->>'id' = q.value->>'id'
  LIMIT 1
) memo_row ON true
WHERE es.status = 'matched'
  AND es.question_paper_id IS NOT NULL
  AND es.memo_id IS NOT NULL
ON CONFLICT (exam_set_id, group_id, question_id) DO NOTHING;
