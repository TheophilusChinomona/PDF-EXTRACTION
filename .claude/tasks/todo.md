# Current Tasks: PDF-Extraction Project Setup

**Last Updated:** 2026-01-27
**Status:** Initial Setup

---

## Active Task: Initialize .claude Project Structure

### Initialization Checklist
- [x] Create `.claude/CLAUDE.md` with project-specific guidelines
- [x] Create `.claude/settings.json` with configuration
- [x] Create `.claude/tasks/template.md` for task tracking
- [x] Create `.claude/tasks/todo.md` (this file)
- [x] Create `.claude/tasks/archive/` directory
- [x] Create `.claude/skills/` directory with custom commands
- [x] Create `.claude/prompts/` directory with reusable prompts
- [x] Create `.claude/README.md` for quick reference

---

## Next Tasks: Project Implementation (From PRD)

### Phase 1: Project Structure Setup
- [ ] Create Python project directory structure
  - [ ] `app/` directory
  - [ ] `app/main.py`
  - [ ] `app/routers/`
  - [ ] `app/services/`
  - [ ] `app/models/`
  - [ ] `app/db/`
  - [ ] `app/config.py`
  - [ ] `tests/` directory
- [ ] Create `.gitignore` for Python project
- [ ] Create `requirements.txt` with dependencies
- [ ] Create `.env.example` template
- [ ] Set up Python virtual environment

### Phase 2: US-001 - Local PDF Extraction
- [ ] Install google-generativeai SDK
- [ ] Set up Gemini API client configuration
- [ ] Create extraction service (`app/services/gemini.py`)
- [ ] Define Pydantic schema for extracted data
- [ ] Create test script for local PDF processing
- [ ] Test with sample academic PDFs
- [ ] Validate output structure

### Phase 3: US-002 - FastAPI Service
- [ ] Create FastAPI application (`app/main.py`)
- [ ] Implement health check endpoint
- [ ] Create upload endpoint (`POST /extract`)
- [ ] Add file validation middleware
- [ ] Integrate Gemini extraction service
- [ ] Add error handling and logging
- [ ] Test API with Postman/curl
- [ ] Add API documentation (Swagger)

### Phase 4: US-003 - Supabase Integration
- [ ] Set up Supabase project
- [ ] Install supabase-py client
- [ ] Create database schema (extractions table)
- [ ] Implement Supabase client (`app/db/supabase.py`)
- [ ] Add data storage logic to API endpoint
- [ ] Test end-to-end flow (upload → extract → store)
- [ ] Add retrieval endpoint (`GET /extractions/{id}`)

### Phase 5: Testing and Documentation
- [ ] Write unit tests for extraction service
- [ ] Write integration tests for API endpoints
- [ ] Write tests for database operations
- [ ] Create README.md with setup instructions
- [ ] Document API endpoints
- [ ] Create deployment guide

---

## Backlog

### Future Enhancements
- [ ] Add batch processing endpoint
- [ ] Implement webhook notifications
- [ ] Add extraction result caching
- [ ] Create admin dashboard
- [ ] Add metrics and monitoring
- [ ] Implement authentication/authorization

---

## Blocked Items

**None currently**

---

## Notes

**PRD Reference:** See `Prd.md` in project root for detailed specifications

**Key Technologies:**
- Python 3.11+
- FastAPI
- Google Gemini 3 Vision API
- Supabase (PostgreSQL)
- Pydantic for data validation

**Security Reminders:**
- Never commit `.env` file
- Validate all file uploads
- Implement rate limiting
- Use HTTPS in production
