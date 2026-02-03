# Testing Guidelines

## Overview
Testing approach for the PDF extraction service.

---

## Test Command

```bash
pytest tests/ -v --cov=app
```

---

## Local Development Testing

- Test Gemini API connection with sample PDF
- Verify extraction output matches expected schema
- Test error handling (invalid files, API failures)

---

## API Testing

- Health check endpoint (`/health`)
- Upload endpoint with valid/invalid PDFs
- Response schema validation

---

## Database Testing

- Supabase connection verification
- Insert/query operations
- Schema migrations
