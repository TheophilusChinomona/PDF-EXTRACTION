# Security Guidelines

## Overview
Security practices for PDF processing and API development.

---

## API Keys and Secrets

- **NEVER** hardcode API keys in source code
- Use `.env` file for all secrets (Gemini API key, Supabase URL/key)
- Load secrets via `python-dotenv` or FastAPI settings
- Verify `.env` is in `.gitignore`

---

## PDF Processing Safety

- Validate file uploads (size limits, file type verification)
- Sanitize file paths to prevent directory traversal
- Implement rate limiting on API endpoints
- Handle malformed PDFs gracefully

---

## Data Privacy

- No logging of extracted content without user consent
- Secure storage of API responses in Supabase
- Clear data retention policies

---

## Feature Checklist

Before completing any feature:

- [ ] No hardcoded secrets
- [ ] Input validation (file uploads, API parameters)
- [ ] Error handling doesn't leak sensitive info
- [ ] Rate limiting considered
- [ ] File operations validate paths
- [ ] HTTPS enforced in production
