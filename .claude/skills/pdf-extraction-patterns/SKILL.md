---
name: pdf-extraction-patterns
description: Coding patterns and conventions extracted from PDF-Extraction repository
version: 1.0.0
source: local-git-analysis
analyzed_commits: 200
---

# PDF-Extraction Patterns

Coding patterns, conventions, and workflows extracted from the PDF-Extraction repository git history.

---

## Commit Conventions

This project uses **Conventional Commits** format:

| Prefix | Usage | Examples |
|--------|-------|----------|
| `feat:` | New features | `feat: implement Gemini Batch API for validation` |
| `fix:` | Bug fixes | `fix: remove shadowed asyncio import in batch router` |
| `docs:` | Documentation updates | `docs: add comprehensive operations guide` |
| `refactor:` | Code refactoring | `refactor: clean up project structure` |
| `chore:` | Maintenance tasks | `chore: configure Claude local settings` |
| `test:` | Test additions/changes | `test: add integration tests for extraction flow` |

**Priority Labels:**
- `[CRITICAL]` - Security or critical bugs
- `[HIGH]` - Important fixes or features

**Examples:**
```
fix: [CRITICAL] Add CORS origin validation via environment variable
fix: [HIGH] Wrap synchronous Supabase calls with asyncio.to_thread
feat: implement Paper Matching & Reconstruction Service
```

---

## Code Architecture

### Project Structure

```
PDF-Extraction/
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── cli.py               # CLI commands (batch-process, poll-batch-jobs)
│   ├── config.py            # Pydantic settings from .env
│   ├── routers/             # API endpoints (FastAPI routers)
│   ├── services/            # Business logic layer
│   ├── models/              # Pydantic schemas (request/response models)
│   ├── db/                  # Database CRUD layer (Supabase client wrappers)
│   ├── middleware/          # HTTP middleware (logging, rate limiting, CORS)
│   └── utils/               # Shared utilities (retry, normalizers)
├── tests/                   # pytest test suite
├── migrations/              # SQL migration files (001-020)
├── scripts/                 # Utility scripts (database operations, exports)
└── docs/                    # Documentation
```

### Layer Responsibilities

**Routers (`app/routers/`):**
- Handle HTTP requests/responses
- Input validation via Pydantic models
- Call services for business logic
- Return standardized responses

**Services (`app/services/`):**
- Business logic and orchestration
- External API calls (Gemini, Firebase)
- Data transformation
- Error handling and retries

**DB Layer (`app/db/`):**
- Supabase client wrappers
- CRUD operations
- Query building
- Transaction handling

**Models (`app/models/`):**
- Pydantic schemas for validation
- Request/response models
- Database model representations

**Middleware (`app/middleware/`):**
- Request ID tracking
- Rate limiting
- Structured logging
- CORS handling

---

## Workflows

### Adding a New Feature

**1. Create Pydantic Model** (`app/models/`)
```python
# app/models/new_feature.py
from pydantic import BaseModel, Field
from typing import Optional

class NewFeatureRequest(BaseModel):
    field1: str = Field(..., description="Field description")
    field2: Optional[int] = None

class NewFeatureResponse(BaseModel):
    id: str
    status: str
```

**2. Create Database Layer** (`app/db/`)
```python
# app/db/new_feature.py
from app.db.supabase_client import get_supabase_client

async def create_new_feature(data: dict) -> dict:
    client = get_supabase_client()
    result = client.table("new_feature_table").insert(data).execute()
    return result.data[0]
```

**3. Create Service** (`app/services/`)
```python
# app/services/new_feature_service.py
from app.models.new_feature import NewFeatureRequest, NewFeatureResponse
from app.db.new_feature import create_new_feature

async def process_new_feature(request: NewFeatureRequest) -> NewFeatureResponse:
    # Business logic here
    data = request.dict()
    result = await create_new_feature(data)
    return NewFeatureResponse(**result)
```

**4. Create Router** (`app/routers/`)
```python
# app/routers/new_feature.py
from fastapi import APIRouter, HTTPException
from app.models.new_feature import NewFeatureRequest, NewFeatureResponse
from app.services.new_feature_service import process_new_feature

router = APIRouter(prefix="/api/new-feature", tags=["new-feature"])

@router.post("/", response_model=NewFeatureResponse)
async def create_new_feature(request: NewFeatureRequest):
    try:
        return await process_new_feature(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**5. Register Router** (`app/main.py`)
```python
from app.routers.new_feature import router as new_feature_router
app.include_router(new_feature_router)
```

**6. Add Tests** (`tests/`)
```python
# tests/test_new_feature.py
import pytest
from app.models.new_feature import NewFeatureRequest

def test_new_feature_model():
    request = NewFeatureRequest(field1="test")
    assert request.field1 == "test"
```

### Database Migrations

**1. Create Migration File** (`migrations/`)
- Naming: `NNN_descriptive_name.sql` (sequential numbering)
- Example: `021_add_new_feature_table.sql`

**2. Migration Template:**
```sql
-- Migration: 021_add_new_feature_table
-- Description: Add new_feature_table for feature X
-- Date: 2026-02-06

CREATE TABLE IF NOT EXISTS new_feature_table (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    field1 TEXT NOT NULL,
    field2 INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_new_feature_field1 ON new_feature_table(field1);

COMMENT ON TABLE new_feature_table IS 'Stores new feature data';
```

**3. Apply Migration:**
- Via Supabase Dashboard SQL Editor (recommended)
- Run migrations sequentially (001 → 002 → ... → 021)

**4. Update Schema Documentation:**
- Update `migrations/README.md` with new table description
- Add to schema overview section

### Adding CLI Commands

**1. Add Command Handler** (`app/cli.py`)
```python
def create_parser() -> argparse.ArgumentParser:
    # ... existing commands ...
    
    new_cmd_parser = subparsers.add_parser(
        "new-command",
        help="Description of new command"
    )
    new_cmd_parser.add_argument("--option", help="Option description")
    
    return parser

async def new_command_handler(args: argparse.Namespace) -> int:
    # Command logic here
    return 0

def main() -> int:
    # ... existing routing ...
    if args.command == "new-command":
        return asyncio.run(new_command_handler(args))
```

**2. Document in `docs/CONTRIB.md`:**
- Add command to CLI Commands section
- Include options table and examples

### Adding Utility Scripts

**1. Create Script** (`scripts/`)
```python
# scripts/new_script.py
"""
Description of what the script does.

Usage:
    python scripts/new_script.py [OPTIONS]
"""

import argparse
import sys
from dotenv import load_dotenv

load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="Script description")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes")
    args = parser.parse_args()
    
    if args.dry_run:
        print("Dry run mode - no changes made")
        return
    
    # Script logic here

if __name__ == "__main__":
    main()
```

**2. Document in `docs/CONTRIB.md`:**
- Add to Scripts Reference section
- Include description and flags

---

## Testing Patterns

### Test File Naming
- Test files: `test_*.py` in `tests/` directory
- Integration tests: `tests/integration/test_*.py`
- Test functions: `def test_*()` or `async def test_*()`

### Test Structure
```python
# tests/test_feature.py
import pytest
from app.models.feature import FeatureRequest

def test_feature_model_validation():
    """Test Pydantic model validation."""
    request = FeatureRequest(field1="test")
    assert request.field1 == "test"

@pytest.mark.asyncio
async def test_feature_service():
    """Test service layer."""
    # Test service logic
    pass
```

### Running Tests
```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_extraction_router.py -v

# With coverage
pytest tests/ --cov=app --cov-report=html
```

---

## Database Patterns

### Supabase Client Usage

**Singleton Pattern:**
```python
from app.db.supabase_client import get_supabase_client

client = get_supabase_client()
result = client.table("extractions").select("*").execute()
```

**Async Wrapping:**
- Wrap synchronous Supabase calls with `asyncio.to_thread()`:
```python
import asyncio
from app.db.supabase_client import get_supabase_client

async def get_extractions():
    client = get_supabase_client()
    return await asyncio.to_thread(
        lambda: client.table("extractions").select("*").execute()
    )
```

### JSONB Usage
- Use JSONB for flexible nested structures:
  - `extractions.groups` → Array of QuestionGroup objects
  - `memo_extractions.sections` → Array of MemoSection objects
  - `processing_metadata` → Flexible metadata storage

### Indexing Strategy
- **UNIQUE indexes** on `file_hash` columns for deduplication
- **Composite indexes** for common query patterns (`status + created_at`)
- **Partial indexes** for filtered queries (`WHERE resolution IS NULL`)

---

## Error Handling Patterns

### Exception Handling
```python
try:
    result = await some_operation()
except SpecificException as e:
    logger.error(f"Operation failed: {e}")
    raise HTTPException(status_code=500, detail=str(e))
except Exception as e:
    logger.exception("Unexpected error")
    raise HTTPException(status_code=500, detail="Internal server error")
```

### Retry Pattern
```python
from app.utils.retry import retry_with_backoff

@retry_with_backoff(max_retries=3, backoff_factor=2)
async def unreliable_operation():
    # Operation that may fail
    pass
```

---

## Configuration Patterns

### Environment Variables
- Load via Pydantic Settings (`app/config.py`)
- Use `.env.example` as template
- Document all variables in `docs/CONTRIB.md`

### Settings Pattern
```python
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    gemini_api_key: str
    supabase_url: str
    supabase_key: str
    
    class Config:
        env_file = ".env"

def get_settings() -> Settings:
    return Settings()
```

---

## Script Patterns

### Common Script Structure
```python
"""
Script description.

Usage:
    python scripts/script_name.py [OPTIONS]
"""

import argparse
import sys
from dotenv import load_dotenv

load_dotenv()

def get_supabase():
    """Initialize Supabase client."""
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    if args.dry_run:
        print("Dry run - no changes")
        return
    
    # Script logic

if __name__ == "__main__":
    main()
```

### Script Categories
- **Extraction & Batch**: Processing scripts
- **Database Operations**: Query/update scripts
- **Data Management**: Migration/linking scripts
- **Diagnostics**: Debugging/fixing scripts

---

## Documentation Patterns

### Code Comments
- Use docstrings for functions/classes
- Include parameter descriptions
- Document return types

### Documentation Files
- `README.md` - Project overview
- `docs/CONTRIB.md` - Development guide
- `docs/RUNBOOK.md` - Operations guide
- `docs/CURRENT_STATUS.md` - Current project status
- `migrations/README.md` - Database schema docs

---

## Common Patterns Summary

### File Co-Changes
- **Router + Service + Model**: Adding new endpoints
- **Migration + DB Layer**: Schema changes
- **Service + Tests**: Feature implementation
- **Config + Router**: New configuration options

### Workflow Sequences
1. **New Feature**: Model → DB → Service → Router → Tests → Docs
2. **Database Change**: Migration → DB Layer → Service Update → Tests
3. **Bug Fix**: Identify → Fix → Test → Document
4. **Script Addition**: Script → Test → Document in CONTRIB.md

### Architecture Principles
- **Separation of Concerns**: Routers handle HTTP, Services handle logic, DB handles data
- **Async First**: Use `async/await` for I/O operations
- **Type Safety**: Use Pydantic models for validation
- **Error Handling**: Wrap external calls, log errors, return appropriate HTTP status codes
- **Configuration**: Environment variables via Pydantic Settings

---

## Testing Checklist

When adding new features:
- [ ] Unit tests for models
- [ ] Service layer tests
- [ ] Router/integration tests
- [ ] Error case tests
- [ ] Edge case tests

---

*Generated from git history analysis (200 commits)*
*Last updated: 2026-02-06*
