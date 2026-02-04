# Paper Matching & Reconstruction Service - Implementation Plan

> **Goal**: Match question papers to their memos, extract document instructions separately, and enable complete paper reconstruction from the database using a unified ID scheme.

---

## Executive Summary

This service extends the extraction pipeline to:
1. **Match QP ↔ Memo** based on metadata (subject, grade, paper, year, session)
2. **Extract Instructions** separately from questions (student instructions, marker notes)
3. **Unified ID Scheme** to link all document components for reconstruction

**Separate from Unification Plan** - can be developed in parallel worktree.

---

## 1. What We're Extracting

### Question Paper Components
| Component | Pages | Content | Current Status |
|-----------|-------|---------|----------------|
| Cover Page | 1 | Title, marks, time, page count | ✅ Extracted as metadata |
| Instructions | 2 | Student instructions (10 items) | ❌ **Skipped** |
| Questions | 3+ | Actual questions with marks | ✅ Extracted |
| Information Sheet | Last | Formulae, references | ❌ **Skipped** |

### Memo Components
| Component | Pages | Content | Current Status |
|-----------|-------|---------|----------------|
| Cover Page | 1 | Title, marks, page count | ✅ Extracted as metadata |
| Notes to Markers | 2-6 | Marking guidelines, rubrics | ❌ **Skipped** |
| Mark Breakdown | Various | LASO scoring, submaxes | ❌ **Skipped** |
| Answers | 7+ | Actual answers with marks | ✅ Extracted |

---

## 2. Unified ID Scheme

### Current Problem
```
QP: scraped_file_id = abc123 (no link to memo)
Memo: scraped_file_id = def456 (no link to QP)
```

### Proposed Solution
```
Exam Set ID: exam-set-uuid-001
├── Question Paper: abc123
│   ├── Cover: abc123-cover
│   ├── Instructions: abc123-instructions
│   ├── Questions: abc123-questions (array)
│   └── Info Sheet: abc123-infosheet
│
└── Memo: def456 (linked via exam_set_id)
    ├── Cover: def456-cover
    ├── Marker Notes: def456-markernotes
    └── Answers: def456-answers (array)
```

### ID Relationships
```
exam_sets.id (UUID)
    ├── exam_sets.question_paper_id → scraped_files.id
    └── exam_sets.memo_id → scraped_files.id

scraped_files.id (UUID)
    ├── document_sections.scraped_file_id
    ├── extractions.scraped_file_id (questions)
    └── memo_extractions.scraped_file_id (answers)
```

---

## 3. Database Schema

### 3.1 Exam Sets (QP ↔ Memo Linking)
```sql
CREATE TABLE exam_sets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Exam Identity (matching key)
    subject TEXT NOT NULL,
    grade INTEGER NOT NULL,            -- Just the number: 10, 11, 12 (not "Grade 12")
    paper_number INTEGER NOT NULL,     -- Just the number: 1, 2, 3 (not "P1")
    year INTEGER NOT NULL,
    session TEXT NOT NULL,             -- 'May/June', 'Nov', 'Feb/March'
    syllabus TEXT,                     -- 'NSC', 'SC', 'IEB'

    -- Linked Documents
    question_paper_id UUID REFERENCES scraped_files(id),
    memo_id UUID REFERENCES scraped_files(id),

    -- Matching Info
    match_method TEXT CHECK (match_method IN (
        'automatic', 'manual', 'filename', 'content'
    )),
    match_confidence INTEGER CHECK (match_confidence BETWEEN 0 AND 100),
    matched_at TIMESTAMPTZ,
    matched_by TEXT,                   -- 'system' or user_id

    -- Status
    status TEXT DEFAULT 'incomplete' CHECK (status IN (
        'incomplete',                  -- Only QP or only Memo
        'matched',                     -- Both linked
        'verified',                    -- Human verified match
        'mismatch'                     -- Incorrectly matched, needs fix
    )),

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    UNIQUE(subject, grade, paper_number, year, session, syllabus)
);

-- Indexes
CREATE INDEX idx_exam_sets_matching
    ON exam_sets(subject, grade, paper_number, year, session);
CREATE INDEX idx_exam_sets_qp ON exam_sets(question_paper_id);
CREATE INDEX idx_exam_sets_memo ON exam_sets(memo_id);
```

### 3.2 Document Sections (Instructions, Marker Notes, etc.)
```sql
CREATE TABLE document_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scraped_file_id UUID NOT NULL REFERENCES scraped_files(id),

    -- Section Identity
    section_type TEXT NOT NULL CHECK (section_type IN (
        'cover_page',              -- Title, marks, time
        'student_instructions',    -- "Read the following instructions..."
        'marker_notes',            -- "Notes to Markers" (memos)
        'information_sheet',       -- Formulae, reference tables
        'mark_breakdown',          -- LASO scoring rubrics
        'appendix'                 -- Additional materials
    )),

    -- Content
    title TEXT,                    -- "INSTRUCTIONS AND INFORMATION"
    content JSONB NOT NULL,        -- Structured content (see below)
    raw_text TEXT,                 -- Plain text version

    -- Location in Document
    page_start INTEGER,
    page_end INTEGER,

    -- Extraction Info
    extraction_method TEXT,        -- 'gemini_vision', 'opendataloader'
    confidence_score INTEGER CHECK (confidence_score BETWEEN 0 AND 100),

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- One section type per document
    UNIQUE(scraped_file_id, section_type)
);

-- Indexes
CREATE INDEX idx_document_sections_file ON document_sections(scraped_file_id);
CREATE INDEX idx_document_sections_type ON document_sections(section_type);
```

### 3.3 Content Structure (JSONB)

**Student Instructions:**
```json
{
  "header": "INSTRUCTIONS AND INFORMATION",
  "items": [
    {
      "number": 1,
      "text": "This question paper consists of 11 questions."
    },
    {
      "number": 2,
      "text": "Answer ALL the questions."
    },
    {
      "number": 3,
      "text": "Number the answers correctly according to the numbering system used in this question paper."
    }
  ],
  "notes": [
    "Diagrams are NOT necessarily drawn to scale.",
    "An information sheet with formulae is included at the end of the question paper."
  ]
}
```

**Marker Notes:**
```json
{
  "header": "NOTES TO MARKERS",
  "preamble": "The notes to markers are provided for quality assurance purposes...",
  "sections": [
    {
      "number": 1,
      "title": "Marking Colours",
      "content": {
        "Marker": "Red",
        "Senior Marker": "Green",
        "Deputy Chief Marker": "Orange",
        "Chief Marker": "Pink",
        "Internal Moderator": "Black/Blue",
        "DBE Moderator": "Turquoise"
      }
    },
    {
      "number": 14,
      "title": "SECTION B",
      "subsections": [
        {
          "number": "14.1",
          "text": "If for example, FIVE facts are required, mark the candidate's FIRST FIVE responses..."
        }
      ]
    }
  ],
  "cognitive_verbs": {
    "simple": ["Give", "name", "state", "outline", "quote"],
    "complex": ["Define", "describe", "explain", "discuss", "elaborate"]
  },
  "essay_marking": {
    "max_content": 32,
    "max_insight": 8,
    "insight_components": {
      "Layout": 2,
      "Analysis": 2,
      "Synthesis": 2,
      "Originality": 2
    }
  }
}
```

**Cover Page:**
```json
{
  "organization": "Department: Basic Education",
  "country": "REPUBLIC OF SOUTH AFRICA",
  "certificate": "NATIONAL SENIOR CERTIFICATE",
  "grade": "GRADE 12",
  "subject": "MATHEMATICS P1",
  "session": "FEBRUARY/MARCH 2017",
  "document_type": "Question Paper",
  "marks": 150,
  "time": "3 hours",
  "page_count": 9,
  "info_sheet_count": 1
}
```

**Information Sheet:**
```json
{
  "header": "INFORMATION SHEET",
  "formulae": [
    {
      "name": "Quadratic Formula",
      "latex": "x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}"
    },
    {
      "name": "Arithmetic Series Sum",
      "latex": "S_n = \\frac{n}{2}[2a + (n-1)d]"
    }
  ],
  "tables": [],
  "constants": []
}
```

---

## 4. Matching Algorithm

### 4.1 When to Match
**Option A: During Validation (Recommended)**
- Validation extracts metadata (subject, grade, year, session, paper)
- Immediately attempt to match with existing exam_sets
- If match found → link; if not → create new incomplete exam_set

**Note:** Validation can run via the **Gemini Batch API** for large batches (100+ files); the poller applies results when the batch job completes. Matching logic runs after validation results are written (whether from online or batch path).

### 4.2 Matching Logic
```python
async def match_document_to_exam_set(
    scraped_file_id: UUID,
    metadata: ValidationResult
) -> Optional[UUID]:
    """Match a document to an exam set, creating one if needed."""

    # 1. Build matching key (grade and paper_number are integers)
    match_key = {
        'subject': normalize_subject(metadata.subject),
        'grade': normalize_grade(metadata.grade),              # INTEGER: 12 (not "Grade 12")
        'paper_number': normalize_paper_number(metadata.paper_number),  # INTEGER: 1 (not "P1")
        'year': metadata.year,
        'session': normalize_session(metadata.session),
        'syllabus': metadata.syllabus or 'NSC'
    }

    # 2. Look for existing exam_set
    existing = await db.exam_sets.find_one(match_key)

    if existing:
        # 3a. Found match - link document
        if metadata.paper_type == 'question_paper':
            if existing.question_paper_id:
                # Already has QP - possible duplicate
                return handle_duplicate(existing, scraped_file_id)
            await db.exam_sets.update(
                existing.id,
                question_paper_id=scraped_file_id,
                status='matched' if existing.memo_id else 'incomplete',
                matched_at=now()
            )
        else:  # memo
            if existing.memo_id:
                return handle_duplicate(existing, scraped_file_id)
            await db.exam_sets.update(
                existing.id,
                memo_id=scraped_file_id,
                status='matched' if existing.question_paper_id else 'incomplete',
                matched_at=now()
            )
        return existing.id
    else:
        # 3b. No match - create new exam_set
        exam_set_id = await db.exam_sets.insert({
            **match_key,
            'question_paper_id': scraped_file_id if metadata.paper_type == 'question_paper' else None,
            'memo_id': scraped_file_id if metadata.paper_type == 'memo' else None,
            'status': 'incomplete',
            'match_method': 'automatic'
        })
        return exam_set_id

def normalize_subject(subject: str) -> str:
    """Normalize subject names for matching."""
    mappings = {
        'maths': 'Mathematics',
        'math': 'Mathematics',
        'mathematics': 'Mathematics',
        'physical science': 'Physical Sciences',
        'physical sciences': 'Physical Sciences',
        'bus studies': 'Business Studies',
        # ... more mappings
    }
    return mappings.get(subject.lower(), subject.title())

def normalize_grade(grade: str | int) -> int:
    """Normalize grade to just the number."""
    if isinstance(grade, int):
        return grade
    # Extract number from strings like "Grade 12", "Gr 12", "12"
    import re
    match = re.search(r'\d+', str(grade))
    return int(match.group()) if match else None

def normalize_paper_number(paper: str | int) -> int:
    """Normalize paper number to just the number."""
    if isinstance(paper, int):
        return paper
    # Extract number from strings like "P1", "Paper 1", "1"
    import re
    match = re.search(r'\d+', str(paper))
    return int(match.group()) if match else 1

def normalize_session(session: str) -> str:
    """Normalize session names."""
    if 'may' in session.lower() or 'june' in session.lower():
        return 'May/June'
    if 'nov' in session.lower():
        return 'November'
    if 'feb' in session.lower() or 'mar' in session.lower():
        return 'February/March'
    return session
```

### 4.3 Match Confidence Scoring
```python
def calculate_match_confidence(qp_meta: dict, memo_meta: dict) -> int:
    """Calculate confidence that QP and Memo match."""
    score = 0

    # Exact matches
    if qp_meta['subject'] == memo_meta['subject']:
        score += 25
    if qp_meta['grade'] == memo_meta['grade']:
        score += 20
    if qp_meta['paper_number'] == memo_meta['paper_number']:
        score += 20
    if qp_meta['year'] == memo_meta['year']:
        score += 20
    if qp_meta['session'] == memo_meta['session']:
        score += 15

    return score  # Max 100
```

---

## 5. Extraction Pipeline Updates

### 5.1 Updated Flow (Validate First → Match → Extract Sections → Extract Questions)

```
Download PDF
    ↓
Validate (Gemini Vision)
    ↓
Match to Exam Set ← NEW
    ↓
Rename File
    ↓
Extract Sections ← NEW (cover, instructions, marker notes)
    ↓
Extract Questions/Answers (existing pipeline)
    ↓
Store All Components
```

### 5.2 Section Extraction Prompt

```python
SECTION_EXTRACTION_PROMPT = """
Analyze this PDF document and extract the following sections:

1. COVER PAGE (page 1):
   - Organization, certificate type, grade
   - Subject, paper number, session/year
   - Total marks, time allowed, page count

2. INSTRUCTIONS (usually page 2):
   For Question Papers:
   - Student instructions (numbered list)
   - General notes

   For Marking Guidelines/Memos:
   - Notes to Markers (detailed marking guidelines)
   - Cognitive verb explanations
   - Essay marking rubrics (LASO scoring)
   - Section-specific marking notes

3. INFORMATION SHEET (last page, if present):
   - Formulae and equations
   - Reference tables
   - Constants

Return JSON with structure:
{
  "cover_page": { ... },
  "instructions": { ... },  // or "marker_notes" for memos
  "information_sheet": { ... }  // null if not present
}
"""
```

### 5.3 Files to Modify

| File | Changes |
|------|---------|
| `app/services/section_extractor.py` | NEW - Extract cover, instructions, info sheet |
| `app/services/pdf_extractor.py` | Call section extractor before question extraction |
| `app/services/exam_matcher.py` | NEW - Match QP ↔ Memo |
| `app/db/exam_sets.py` | NEW - CRUD for exam_sets table |
| `app/db/document_sections.py` | NEW - CRUD for document_sections |
| `ValidationAgent/validate_worker.py` | Add exam set matching after validation |
| `app/services/batch_job_poller.py` | When processing validation batch results, apply matching per result (Gemini Batch API path) |

---

## 6. API Endpoints

### 6.1 Exam Sets API

```
GET /api/exam-sets
Query params: subject, grade, year, session, status
Response: List of exam sets with QP/Memo linkage status

GET /api/exam-sets/{exam_set_id}
Response: Full exam set with all linked documents and sections

GET /api/exam-sets/{exam_set_id}/reconstruct
Response: Complete reconstructed paper (cover + instructions + questions)

POST /api/exam-sets/match
Body: { question_paper_id, memo_id }
Response: Created/updated exam_set with match confidence
```

### 6.2 Document Sections API

```
GET /api/documents/{scraped_file_id}/sections
Response: All sections for a document

GET /api/documents/{scraped_file_id}/sections/{section_type}
Response: Specific section (cover_page, student_instructions, etc.)
```

### 6.3 Paper Reconstruction API

```
GET /api/exam-sets/{exam_set_id}/question-paper/full
Response: {
  "exam_set_id": "...",
  "cover_page": { ... },
  "instructions": { ... },
  "questions": [ ... ],
  "information_sheet": { ... }
}

GET /api/exam-sets/{exam_set_id}/memo/full
Response: {
  "exam_set_id": "...",
  "cover_page": { ... },
  "marker_notes": { ... },
  "answers": [ ... ],
  "mark_breakdown": { ... }
}
```

---

## 7. Implementation Phases

### Phase 1: Database & Matching (Week 1-2)
- [ ] Create `exam_sets` table
- [ ] Create `document_sections` table
- [ ] Implement matching algorithm
- [ ] Integrate matching into validation flow

### Phase 2: Section Extraction (Week 2-3)
- [ ] Create section extraction prompts
- [ ] Implement `section_extractor.py`
- [ ] Extract cover pages
- [ ] Extract student instructions (QP)
- [ ] Extract marker notes (Memo)
- [ ] Extract information sheets

### Phase 3: API & Reconstruction (Week 3-4)
- [ ] Create exam sets API endpoints
- [ ] Create document sections API endpoints
- [ ] Implement paper reconstruction endpoint
- [ ] Add match confidence scoring

### Phase 4: Integration & Testing (Week 4-5)
- [ ] Integrate with main extraction pipeline
- [ ] Test QP ↔ Memo matching accuracy
- [ ] Test full paper reconstruction
- [ ] Handle edge cases (missing memos, duplicates)

---

## 8. Verification

### 8.1 Matching Verification
```sql
-- Find matched exam sets
SELECT
    es.subject, es.grade, es.paper_number, es.year, es.session,
    qp.file_name as question_paper,
    m.file_name as memo,
    es.match_confidence,
    es.status
FROM exam_sets es
LEFT JOIN scraped_files qp ON es.question_paper_id = qp.id
LEFT JOIN scraped_files m ON es.memo_id = m.id
WHERE es.status = 'matched';

-- Find incomplete sets (missing QP or Memo)
SELECT * FROM exam_sets WHERE status = 'incomplete';
```

### 8.2 Reconstruction Test
```bash
# Get full question paper
curl http://localhost:8000/api/exam-sets/{id}/question-paper/full

# Verify all components present
jq '.cover_page, .instructions, .questions | length, .information_sheet' response.json
```

---

## 9. Success Criteria

- [ ] QP ↔ Memo matching works with 95%+ accuracy
- [ ] Exam sets created for all document pairs
- [ ] Instructions extracted separately from questions
- [ ] Marker notes extracted separately from answers
- [ ] Full paper reconstruction returns complete document
- [ ] API endpoints return linked data
- [ ] Incomplete sets (missing QP or Memo) are tracked

---

## Appendix A: Document Structure Examples

### Question Paper Structure
```
Page 1:  Cover (DBE logo, title, marks, time)
Page 2:  Instructions (10 numbered items)
Page 3+: Questions (QUESTION 1, 2, 3...)
Page N:  Information Sheet (formulae)
```

### Memo Structure
```
Page 1:    Cover (DBE logo, title, "MARKING GUIDELINES")
Page 2-6:  Notes to Markers (preamble, marking rules, LASO)
Page 7+:   Answers (SECTION A, B, C with mark allocations)
```

---

## Appendix B: Normalization Mappings

### Grade Normalization (to INTEGER)
```python
def normalize_grade(grade: str | int) -> int:
    """
    Normalize grade to just the number.

    Examples:
        "Grade 12" → 12
        "Gr 12" → 12
        "12" → 12
        12 → 12
    """
    if isinstance(grade, int):
        return grade
    import re
    match = re.search(r'\d+', str(grade))
    return int(match.group()) if match else None
```

### Paper Number Normalization (to INTEGER)
```python
def normalize_paper_number(paper: str | int) -> int:
    """
    Normalize paper number to just the number.

    Examples:
        "P1" → 1
        "Paper 1" → 1
        "1" → 1
        1 → 1
    """
    if isinstance(paper, int):
        return paper
    import re
    match = re.search(r'\d+', str(paper))
    return int(match.group()) if match else 1
```

### Subject Normalization
```python
SUBJECT_MAPPINGS = {
    'maths': 'Mathematics',
    'math': 'Mathematics',
    'mathematics': 'Mathematics',
    'mathematical literacy': 'Mathematical Literacy',
    'math lit': 'Mathematical Literacy',
    'physical science': 'Physical Sciences',
    'physical sciences': 'Physical Sciences',
    'physics': 'Physical Sciences',
    'life science': 'Life Sciences',
    'life sciences': 'Life Sciences',
    'biology': 'Life Sciences',
    'business studies': 'Business Studies',
    'bus studies': 'Business Studies',
    'accounting': 'Accounting',
    'acc': 'Accounting',
    'economics': 'Economics',
    'eco': 'Economics',
    'geography': 'Geography',
    'geo': 'Geography',
    'history': 'History',
    'his': 'History',
    'english': 'English',
    'english hl': 'English Home Language',
    'english fal': 'English First Additional Language',
    'afrikaans': 'Afrikaans',
    'afrikaans hl': 'Afrikaans Home Language',
    'afrikaans fal': 'Afrikaans First Additional Language',
}
```

### Session Normalization
```python
SESSION_MAPPINGS = {
    'may': 'May/June',
    'june': 'May/June',
    'may/june': 'May/June',
    'may-june': 'May/June',
    'nov': 'November',
    'november': 'November',
    'feb': 'February/March',
    'march': 'February/March',
    'feb/march': 'February/March',
    'feb-march': 'February/March',
    'supplementary': 'February/March',
}
```

---

*Plan created: 2026-02-03*
*Separate worktree from UNIFICATION_PLAN.md*
