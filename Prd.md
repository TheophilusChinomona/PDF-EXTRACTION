# Product Requirements Document: Academy Scrapper AI Sidecar (Python/FastAPI)

---

### 1. Introduction/Overview

The **Academy Scrapper AI Sidecar** is a high-performance extraction service designed to solve the problem of unstructured data in academic PDFs. While the primary crawler successfully retrieves exam papers, the layout of these documents varies wildly by year and institution. This module uses **Gemini 3/2.0 Pro's** multimodal (Vision) capabilities to "read" these PDFs and convert them into structured, searchable data for the **Academy Scrapper** ecosystem.

---

### 2. Goals

* **Structured Output:** Convert 100% of processed PDFs into a valid, predefined JSON schema.
* **Model Superiority:** Implement **Gemini 3** (or 2.0 Pro) Vision to handle complex mathematical formulas and multi-column layouts that standard OCR fails on.
* **Isolation:** Operate as a standalone FastAPI service to prevent extraction heavy-lifting from slowing down the main crawling process.
* **Verification:** Provide a local-first testing loop where extraction results are saved to a local directory for review before cloud synchronization.

---

### 3. User Stories

### US-001: Local Vision-Based PDF Extraction

**Description:** As a developer, I want to send a local PDF to a Python script that calls the Gemini Vision API so that I can verify the AI's ability to extract subject, year, and question data without a database.

**Acceptance Criteria:**

* [ ] Script successfully converts PDF pages to images or bytes for Gemini Vision ingestion.
* [ ] The model returns a structured JSON object containing `subject`, `year`, `grade`, and `total_marks`.
* [ ] Extracted JSON is saved to a local `outputs/` folder with the same name as the source PDF.
* [ ] Error handling logs a clear message if the Gemini API key is missing or invalid.

---

### US-002: FastAPI Endpoint for Sidecar Integration

**Description:** As a developer, I want a FastAPI POST endpoint that accepts a file path or URL so that the module can eventually be called as a sidecar by the main crawler.

**Acceptance Criteria:**

* [ ] Endpoint `/extract` accepts a JSON payload with a `file_path` or `supabase_url`.
* [ ] The service returns a `202 Accepted` status immediately with a `job_id` for asynchronous processing.
* [ ] Validation logic ensures only `.pdf` files are processed.
* [ ] Pydantic models are used to enforce the structure of the API request and response.

---

### US-003: Supabase Data Persistence

**Description:** As a developer, I want the extracted JSON data to be upserted into my Supabase SQL database so that the "Academy Scrapper" frontend can display the metadata.

**Acceptance Criteria:**

* [ ] The module connects to Supabase using `supabase-py` and environment variables.
* [ ] Successfully inserts extracted fields into the `processed_papers` table.
* [ ] If a record for the file already exists, the module updates the record rather than creating a duplicate.
* [ ] Any extraction failures are recorded in a `failed_jobs` table in Supabase for later debugging.

---

### 4. Proposed Project Structure (Python)

```text
academy-scrapper-ai/
├── src/
│   ├── api/
│   │   ├── main.py          # FastAPI entry point
│   │   └── routes.py        # /extract endpoint logic
│   ├── services/
│   │   ├── gemini_client.py # Gemini 3/2.0 API integration
│   │   └── supabase_db.py   # Supabase client and CRUD operations
│   ├── utils/
│   │   ├── pdf_processor.py # PDF to Image conversion
│   │   └── schemas.py       # Pydantic models for JSON output
│   └── .env                 # API Keys (GEMINI_API_KEY, SUPABASE_URL, etc.)
├── tests/
│   └── test_extraction.py   # Local testing scripts
├── outputs/                 # Local JSON results for Phase 1
├── requirements.txt
└── README.md

```

---

### 5. Gemini System Prompt (Draft)

To ensure Gemini 3 performs as a sidecar extractor, we will use a **System Instruction**:

> "You are an expert academic document parser. Your task is to analyze the provided images of an exam paper PDF. Extract the following information into a strict JSON format:
> 1. `subject`: The name of the subject.
> 2. `year`: The year of the exam.
> 3. `grade`: The school grade level.
> 4. `total_marks`: The total marks possible.
> 5. `questions`: An array of objects containing `question_number`, `text`, and `marks_allocated`.
> 
> 
> If a value is not found, use `null`. Do not include any conversational text or markdown formatting in your response—output ONLY valid JSON."

Here is the updated PRD following your specific structure and the technical requirements for a **Python/FastAPI** sidecar using the latest **Gemini 3 Vision** capabilities.

## Step 2: PRD Structure

### 1. Introduction/Overview

The **Academy Scrapper AI Sidecar** is a Python-based microservice designed to handle the complex extraction of data from academic PDF exam papers. Traditional scrapers struggle with varied document layouts; this sidecar uses **Gemini 3 Pro’s** multimodal vision to "read" document images and output structured JSON. It acts as an isolated extraction brain, allowing the main crawler to focus on discovery and downloading.

### 2. Goals

* **Vision-First Extraction:** Use Gemini 3 Vision to maintain 95%+ accuracy on complex layouts (tables, diagrams, handwritten marks).
* **FastAPI Integration:** Provide a high-performance REST API for the main scraper to trigger extraction jobs.
* **Structured Output:** Guarantee all responses follow a strict Pydantic-validated JSON schema.
* **Asynchronous Processing:** Handle long-running AI extractions without blocking the main scraper's flow.

### 3. User Stories

### US-001: Local Multimodal PDF Processing

**Description:** As a developer, I want to process a local PDF by converting its pages to images and sending them to Gemini 3 so that I can verify extraction accuracy before moving to the cloud.

**Acceptance Criteria:**

* [ ] Script uses `pdf2image` to convert PDF pages into high-res JPEGs.
* [ ] Images are successfully passed as `Content` parts to the `google-genai` SDK.
* [ ] The output is valid JSON matching the `ExamPaper` schema.
* [ ] Results are saved to a local `test_outputs/` directory.

### US-002: FastAPI Extraction Endpoint

**Description:** As a developer, I want a `/v1/extract` endpoint that accepts a file path or URL so that the sidecar can be integrated into the Scrapper workflow.

**Acceptance Criteria:**

* [ ] POST endpoint `/v1/extract` accepts a payload with `source_path`.
* [ ] Endpoint returns a `job_id` and processing status immediately.
* [ ] The service implements basic rate-limiting to prevent hitting Gemini API quotas.
* [ ] Pydantic validation ensures the request body is correctly formatted.

### US-003: Supabase Data Synchronization

**Description:** As a developer, I want the sidecar to automatically update my Supabase database once extraction is complete so the data is ready for the CRM/LMS.

**Acceptance Criteria:**

* [ ] Successfully connects to Supabase using `supabase-py`.
* [ ] Upserts extracted metadata (Subject, Year, Grade) into the `papers` table.
* [ ] Updates the `extraction_status` from 'pending' to 'completed' in Supabase.
* [ ] **Verify in browser using dev-browser skill** (to check Supabase dashboard records during testing).

---

### Project Structure (Python/FastAPI)

```text
academy-scrapper-ai/
├── src/
│   ├── main.py              # FastAPI Entry Point
│   ├── api/
│   │   └── routes.py        # API Endpoints
│   ├── services/
│   │   ├── gemini_vision.py # Gemini 3 API Logic
│   │   └── supabase_svc.py  # Supabase Client
│   ├── utils/
│   │   ├── pdf_utils.py     # PDF-to-Image conversion
│   │   └── schemas.py       # Pydantic models (ExamPaper, Question)
│   └── config.py            # Env variables (API Keys)
├── tests/
│   └── test_gemini.py       # Local testing script
├── requirements.txt
└── .env

```

---

### The Gemini 3 Vision "System Prompt"

Since you are using **Gemini 3**, we will utilize the `thinking_config` to ensure the model reasons through the document structure before outputting JSON.

**System Instruction:**

> "You are an elite academic data extractor. Analyze the provided images of an exam paper.
> 1. Identify the Subject, Year, Grade, and Total Marks.
> 2. List every question, including its number and marks assigned.
> 3. Output the result in a RAW JSON object.
> 4. Do not include markdown blocks or preamble.
> 5. If a diagram is present, describe it briefly in a 'context' field for that question."
> 
> 

---

### Implementation Snippet: `gemini_vision.py`

Using the 2026 `google-genai` SDK:

```python
from google import genai
from google.genai import types

client = genai.Client(api_key="YOUR_GEMINI_API_KEY")

def extract_paper_data(images):
    # Gemini 3 Pro supports 'Thinking' levels for complex PDFs
    config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MEDIUM),
        response_mime_type="application/json"
    )
    
    response = client.models.generate_content(
        model="gemini-3-pro-preview",
        contents=["Extract the exam details from these images:", *images],
        config=config
    )
    return response.text

```
