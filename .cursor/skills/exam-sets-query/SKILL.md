---
name: exam-sets-query
description: Query the exam_sets table for complete QP-Memo pairs, incomplete sets, or summary statistics. Use when the user wants to see matched exam papers, check matching status, or export exam set data.
version: 1.0.0
source: project-docs
---

# Exam Sets – Query and Export

When you need to **query exam_sets** for complete pairs, incomplete sets, or statistics, use this skill with Supabase MCP.

## When to Use

- User asks for "complete pairs", "matched exams", "exam sets", or "QP-Memo matches"
- You need to check matching status or export exam set data
- You need statistics on matching progress

## Key Concepts

### exam_sets Table Structure

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| subject | text | Subject name |
| grade | int | Grade level (10, 11, 12) |
| paper_number | int | Paper number (1, 2, 3) |
| year | int | Exam year |
| session | text | Exam session (November, May/June, etc.) |
| syllabus | text | Syllabus (NSC, IEB, Cambridge, etc.) |
| question_paper_id | UUID | FK to scraped_files (QP) |
| memo_id | UUID | FK to scraped_files (Memo) |
| match_method | text | How matched: automatic, manual, filename, content |
| match_confidence | int | Confidence score (0-100) |
| status | text | matched, incomplete, duplicate_review |
| created_at | timestamp | Creation timestamp |

### Status Values

- **matched**: Complete pair (both QP and Memo linked)
- **incomplete**: Only QP or only Memo linked
- **duplicate_review**: Potential duplicate or mismatch needing review

## Common Queries

### 1. Summary Statistics

```sql
SELECT 
    COUNT(*) as total_exam_sets,
    COUNT(question_paper_id) as with_qp,
    COUNT(memo_id) as with_memo,
    COUNT(CASE WHEN question_paper_id IS NOT NULL AND memo_id IS NOT NULL THEN 1 END) as complete_pairs,
    COUNT(CASE WHEN question_paper_id IS NOT NULL AND memo_id IS NULL THEN 1 END) as qp_only,
    COUNT(CASE WHEN question_paper_id IS NULL AND memo_id IS NOT NULL THEN 1 END) as memo_only
FROM exam_sets;
```

### 2. Complete Pairs (QP + Memo)

```sql
SELECT 
    es.id as exam_set_id,
    es.subject,
    es.grade,
    es.paper_number,
    es.year,
    es.session,
    es.syllabus,
    es.match_method,
    es.match_confidence,
    es.status,
    sf_qp.filename as qp_filename,
    sf_memo.filename as memo_filename,
    es.created_at
FROM exam_sets es
LEFT JOIN scraped_files sf_qp ON es.question_paper_id = sf_qp.id
LEFT JOIN scraped_files sf_memo ON es.memo_id = sf_memo.id
WHERE es.question_paper_id IS NOT NULL 
  AND es.memo_id IS NOT NULL
ORDER BY es.created_at DESC
LIMIT {N};
```

### 3. Incomplete Sets (QP Only)

```sql
SELECT 
    es.id,
    es.subject,
    es.grade,
    es.paper_number,
    es.year,
    es.session,
    sf_qp.filename as qp_filename
FROM exam_sets es
LEFT JOIN scraped_files sf_qp ON es.question_paper_id = sf_qp.id
WHERE es.question_paper_id IS NOT NULL 
  AND es.memo_id IS NULL
ORDER BY es.created_at DESC
LIMIT {N};
```

### 4. Incomplete Sets (Memo Only)

```sql
SELECT 
    es.id,
    es.subject,
    es.grade,
    es.paper_number,
    es.year,
    es.session,
    sf_memo.filename as memo_filename
FROM exam_sets es
LEFT JOIN scraped_files sf_memo ON es.memo_id = sf_memo.id
WHERE es.question_paper_id IS NULL 
  AND es.memo_id IS NOT NULL
ORDER BY es.created_at DESC
LIMIT {N};
```

### 5. Duplicate Review Items

```sql
SELECT 
    es.id,
    es.subject,
    es.grade,
    es.paper_number,
    es.year,
    es.session,
    sf_qp.filename as qp_filename,
    sf_memo.filename as memo_filename
FROM exam_sets es
LEFT JOIN scraped_files sf_qp ON es.question_paper_id = sf_qp.id
LEFT JOIN scraped_files sf_memo ON es.memo_id = sf_memo.id
WHERE es.status = 'duplicate_review'
ORDER BY es.created_at DESC
LIMIT {N};
```

### 6. By Match Method

```sql
SELECT 
    match_method,
    COUNT(*) as count,
    AVG(match_confidence) as avg_confidence
FROM exam_sets
GROUP BY match_method
ORDER BY count DESC;
```

### 7. By Subject (Top Subjects)

```sql
SELECT 
    subject,
    COUNT(*) as total,
    COUNT(CASE WHEN question_paper_id IS NOT NULL AND memo_id IS NOT NULL THEN 1 END) as complete_pairs
FROM exam_sets
GROUP BY subject
ORDER BY total DESC
LIMIT 20;
```

### 8. Filter by Subject/Grade/Year

```sql
SELECT 
    es.*,
    sf_qp.filename as qp_filename,
    sf_memo.filename as memo_filename
FROM exam_sets es
LEFT JOIN scraped_files sf_qp ON es.question_paper_id = sf_qp.id
LEFT JOIN scraped_files sf_memo ON es.memo_id = sf_memo.id
WHERE es.subject ILIKE '%{subject}%'
  AND es.grade = {grade}
  AND es.year = {year}
ORDER BY es.created_at DESC;
```

## Markdown Output Format

### Summary Table

```markdown
## Exam Sets Summary

| Metric | Count |
|--------|-------|
| Total exam_sets | 3,626 |
| With Question Paper | 2,706 |
| With Memo | 2,041 |
| Complete Pairs | 1,121 |
| QP Only | 1,585 |
| Memo Only | 920 |
```

### Complete Pairs Table

```markdown
## Complete QP-Memo Pairs

| Subject | Grade | Paper | Year | Session | Status | QP Filename | Memo Filename |
|---------|-------|-------|------|---------|--------|-------------|---------------|
| Mathematics | 12 | 1 | 2024 | November | matched | Math-P1-QP-Nov-2024.pdf | Math-P1-Memo-Nov-2024.pdf |
| ... | ... | ... | ... | ... | ... | ... | ... |
```

## Related

- **Batch Matcher Script:** `scripts/run_extraction_batch_matcher.py` – creates exam_sets from extractions
- **DB Tables Export:** `.cursor/skills/db-tables-markdown-export/SKILL.md` – general table export
- **Extractions Export:** `.cursor/skills/extractions-db-export/SKILL.md` – extractions table export
