@echo off
REM Apply all migrations to Supabase database
REM Usage: apply_migrations.bat

echo ==========================================
echo PDF Extraction Service - Database Migrations
echo ==========================================
echo.

REM Check if DATABASE_URL is set
if "%DATABASE_URL%"=="" (
    echo ERROR: DATABASE_URL environment variable not set
    echo.
    echo Please set your Supabase connection string:
    echo set DATABASE_URL=postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres
    echo.
    echo Or use SUPABASE_URL and SUPABASE_KEY:
    echo set SUPABASE_URL=https://[project-ref].supabase.co
    echo set SUPABASE_KEY=your-service-role-key
    exit /b 1
)

REM Apply migrations in order
echo Applying migration 001_create_extractions_table.sql...
psql "%DATABASE_URL%" -f "migrations\001_create_extractions_table.sql" >nul 2>&1
if errorlevel 1 (
    echo [FAILED] Migration 001 failed
    exit /b 1
)
echo [OK] Migration 001 complete

echo Applying migration 002_create_review_queue_table.sql...
psql "%DATABASE_URL%" -f "migrations\002_create_review_queue_table.sql" >nul 2>&1
if errorlevel 1 (
    echo [FAILED] Migration 002 failed
    exit /b 1
)
echo [OK] Migration 002 complete

echo Applying migration 003_create_batch_jobs_table.sql...
psql "%DATABASE_URL%" -f "migrations\003_create_batch_jobs_table.sql" >nul 2>&1
if errorlevel 1 (
    echo [FAILED] Migration 003 failed
    exit /b 1
)
echo [OK] Migration 003 complete

echo Applying migration 004_create_memo_extractions_table.sql...
psql "%DATABASE_URL%" -f "migrations\004_create_memo_extractions_table.sql" >nul 2>&1
if errorlevel 1 (
    echo [FAILED] Migration 004 failed
    exit /b 1
)
echo [OK] Migration 004 complete

echo Applying migration 005_update_extractions_for_exam_papers.sql...
psql "%DATABASE_URL%" -f "migrations\005_update_extractions_for_exam_papers.sql" >nul 2>&1
if errorlevel 1 (
    echo [FAILED] Migration 005 failed
    exit /b 1
)
echo [OK] Migration 005 complete

echo Applying migration 006_add_constraints_and_indexes.sql...
psql "%DATABASE_URL%" -f "migrations\006_add_constraints_and_indexes.sql" >nul 2>&1
if errorlevel 1 (
    echo [FAILED] Migration 006 failed
    exit /b 1
)
echo [OK] Migration 006 complete

echo.
echo ==========================================
echo All migrations applied successfully!
echo ==========================================
echo.

echo Verifying tables...
psql "%DATABASE_URL%" -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name;"

echo.
echo Setup complete!
echo.
echo Next steps:
echo 1. Update .env with SUPABASE_URL and SUPABASE_KEY
echo 2. Run: pytest tests/ -v
echo 3. Test extraction: python -m app.cli batch-process
