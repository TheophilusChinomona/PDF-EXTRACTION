# PDF-Extraction Service

Microservice for extracting structured data from academic PDFs using hybrid OpenDataLoader + Gemini pipeline. Achieves 80% cost reduction and 95%+ accuracy.

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `"C:\Python314\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000` | Start server |
| `"C:\Python314\python.exe" scripts/<script>.py` | Run scripts |
| `pytest tests/ -v --cov=app` | Run tests |

**Note:** No local venv - use system Python (`C:\Python314\python.exe`) for all operations.

---

## SQL Migrations

No CLI tools available. Use Supabase Dashboard SQL Editor:
`https://supabase.com/dashboard/project/aqxgnvjqabitfvcnboah`

---

## Ralph Agents

If you are an autonomous agent, read `scripts/ralph/CLAUDE.md` first.

---

## Detailed Guidelines

- [Architecture](instructions/architecture.md) - Tech stack, file structure, hybrid pipeline
- [Python Patterns](instructions/python-patterns.md) - Code style, Gemini SDK, extraction patterns
- [Environment Setup](instructions/environment.md) - Python interpreter, env vars, migrations
- [Security](instructions/security.md) - API keys, PDF safety, data privacy
- [Testing](instructions/testing.md) - Test commands and coverage
- [Ralph Workflow](instructions/ralph-workflow.md) - Autonomous agent instructions

---

## References

- **PRD:** `.claude/tasks/prd-pdf-extraction-service.md`
- **Tasks:** `.claude/tasks/todo.md`
- **Global Rules:** `~/.claude/CLAUDE.md`
