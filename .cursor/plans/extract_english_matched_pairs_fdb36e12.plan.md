---
name: Extract English Matched Pairs
overview: Create a script to run extraction on matched English exam_sets (32 QP-Memo pairs), then export the extraction results to markdown documents showing the full question paper and marking guideline content.
todos:
  - id: create-extract-script
    content: Create scripts/extract_matched_pairs.py - downloads PDFs from Firebase for matched exam_sets and runs extraction pipeline
    status: completed
  - id: update-export-script
    content: Update scripts/export_extractions_md.py --exam-sets mode to fetch full extraction JSON and convert to markdown
    status: completed
  - id: run-extraction
    content: Run extraction on 10 English matched pairs as test
    status: completed
  - id: export-markdown
    content: Export extracted pairs to markdown files
    status: completed
isProject: false
---

# Extract and Export Matched English Exam Pairs

## Current State

- **32 matched English exam_sets** in database (QP + Memo pairs)
- Only **3 have QP extractions**, **0 have memo extractions**
- All files exist in Firebase Storage with valid `storage_path`

## Data Flow

```mermaid
flowchart LR
    subgraph source [Source Data]
        ES[exam_sets<br/>32 English pairs]
        SF[scraped_files<br/>storage_path]
    end
    
    subgraph extract [Extraction]
        FB[(Firebase Storage)]
        EXT[extract_pdf_data_hybrid]
        MEMO[extract_memo_data_hybrid]
    end
    
    subgraph output [Output]
        DB[(extractions +<br/>memo_extractions)]
        MD[Markdown Files]
    end
    
    ES --> SF
    SF --> FB
    FB --> EXT
    FB --> MEMO
    EXT --> DB
    MEMO --> DB
    DB --> MD
```



## Implementation

### Step 1: Create Extraction Script for Matched Pairs

Create `[scripts/extract_matched_pairs.py](scripts/extract_matched_pairs.py)` that:

1. **Queries exam_sets** filtered by subject and status
2. **Downloads PDFs** from Firebase Storage using `storage_path`
3. **Runs extraction** via existing pipeline:
  - `extract_pdf_data_hybrid()` for question papers
  - `extract_memo_data_hybrid()` for memos
4. **Saves to database** with `scraped_file_id` linkage

Key code to leverage:

- `[app/services/firebase_client.py](app/services/firebase_client.py)` - `download_as_bytes()`
- `[app/services/pdf_extractor.py](app/services/pdf_extractor.py)` - `extract_pdf_data_hybrid()`
- `[app/services/memo_extractor.py](app/services/memo_extractor.py)` - `extract_memo_data_hybrid()`
- `[app/db/extractions.py](app/db/extractions.py)` - `create_extraction()`
- `[app/db/memo_extractions.py](app/db/memo_extractions.py)` - `create_memo_extraction()`

### Step 2: Update Export Script

Modify `[scripts/export_extractions_md.py](scripts/export_extractions_md.py)` to:

1. Add `--exam-sets` mode that:
  - Fetches exam_sets with linked extractions
  - Retrieves full extraction JSON from `extractions` and `memo_extractions`
  - Converts to markdown using existing `qp_to_markdown()` and `memo_to_markdown()`
2. Output paired markdown files: `{subject}-{year}-p{paper}-qp.md` and `{subject}-{year}-p{paper}-mg.md`

### CLI Usage

```bash
# Step 1: Run extraction on matched English pairs
python scripts/extract_matched_pairs.py --subject english --status matched --limit 10

# Step 2: Export to markdown
python scripts/export_extractions_md.py --exam-sets --subject english
```

## Files to Create/Modify


| File                               | Action | Purpose                                         |
| ---------------------------------- | ------ | ----------------------------------------------- |
| `scripts/extract_matched_pairs.py` | Create | Extract matched exam_sets from Firebase         |
| `scripts/export_extractions_md.py` | Modify | Add exam_sets mode with full extraction content |


## Dependencies

- `SUPABASE_SERVICE_ROLE_KEY` in `.env` (for RLS bypass)
- `GOOGLE_API_KEY` in `.env` (for Gemini extraction)
- Firebase credentials configured

