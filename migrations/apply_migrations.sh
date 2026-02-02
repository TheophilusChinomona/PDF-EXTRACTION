#!/bin/bash
# Apply all migrations to Supabase database
# Usage: ./apply_migrations.sh

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "PDF Extraction Service - Database Migrations"
echo "=========================================="
echo ""

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo -e "${RED}ERROR: DATABASE_URL environment variable not set${NC}"
    echo ""
    echo "Please set your Supabase connection string:"
    echo "export DATABASE_URL=\"postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres\""
    echo ""
    echo "Or use SUPABASE_URL and SUPABASE_KEY:"
    echo "export SUPABASE_URL=\"https://[project-ref].supabase.co\""
    echo "export SUPABASE_KEY=\"your-service-role-key\""
    exit 1
fi

# Migration files in order
MIGRATIONS=(
    "001_create_extractions_table.sql"
    "002_create_review_queue_table.sql"
    "003_create_batch_jobs_table.sql"
    "004_create_memo_extractions_table.sql"
    "005_update_extractions_for_exam_papers.sql"
    "006_add_constraints_and_indexes.sql"
)

echo "Found ${#MIGRATIONS[@]} migration files"
echo ""

# Apply each migration
for migration in "${MIGRATIONS[@]}"; do
    echo -e "${YELLOW}Applying:${NC} $migration"

    if psql "$DATABASE_URL" -f "migrations/$migration" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Success${NC}"
    else
        echo -e "${RED}✗ Failed${NC}"
        echo "Migration failed. Stopping here."
        exit 1
    fi
    echo ""
done

echo "=========================================="
echo -e "${GREEN}All migrations applied successfully!${NC}"
echo "=========================================="
echo ""

# Verify tables exist
echo "Verifying tables..."
psql "$DATABASE_URL" -c "
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;
"

echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Update .env with SUPABASE_URL and SUPABASE_KEY"
echo "2. Run: pytest tests/ -v"
echo "3. Test extraction: python -m app.cli batch-process"
