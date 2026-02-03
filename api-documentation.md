# PDF Extraction Service - API Documentation

**Version:** 1.0.0
**Base URL:** `/api` (e.g., `http://localhost:8000/api`)
**Protocol:** REST/JSON

---

## Table of Contents

1. [Overview](#1-overview)
2. [Authentication](#2-authentication)
3. [Rate Limiting](#3-rate-limiting)
4. [Endpoints](#4-endpoints)
   - [System Endpoints](#41-system-endpoints)
   - [Extraction Endpoints](#42-extraction-endpoints)
   - [Batch Processing](#43-batch-processing)
   - [Review Queue](#44-review-queue)
   - [Statistics](#45-statistics)
5. [Data Models](#5-data-models)
6. [Error Handling](#6-error-handling)
7. [Webhooks](#7-webhooks)
8. [Integration Examples](#8-integration-examples)

---

## 1. Overview

The PDF Extraction Service provides a RESTful API for extracting structured data from academic exam papers and marking guidelines (memos). It's designed to be integrated as a microservice in your backend architecture.

### Key Features

- **Automatic Document Classification**: Identifies exam papers vs memos
- **Hybrid Processing**: Local parsing + AI semantic analysis
- **Structured Output**: JSON with complete question hierarchies
- **Bounding Boxes**: PDF coordinates for frontend highlighting
- **Batch Processing**: Async processing for multiple files
- **Cost Optimization**: 80% savings through intelligent routing

### Architecture

```
Your Backend → PDF Extraction Service → [OpenDataLoader + Gemini 3] → Supabase
```

---

## 2. Authentication

**Current Status:** Open API (no authentication required)

### Production Recommendations

For production deployments, implement authentication at one of these layers:

**Option 1: API Gateway**
```
Frontend → Your Backend (authenticated) → API Gateway → PDF Service
```

**Option 2: Shared Secret**
```typescript
// In your backend
const response = await fetch('http://pdf-service:8000/api/extract', {
  headers: {
    'X-API-Key': process.env.PDF_SERVICE_SECRET
  }
});
```

**Option 3: Network Security**
- Deploy service on private network
- Use firewall rules to restrict access
- Configure `ALLOWED_ORIGINS` in `.env`

---

## 3. Rate Limiting

Rate limits are enforced per IP address using `slowapi`.

### Limits

| Endpoint Type | Limit | Window |
|--------------|-------|--------|
| Extraction Upload | 10 requests | per minute |
| Batch Upload | 2 requests | per minute |
| Read Operations | 100 requests | per minute |
| Health Check | 200 requests | per minute |

### Headers

Every response includes rate limit headers:

```http
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1640995200
```

### Rate Limit Exceeded Response

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 45

{
  "detail": "Rate limit exceeded: 10 per 1 minute"
}
```

---

## 4. Endpoints

### 4.1. System Endpoints

#### Health Check

**`GET /health`**

Verifies operational status of all services.

**Response: 200 OK**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-29T10:30:00Z",
  "services": {
    "opendataloader": "healthy",
    "gemini_api": "healthy",
    "supabase": "healthy"
  },
  "version": "1.0.0"
}
```

**Response: 503 Service Unavailable**
```json
{
  "status": "unhealthy",
  "timestamp": "2026-01-29T10:30:00Z",
  "services": {
    "opendataloader": "healthy",
    "gemini_api": "unhealthy",
    "supabase": "healthy"
  }
}
```

---

#### Version Info

**`GET /version`**

Returns API version and build information.

**Response: 200 OK**
```json
{
  "version": "1.0.0",
  "commit_hash": "development"
}
```

---

### 4.2. Extraction Endpoints

#### Extract PDF

**`POST /api/extract`**

Upload and process a single PDF file. Automatically classifies document type (exam paper or memo) and extracts structured data.

**Rate Limit:** 10 requests/minute

**Request:**
```http
POST /api/extract
Content-Type: multipart/form-data

file: [PDF binary data]
webhook_url: https://your-backend.com/webhook (optional)
```

**cURL Example:**
```bash
curl -X POST http://localhost:8000/api/extract \
  -F "file=@path/to/exam_paper.pdf" \
  -F "webhook_url=https://example.com/callback"
```

**Response: 201 Created**
```http
HTTP/1.1 201 Created
X-Extraction-ID: 550e8400-e29b-41d4-a716-446655440000
X-Processing-Method: hybrid
X-Quality-Score: 0.94
X-Document-Type: question_paper
Content-Type: application/json

{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "subject": "Business Studies",
  "syllabus": "NSC",
  "year": 2023,
  "session": "MAY/JUNE",
  "grade": 12,
  "language": "English",
  "total_marks": 150,
  "groups": [
    {
      "group_id": "SECTION A",
      "title": "SECTION A: COMPULSORY",
      "instructions": "Answer ALL questions in this section.",
      "questions": [
        {
          "id": "1.1.1",
          "parent_id": "1.1",
          "text": "Choose the correct answer from the options below.",
          "marks": 1,
          "options": [
            {
              "label": "A",
              "text": "Human resources"
            },
            {
              "label": "B",
              "text": "Financial resources"
            }
          ]
        }
      ]
    }
  ],
  "processing_metadata": {
    "processing_method": "hybrid",
    "quality_score": 0.94,
    "cache_hit": true,
    "total_tokens": 1500,
    "cached_tokens": 850,
    "document_type": "question_paper"
  }
}
```

**Response Headers:**
- `X-Extraction-ID`: UUID for retrieving results later
- `X-Processing-Method`: `hybrid` or `vision_fallback`
- `X-Quality-Score`: OpenDataLoader quality (0.0-1.0)
- `X-Document-Type`: `question_paper` or `memo`

**Error Responses:**

**400 Bad Request** - Invalid file or missing file
```json
{
  "detail": "No file provided"
}
```

**413 Payload Too Large** - File exceeds 200MB
```json
{
  "detail": "File size exceeds maximum allowed size of 200MB"
}
```

**422 Unprocessable Entity** - Corrupted or invalid PDF
```json
{
  "detail": "File is not a valid PDF or is corrupted"
}
```

**429 Too Many Requests** - Rate limit exceeded
```json
{
  "detail": "Rate limit exceeded: 10 per 1 minute"
}
```

---

#### Get Extraction Result

**`GET /api/extractions/{extraction_id}`**

Retrieve a completed extraction by its UUID.

**Rate Limit:** 100 requests/minute

**Request:**
```http
GET /api/extractions/550e8400-e29b-41d4-a716-446655440000
```

**Response: 200 OK**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "subject": "Business Studies",
  "status": "completed",
  "groups": [...],
  "created_at": "2026-01-29T10:00:00Z"
}
```

**Response: 404 Not Found**
```json
{
  "detail": "Extraction not found: 550e8400-e29b-41d4-a716-446655440000"
}
```

---

#### List Extractions

**`GET /api/extractions`**

Retrieve a paginated list of all extractions.

**Rate Limit:** 100 requests/minute

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 50 | Max records (1-100) |
| `offset` | integer | No | 0 | Records to skip |
| `status_filter` | string | No | - | Filter by status: `completed`, `failed`, `pending`, `partial` |

**Request:**
```http
GET /api/extractions?limit=20&offset=0&status_filter=completed
```

**Response: 200 OK**
```json
{
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "subject": "Business Studies",
      "year": 2023,
      "grade": 12,
      "status": "completed",
      "created_at": "2026-01-29T10:00:00Z"
    }
  ],
  "pagination": {
    "limit": 20,
    "offset": 0,
    "count": 15,
    "has_more": false
  }
}
```

---

#### Get Bounding Boxes

**`GET /api/extractions/{extraction_id}/bounding-boxes`**

Retrieve PDF coordinates for all extracted elements. Useful for frontend highlighting.

**Rate Limit:** 100 requests/minute

**Request:**
```http
GET /api/extractions/550e8400-e29b-41d4-a716-446655440000/bounding-boxes
```

**Response: 200 OK**
```json
{
  "question_1.1.1": {
    "x1": 72.5,
    "y1": 150.0,
    "x2": 520.0,
    "y2": 180.5,
    "page": 1
  },
  "section_a_title": {
    "x1": 72.5,
    "y1": 100.0,
    "x2": 300.0,
    "y2": 120.0,
    "page": 1
  }
}
```

---

#### Get Element Details

**`GET /api/extractions/{extraction_id}/elements/{element_id}`**

Retrieve specific element data with its bounding box.

**Rate Limit:** 100 requests/minute

**Request:**
```http
GET /api/extractions/550e8400-e29b-41d4-a716-446655440000/elements/question_1.1.1
```

**Response: 200 OK**
```json
{
  "element_id": "question_1.1.1",
  "element_type": "question",
  "bounding_box": {
    "x1": 72.5,
    "y1": 150.0,
    "x2": 520.0,
    "y2": 180.5,
    "page": 1
  },
  "content": {
    "id": "1.1.1",
    "text": "Choose the correct answer...",
    "marks": 1
  }
}
```

---

#### Retry Failed Extraction

**`POST /api/extractions/{extraction_id}/retry`**

Retry a failed or partial extraction.

**Rate Limit:** 10 requests/minute

**Request:**
```http
POST /api/extractions/550e8400-e29b-41d4-a716-446655440000/retry
```

**Response: 200 OK**
```json
{
  "message": "Extraction retry initiated",
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing"
}
```

---

### 4.3. Batch Processing

#### Create Batch Job

**`POST /api/batch`**

Upload multiple PDFs for asynchronous processing.

**Rate Limit:** 2 requests/minute

**Request:**
```http
POST /api/batch
Content-Type: multipart/form-data

files: [PDF 1]
files: [PDF 2]
files: [PDF 3]
webhook_url: https://your-backend.com/webhook (optional)
```

**cURL Example:**
```bash
curl -X POST http://localhost:8000/api/batch \
  -F "files=@paper1.pdf" \
  -F "files=@paper2.pdf" \
  -F "webhook_url=https://example.com/callback"
```

**Response: 202 Accepted**
```json
{
  "batch_job_id": "770e8400-e29b-41d4-a716-446655440000",
  "status_url": "/api/batch/770e8400-e29b-41d4-a716-446655440000",
  "total_files": 2,
  "status": "processing",
  "message": "Batch job created successfully. Processing 2 files."
}
```

**Error Responses:**

**400 Bad Request** - Too many files
```json
{
  "detail": "Maximum 100 files allowed per batch"
}
```

---

#### Get Batch Job Status

**`GET /api/batch/{batch_job_id}`**

Check the progress of a batch processing job.

**Rate Limit:** 100 requests/minute

**Request:**
```http
GET /api/batch/770e8400-e29b-41d4-a716-446655440000
```

**Response: 200 OK**
```json
{
  "id": "770e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "total_files": 10,
  "completed_files": 9,
  "failed_files": 1,
  "routing_stats": {
    "hybrid": 7,
    "vision_fallback": 2,
    "pending": 0
  },
  "extraction_ids": [
    "550e8400-e29b-41d4-a716-446655440001",
    "550e8400-e29b-41d4-a716-446655440002"
  ],
  "cost_estimate_usd": 0.45,
  "cost_savings_usd": 1.80,
  "created_at": "2026-01-29T10:00:00Z",
  "completed_at": "2026-01-29T10:15:00Z"
}
```

**Status Values:**
- `pending`: Job created, not started
- `processing`: Currently processing files
- `completed`: All files processed successfully
- `partial`: Some files failed
- `failed`: All files failed

---

#### List Batch Jobs

**`GET /api/batch`**

List all batch jobs with pagination.

**Rate Limit:** 100 requests/minute

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 50 | Max records (1-100) |
| `offset` | integer | No | 0 | Records to skip |
| `status` | string | No | - | Filter by: `pending`, `processing`, `completed`, `partial`, `failed` |

**Response: 200 OK**
```json
{
  "data": [...],
  "pagination": {
    "limit": 50,
    "offset": 0,
    "count": 10,
    "has_more": false
  }
}
```

---

### 4.4. Review Queue

#### List Review Items

**`GET /api/review-queue`**

List extractions that failed and require manual review.

**Rate Limit:** 100 requests/minute

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 50 | Max records (1-100) |
| `offset` | integer | No | 0 | Records to skip |

**Response: 200 OK**
```json
{
  "data": [
    {
      "id": "review-001",
      "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
      "file_name": "corrupted_exam.pdf",
      "error_type": "low_confidence",
      "error_message": "Extraction confidence below threshold (0.45)",
      "created_at": "2026-01-29T10:00:00Z"
    }
  ],
  "pagination": {
    "limit": 50,
    "offset": 0,
    "count": 1,
    "has_more": false
  }
}
```

---

#### Resolve Review Item

**`POST /api/review-queue/{review_id}/resolve`**

Mark a review item as resolved after manual intervention.

**Rate Limit:** 10 requests/minute

**Request Body:**
```json
{
  "resolution": "fixed",
  "reviewer_notes": "Manually corrected metadata and re-extracted."
}
```

**Response: 200 OK**
```json
{
  "message": "Review item resolved successfully",
  "review_id": "review-001",
  "status": "resolved"
}
```

---

### 4.5. Statistics

#### Caching Statistics

**`GET /api/stats/caching`**

View context caching performance metrics.

**Rate Limit:** 100 requests/minute

**Response: 200 OK**
```json
{
  "total_requests": 1000,
  "cache_hits": 850,
  "cache_misses": 150,
  "hit_rate": 0.85,
  "tokens_saved": 425000,
  "cost_savings_usd": 85.50
}
```

---

#### Routing Statistics

**`GET /api/stats/routing`**

View distribution of processing methods.

**Rate Limit:** 100 requests/minute

**Response: 200 OK**
```json
{
  "total_extractions": 1000,
  "routing_breakdown": {
    "hybrid": 800,
    "vision_fallback": 200
  },
  "average_quality_score": 0.87,
  "cost_metrics": {
    "total_cost_usd": 45.00,
    "potential_cost_usd": 225.00,
    "savings_usd": 180.00,
    "savings_percent": 80
  }
}
```

---

## 5. Data Models

### FullExamPaper (Question Paper)

```typescript
interface FullExamPaper {
  // Metadata
  subject: string;                    // e.g., "Business Studies"
  syllabus: string;                   // "NSC" or "SC"
  year: number;                       // e.g., 2023
  session: string;                    // "MAY/JUNE" or "NOV"
  grade: number;                      // 10, 11, or 12
  language: string;                   // "English", "Afrikaans", etc.
  total_marks: number;                // Total exam marks

  // Question structure
  groups: QuestionGroup[];

  // Processing info
  processing_metadata?: {
    processing_method: string;        // "hybrid" or "vision_fallback"
    quality_score: number;            // 0.0 to 1.0
    cache_hit: boolean;
    total_tokens: number;
    cached_tokens?: number;
    document_type: string;            // "question_paper"
  };
}

interface QuestionGroup {
  group_id: string;                   // "SECTION A", "QUESTION 1"
  title: string;                      // Full heading text
  instructions?: string;              // Instructions for section/question
  questions: Question[];
}

interface Question {
  id: string;                         // "1.1.1", "2.3.2"
  parent_id?: string;                 // "1.1" for sub-questions
  text: string;                       // Actual question text
  marks?: number;                     // Marks allocated

  // Contextual fields
  scenario?: string;                  // Case study or word bank
  context?: string;                   // Framing text or diagram description

  // Type-specific structures
  options?: MultipleChoiceOption[];   // For MCQs
  match_data?: MatchData;            // For column matching
  guide_table?: Array<Record<string, string>>;  // For fill-in-blank
}

interface MultipleChoiceOption {
  label: string;                      // "A", "B", "C", "D"
  text: string;                       // Option content
}

interface MatchData {
  column_a_title: string;
  column_b_title: string;
  column_a_items: MatchColumnItem[];
  column_b_items: MatchColumnItem[];  // Includes distractors
}

interface MatchColumnItem {
  label: string;                      // "1.3.1" or "A"
  text: string;                       // Item content
}
```

---

### MarkingGuideline (Memo)

```typescript
interface MarkingGuideline {
  // Metadata
  subject: string;
  paper_number: string;               // "P1", "P2"
  session: string;                    // "MAY/JUNE" or "NOV"
  year: number;
  grade: number;
  total_marks: number;

  // Marking answers
  sections: MarkingSection[];

  // Processing info
  processing_metadata?: {
    processing_method: string;
    quality_score: number;
    document_type: string;            // "memo"
  };
}

interface MarkingSection {
  section_id: string;                 // "SECTION A"
  answers: Answer[];
}

interface Answer {
  question_id: string;                // "1.1.1"
  acceptable_answers: string[];       // All valid answers
  marks: number;
  marker_instruction?: string;        // "Mark the first TWO only"
  notes?: string;                     // Additional guidance
}
```

---

### BoundingBox

```typescript
interface BoundingBox {
  x1: number;          // Left coordinate (points)
  y1: number;          // Top coordinate (points)
  x2: number;          // Right coordinate (points)
  y2: number;          // Bottom coordinate (points)
  page: number;        // Page number (1-indexed)
}
```

---

### BatchJobStatus

```typescript
interface BatchJobStatus {
  id: string;                         // UUID
  status: "pending" | "processing" | "completed" | "partial" | "failed";
  total_files: number;
  completed_files: number;
  failed_files: number;
  routing_stats: {
    hybrid: number;
    vision_fallback: number;
    pending: number;
  };
  extraction_ids: string[];           // UUIDs of individual extractions
  cost_estimate_usd?: number;
  cost_savings_usd?: number;
  created_at: string;                 // ISO 8601
  completed_at?: string;              // ISO 8601
  webhook_url?: string;
}
```

---

## 6. Error Handling

### Standard Error Response

```json
{
  "detail": "Error description message"
}
```

### HTTP Status Codes

| Code | Meaning | When It Occurs |
|------|---------|----------------|
| **200** | OK | Request succeeded |
| **201** | Created | Resource created (extraction) |
| **202** | Accepted | Async operation started (batch) |
| **400** | Bad Request | Invalid parameters or malformed request |
| **404** | Not Found | Resource doesn't exist |
| **413** | Payload Too Large | File exceeds 200MB |
| **422** | Unprocessable Entity | PDF validation failed |
| **429** | Too Many Requests | Rate limit exceeded |
| **500** | Internal Server Error | Server-side error |
| **503** | Service Unavailable | Service health check failed |

### Error Examples

**Validation Error:**
```json
{
  "detail": [
    {
      "loc": ["body", "file"],
      "msg": "File is required",
      "type": "value_error.missing"
    }
  ]
}
```

**Rate Limit Error:**
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 45

{
  "detail": "Rate limit exceeded: 10 per 1 minute"
}
```

---

## 7. Webhooks

Register webhook URLs to receive asynchronous notifications when extractions complete.

### Webhook Security

**Recommendations:**
1. Use HTTPS endpoints only
2. Validate webhook signatures (implement in your backend)
3. Implement idempotency (same event may be sent twice)
4. Return 200 OK quickly (process async)

### Event: Extraction Completed

Sent when a single extraction finishes.

**Request to Your Webhook:**
```http
POST https://your-backend.com/webhook
Content-Type: application/json

{
  "event": "extraction_completed",
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "file_name": "exam_paper.pdf",
  "subject": "Business Studies",
  "grade": 12,
  "year": 2023,
  "confidence_score": 0.95,
  "processing_method": "hybrid",
  "timestamp": "2026-01-29T10:15:00Z"
}
```

**Your Response:**
```http
HTTP/1.1 200 OK
```

---

### Event: Batch Completed

Sent when a batch job finishes processing all files.

**Request to Your Webhook:**
```http
POST https://your-backend.com/webhook
Content-Type: application/json

{
  "event": "batch_completed",
  "batch_job_id": "770e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "summary": {
    "total_files": 10,
    "completed_files": 9,
    "failed_files": 1
  },
  "extraction_ids": [
    "550e8400-e29b-41d4-a716-446655440001",
    "550e8400-e29b-41d4-a716-446655440002"
  ],
  "timestamp": "2026-01-29T10:20:00Z"
}
```

---

## 8. Integration Examples

### Example 1: Node.js/Express Backend

```javascript
const express = require('express');
const FormData = require('form-data');
const axios = require('axios');
const multer = require('multer');

const app = express();
const upload = multer({ dest: 'uploads/' });

// Proxy extraction to PDF service
app.post('/api/upload-exam', upload.single('file'), async (req, res) => {
  try {
    const form = new FormData();
    form.append('file', fs.createReadStream(req.file.path));
    form.append('webhook_url', 'https://yourbackend.com/webhook');

    const response = await axios.post(
      'http://pdf-service:8000/api/extract',
      form,
      {
        headers: form.getHeaders(),
        timeout: 300000  // 5 minutes
      }
    );

    // Save to your database
    await db.exams.create({
      id: response.data.id,
      subject: response.data.subject,
      grade: response.data.grade,
      year: response.data.year,
      questions: response.data.groups
    });

    res.json({
      success: true,
      extraction_id: response.data.id,
      subject: response.data.subject
    });

  } catch (error) {
    if (error.response?.status === 429) {
      res.status(429).json({ error: 'Rate limit exceeded' });
    } else {
      res.status(500).json({ error: error.message });
    }
  }
});

// Webhook receiver
app.post('/webhook', express.json(), async (req, res) => {
  const { event, extraction_id, status } = req.body;

  if (event === 'extraction_completed' && status === 'completed') {
    // Update your database
    await db.exams.update(extraction_id, { status: 'ready' });

    // Notify frontend via WebSocket
    io.emit('extraction_ready', { extraction_id });
  }

  res.sendStatus(200);
});
```

---

### Example 2: Python/FastAPI Backend

```python
from fastapi import FastAPI, UploadFile, BackgroundTasks
import httpx

app = FastAPI()

PDF_SERVICE_URL = "http://pdf-service:8000"

@app.post("/upload-exam")
async def upload_exam(file: UploadFile, background_tasks: BackgroundTasks):
    """Proxy PDF upload to extraction service."""

    async with httpx.AsyncClient() as client:
        files = {
            "file": (file.filename, await file.read(), file.content_type)
        }
        data = {
            "webhook_url": "https://yourbackend.com/webhook"
        }

        response = await client.post(
            f"{PDF_SERVICE_URL}/api/extract",
            files=files,
            data=data,
            timeout=300.0
        )
        response.raise_for_status()
        result = response.json()

    # Save to database
    exam_id = await save_exam_to_db(result)

    return {
        "success": True,
        "extraction_id": result["id"],
        "exam_id": exam_id,
        "subject": result["subject"]
    }


@app.post("/webhook")
async def webhook(event_data: dict):
    """Receive extraction completion webhooks."""

    if event_data["event"] == "extraction_completed":
        extraction_id = event_data["extraction_id"]

        # Update database status
        await db.update_exam_status(extraction_id, "ready")

        # Trigger notifications
        await notify_user(extraction_id)

    return {"status": "received"}
```

---

### Example 3: React Frontend (via Your Backend)

```typescript
// Upload component
async function uploadExamPaper(file: File) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('/api/upload-exam', {
    method: 'POST',
    body: formData
  });

  if (!response.ok) {
    if (response.status === 429) {
      throw new Error('Rate limit exceeded. Please try again later.');
    }
    throw new Error('Upload failed');
  }

  const data = await response.json();
  return data.extraction_id;
}

// Display extracted questions
function ExamViewer({ extractionId }: { extractionId: string }) {
  const { data: exam } = useQuery(['exam', extractionId], async () => {
    const res = await fetch(`/api/exams/${extractionId}`);
    return res.json();
  });

  return (
    <div>
      <h1>{exam.subject} - Grade {exam.grade}</h1>
      <p>{exam.year} {exam.session}</p>

      {exam.groups.map(group => (
        <Section key={group.group_id}>
          <h2>{group.title}</h2>
          {group.questions.map(q => (
            <QuestionCard
              key={q.id}
              question={q}
              onHighlight={() => highlightInPDF(q.id)}
            />
          ))}
        </Section>
      ))}
    </div>
  );
}

// Highlight in PDF viewer
function highlightInPDF(questionId: string) {
  const bbox = bounding_boxes[questionId];
  if (bbox) {
    pdfViewer.highlightArea(bbox.page, {
      x1: bbox.x1,
      y1: bbox.y1,
      x2: bbox.x2,
      y2: bbox.y2
    });
  }
}
```

---

## Quick Reference

### Base URLs
- **Development:** `http://localhost:8000`
- **Production:** `https://your-domain.com`

### Interactive Docs
- **Swagger UI:** `/docs`
- **ReDoc:** `/redoc`

### Support
- **GitHub Issues:** https://github.com/yourusername/PDF-Extraction/issues
- **Email:** support@example.com

---

**Last Updated:** 2026-02-03
**API Version:** 1.0.0
