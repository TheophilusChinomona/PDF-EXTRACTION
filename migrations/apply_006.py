"""
Apply migration 006_add_constraints_and_indexes.sql to the database.

Uses DATABASE_URL (PostgreSQL connection string) from environment or .env.
Requires: pip install psycopg2-binary python-dotenv

Alternatively, run the SQL manually in Supabase Dashboard → SQL Editor.
"""

import os
import sys
from pathlib import Path

# Load .env from project root
root = Path(__file__).resolve().parent.parent
dotenv_path = root / ".env"
if dotenv_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL is not set.", file=sys.stderr)
    print("Set it to your Supabase Postgres connection string, e.g.:", file=sys.stderr)
    print("  DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres", file=sys.stderr)
    print("Or run the migration manually:", file=sys.stderr)
    print(f"  1. Open Supabase Dashboard → SQL Editor", file=sys.stderr)
    print(f"  2. Paste contents of: {Path(__file__).parent / '006_add_constraints_and_indexes.sql'}", file=sys.stderr)
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("psycopg2 is not installed. Install it with: pip install psycopg2-binary", file=sys.stderr)
    print("Or run the SQL manually in Supabase Dashboard → SQL Editor.", file=sys.stderr)
    sys.exit(1)

migration_path = Path(__file__).parent / "006_add_constraints_and_indexes.sql"
sql = migration_path.read_text()

print("Applying migration 006_add_constraints_and_indexes.sql...")
try:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.close()
    print("Migration 006 applied successfully.")
except Exception as e:
    print(f"Migration failed: {e}", file=sys.stderr)
    sys.exit(1)
