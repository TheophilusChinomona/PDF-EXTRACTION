# .claude Directory - Quick Reference

Welcome to the PDF-Extraction project configuration directory.

---

## Directory Structure

```
.claude/
├── CLAUDE.md               # Project-specific guidelines and conventions
├── settings.json           # Project configuration
├── README.md              # This file
├── tasks/
│   ├── todo.md            # Current active tasks
│   ├── template.md        # Task template following 7 Rules
│   └── archive/           # Completed tasks (dated)
├── skills/
│   ├── test-extraction.skill    # Run local PDF extraction tests
│   ├── check-api.skill          # FastAPI health check
│   └── db-verify.skill          # Supabase connection verification
└── prompts/
    ├── gemini-system-prompt.md     # Gemini Vision API extraction prompt
    └── pydantic-schema-prompt.md   # Schema generation prompt
```

---

## Quick Start

### 1. Read Project Guidelines
Start with `CLAUDE.md` for project-specific conventions, tech stack, and coding standards.

### 2. Check Current Tasks
Review `tasks/todo.md` for active work items and upcoming tasks.

### 3. Follow 7 Rules Workflow
All development follows the systematic workflow defined in global `~/.claude/CLAUDE.md`:
1. Think Through the Problem
2. Write a Plan to tasks/todo.md
3. Check In With User
4. Execute the Plan
5. Explain Every Step
6. Keep Everything Simple
7. Add Review Section

### 4. Use Custom Skills
Available commands:
- `/test-extraction <pdf>` - Test local PDF extraction
- `/check-api` - Verify FastAPI service health
- `/db-verify` - Test Supabase connection

---

## Key Files

### CLAUDE.md
- Python/FastAPI conventions (PEP 8, async/await, type hints)
- Security guidelines (API keys, PDF validation)
- Testing requirements
- Project structure standards

### settings.json
- Model preferences (Sonnet for planning/coding)
- File exclusions (.env, __pycache__, etc.)
- Python tooling (black, ruff, mypy)
- Security settings (upload limits, rate limiting)

### tasks/todo.md
- Current sprint tasks
- Phase-based implementation plan (per PRD)
- Blocked items tracking
- Backlog for future enhancements

### prompts/
- `gemini-system-prompt.md` - The core extraction prompt sent to Gemini Vision API
- `pydantic-schema-prompt.md` - Schema validation and generation guide

---

## Development Workflow

### Starting New Work
1. Create new task from `tasks/template.md`
2. Follow 7 Rules: Think → Plan → Check In → Execute → Explain → Simplify → Review
3. Update `tasks/todo.md` with progress
4. Archive completed tasks with date stamp

### Testing Changes
```bash
# Run tests
pytest tests/ -v --cov=app

# Test local extraction
python -m app.services.test_extraction sample.pdf

# Check API health
curl http://localhost:8000/health

# Verify database
python -m app.db.test_connection
```

### Security Checklist (Before Every Commit)
- [ ] No hardcoded secrets
- [ ] Input validation in place
- [ ] File paths sanitized
- [ ] Error messages sanitized
- [ ] .env in .gitignore

---

## Technology Stack

**Backend:**
- Python 3.11+
- FastAPI (async web framework)
- Uvicorn (ASGI server)

**AI/ML:**
- Google Gemini 3 Vision API (multimodal document processing)

**Database:**
- Supabase (PostgreSQL)

**Validation:**
- Pydantic (data models and validation)

**Testing:**
- pytest, pytest-asyncio, pytest-cov

---

## Environment Setup

1. Create virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

4. Run development server:
   ```bash
   uvicorn app.main:app --reload
   ```

---

## Resources

- **PRD:** See `Prd.md` in project root
- **Global Rules:** `~/.claude/CLAUDE.md`
- **API Docs:** http://localhost:8000/docs (when server running)
- **Gemini API:** https://ai.google.dev/docs

---

## Next Steps

1. Review `tasks/todo.md` for current work
2. Set up Python environment
3. Begin Phase 1: Local PDF extraction (US-001)

**Last Updated:** 2026-01-27
