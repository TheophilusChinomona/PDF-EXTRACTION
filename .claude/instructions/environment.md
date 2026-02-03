# Environment Setup

## Overview
Local development environment configuration.

---

## Required Environment Variables

```bash
GEMINI_API_KEY=your_api_key_here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_anon_key_here
```

---

## Python Interpreter

**No local virtual environment** - use system Python for all operations.

| Task | Command |
|------|---------|
| Start server | `"C:\Python314\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Run scripts | `"C:\Python314\python.exe" scripts/<script>.py` |
| Run tests | `"C:\Python314\python.exe" -m pytest tests/ -v` |

---

## SQL Migrations

No `psql` or Supabase CLI on this machine. To run DDL migrations:

1. Open: `https://supabase.com/dashboard/project/aqxgnvjqabitfvcnboah`
2. Go to SQL Editor
3. Paste the SQL from the migration file
4. Click **Run**
