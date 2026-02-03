# Architecture

## Overview
Hybrid extraction pipeline architecture and file organization.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11+, FastAPI |
| AI/ML | Google Gemini 3 API + OpenDataLoader PDF |
| Database | Supabase (PostgreSQL) |
| Key Libraries | opendataloader-pdf, google-genai, fastapi, supabase-py, pydantic |

---

## Hybrid Pipeline

| Component | Role | Performance |
|-----------|------|-------------|
| **OpenDataLoader** (local) | PDF structure, tables, bounding boxes | 0.05s/page, $0 cost, F1: 0.93 |
| **Gemini 3 API** (cloud) | Semantic analysis | 80% cost reduction vs pure AI |

---

## File Organization

```
pdf-extraction/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── routers/             # API route handlers
│   ├── services/            # Business logic (PDF processing, Gemini)
│   ├── models/              # Pydantic schemas
│   ├── db/                  # Database clients and queries
│   └── config.py            # Configuration management
├── tests/                   # Unit and integration tests
├── .env                     # Environment variables (NEVER commit)
└── requirements.txt         # Python dependencies
```

---

## Routing Logic

```
PDF Input
    │
    ▼
OpenDataLoader (local extraction)
    │
    ▼
Quality Score Check
    │
    ├── score >= 0.7 → Gemini Text Analysis (80% cheaper)
    │
    └── score < 0.7  → Gemini Vision Fallback
    │
    ▼
Merge Results + Store in Supabase
```
