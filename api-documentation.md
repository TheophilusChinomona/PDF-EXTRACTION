# PDF Extraction Service API Documentation

## 1. Overview

The PDF Extraction Service is a high-performance academic PDF extraction microservice featuring a hybrid architecture. It combines **OpenDataLoader** for rapid structural analysis and **Gemini Pro** for semantic understanding, optimizing for both cost and quality.

- **Base URL**: `/api` (e.g., `http://localhost:8000/api`)
- **Version**: 1.0.0
- **Rate Limiting**: Enforced per IP address via `slowapi`.

### Capabilities
- **Hybrid Extraction**: Intelligent routing between local OCR and cloud Vision AI.
- **Batch Processing**: Handle bulk PDF uploads with status tracking.
- **Review Queue**: Manual verification workflow for low-confidence extractions.
- **Analytics**: Detailed caching and routing statistics.

---

## 2. Authentication

**Currently, the API is open and does not strictly enforce authentication.**

However, in a production environment, it is recommended to place this service behind an API Gateway or configure specific allowed origins in CORS settings.

*Security Note*: All endpoints are currently public. Ensure appropriate network security measures are in place.

---

## 3. Endpoints

### 3.1. System
#### Health Check
**Method**: `GET`
**Path**: `/health`
**Description**: Verifies the operational status of all dependent services (OpenDataLoader, Gemini API, Supabase).

**Response**:
- **200 OK**: All systems healthy.
- **503 Service Unavailable**: One or more services are down.

```json
{
  "status": "healthy",
  "timestamp": "2023-10-27T10:00:00Z",
  "services": {
    "opendataloader": "healthy",
    "gemini_api": "healthy",
    "supabase": "healthy"
  }
}
```

#### Version Info
**Method**: `GET`
**Path**: `/version`
**Description**: Returns current API version and commit hash.

**Response**:
```json
{
  "version": "1.0.0",
  "commit_hash": "development"
}
```

---

### 3.2. Extraction

#### Extract PDF
**Method**: `POST`
**Path**: `/api/extract`
**Description**: Upload a single PDF for extraction. Uses the hybrid pipeline to validate, extract, and store data.
**Rate Limit**: 10 requests/minute

**Request Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| file | File | Yes | PDF file (max 200MB) |
| webhook_url | string | No | HTTPS URL for completion notification |

**Example Request**:
```bash
curl -X POST http://localhost:8000/api/extract \
  -F "file=@/path/to/paper.pdf" \
  -F "webhook_url=https://my-webhook.com/callback"
```

**Response (201 Created)**:
Returns an `ExtractionResult` object (see Data Models).
**Headers**:
- `X-Extraction-ID`: UUID of the created extraction.
- `X-Processing-Method`: `hybrid`, `vision_fallback`, etc.

**Error Responses**:
- **422**: Invalid/Corrupted PDF.
- **413**: File too large.
- **429**: Rate limit exceeded.

#### Get Extraction Result
**Method**: `GET`
**Path**: `/api/extractions/{extraction_id}`
**Description**: Retrieve a completed extraction by its UUID.
**Rate Limit**: 100 requests/minute

**Response (200 OK)**:
Returns `ExtractionResult` JSON.

#### List Extractions
**Method**: `GET`
**Path**: `/api/extractions`
**Description**: Get a paginated list of extraction records.
**Rate Limit**: 100 requests/minute

**Query Parameters**:
| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| limit | int | No | Max records (1-100) | 50 |
| offset | int | No | Records to skip | 0 |
| status_filter | string | No | Filter by status (`completed`, `failed`, `pending`) | None |

**Response**:
```json
{
  "data": [ ... ],
  "pagination": {
    "limit": 50,
    "offset": 0,
    "count": 25,
    "has_more": false
  }
}
```

#### Get Bounding Boxes
**Method**: `GET`
**Path**: `/api/extractions/{extraction_id}/bounding-boxes`
**Description**: Retrieve map of element IDs to their PDF coordinates.

---

### 3.3. Batch Processing

#### Create Batch Job
**Method**: `POST`
**Path**: `/api/batch`
**Description**: Upload multiple PDFs (up to 100) for asynchronous processing.
**Rate Limit**: 2 requests/minute

**Request Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| files | File[] | Yes | List of PDF files |
| webhook_url | string | No | Webhook for batch completion |

**Example Request**:
```bash
curl -X POST http://localhost:8000/api/batch \
  -F "files=@paper1.pdf" \
  -F "files=@paper2.pdf"
```

**Response (202 Accepted)**:
```json
{
  "batch_job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status_url": "/api/batch/550e8400-e29b-41d4-a716-446655440000",
  "total_files": 2,
  "status": "processing"
}
```

#### Get Batch Status
**Method**: `GET`
**Path**: `/api/batch/{batch_job_id}`
**Description**: Check progress of a batch job.

**Response**:
Returns `BatchJobStatus` object.

---

### 3.4. Review Queue

#### List Review Items
**Method**: `GET`
**Path**: `/api/review-queue`
**Description**: List failed extractions requiring manual intervention.
**Rate Limit**: 100 requests/minute

#### Resolve Review
**Method**: `POST`
**Path**: `/api/review-queue/{review_id}/resolve`
**Description**: Mark a review item as resolved.

**Request Body**:
```json
{
  "resolution": "fixed",
  "reviewer_notes": "Manually corrected metadata."
}
```

---

### 3.5. Statistics

#### Caching Stats
**Method**: `GET`
**Path**: `/api/stats/caching`
**Description**: View cache hit rates and token savings.

#### Routing Stats
**Method**: `GET`
**Path**: `/api/stats/routing`
**Description**: View processing method distribution and cost metrics.

---

## 4. Data Models

### ExtractionResult
The core data structure returned by extraction endpoints.

```typescript
interface ExtractionResult {
  metadata: {
    title: string;
    authors: string[];
    journal?: string;
    year?: number;
    doi?: string;
  };
  abstract?: string;
  sections: Array<{
    heading: string;
    content: string;
    page_number: number;
    bbox?: BoundingBox;
  }>;
  tables: Array<{
    caption: string;
    page_number: number;
    data: Array<Record<string, any>>; // Row data
    bbox?: BoundingBox;
  }>;
  references: Array<{
    citation_text: string;
    authors: string[];
    year?: number;
    title?: string;
  }>;
  confidence_score: number; // 0.0 to 1.0
  bounding_boxes: Record<string, BoundingBox>;
  processing_metadata: Record<string, any>;
}

interface BoundingBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  page: number;
}
```

### BatchJobStatus

```typescript
interface BatchJobStatus {
  id: string; // UUID
  status: "pending" | "processing" | "completed" | "failed" | "partial";
  total_files: number;
  completed_files: number;
  failed_files: number;
  routing_stats: {
    hybrid: number;
    vision_fallback: number;
    pending: number;
  };
  extraction_ids: string[]; // UUIDs
  cost_estimate_usd?: number;
  cost_savings_usd?: number;
  created_at: string; // ISO Date
  webhook_url?: string;
}
```

---

## 5. Error Handling

The API uses standard HTTP status codes and a consistent JSON error format.

**Error Response Format**:
```json
{
  "detail": "Error description message"
}
```

**Common Status Codes**:
- **400 Bad Request**: Malformed request or invalid parameters (e.g., invalid UUID).
- **404 Not Found**: Resource (extraction, batch job) does not exist.
- **422 Unprocessable Entity**: The PDF file is corrupted or validation failed.
- **429 Too Many Requests**: Rate limit exceeded. Check `Retry-After` header.
- **500 Internal Server Error**: Server-side processing or database error.

---

## 6. Rate Limiting

The API implements rate limiting to ensure fair usage and prevent abuse.

| Scope | Limit |
|-------|-------|
| Extraction Upload | 10 per minute |
| Batch Upload | 2 per minute |
| Read Operations | 100 per minute |

**Headers**:
When a request is made, the following headers are included:
- `X-RateLimit-Limit`: The limit for the endpoint.
- `X-RateLimit-Remaining`: Requests remaining in the current window.
- `Retry-After`: (On 429) Seconds to wait before retrying.

---

## 7. Webhooks

Webhooks can be registered during **Extraction** or **Batch Creation** to receive asynchronous notifications.

**Event: Extraction Completed**
**Payload**:
```json
{
  "event": "extraction_completed",
  "extraction_id": "550e8400-e29b...",
  "status": "completed",
  "file_name": "paper.pdf",
  "metadata": { ... }, // Extracted metadata
  "confidence_score": 0.95
}
```

**Event: Batch Completed**
**Payload**:
```json
{
  "event": "batch_completed",
  "batch_job_id": "770e8400-e29b...",
  "status": "completed",
  "summary": {
    "total_files": 10,
    "completed_files": 9,
    "failed_files": 1
  }
}
```
