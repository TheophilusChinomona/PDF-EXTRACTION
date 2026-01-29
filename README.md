# PDF-Extraction Service

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100.0-teal)

A high-performance, hybrid AI microservice for extracting structured data from academic PDFs, combining local OCR speed with Gemini Vision's semantic understanding.

## 📖 Description

The **PDF-Extraction Service** (also known as the Academy Scrapper AI Sidecar) solves the challenge of extracting structured metadata from unstructured academic documents, such as exam papers. Traditional OCR often fails on complex layouts, mathematical formulas, and multi-column text.

This project implements a **hybrid pipeline**:
1.  **Fast Path**: Uses local **OpenDataLoader** for rapid structure and text extraction.
2.  **Smart Routing**: Analyzes extraction quality in real-time.
3.  **AI Fallback**: Seamlessly escalates complex pages to **Google Gemini 3 Vision** for human-level understanding.

**Key Features:**
*   **Hybrid Architecture**: Reduces costs by ~80% by only using expensive AI models when necessary.
*   **Batch Processing**: Asynchronous processing for bulk uploads (up to 100 files).
*   **Review Queue**: Built-in workflow for flagging and manually resolving low-confidence extractions.
*   **Structured Output**: 100% compliant JSON schema output for easy integration.
*   **Supabase Integration**: Native synchronization with Supabase for data persistence.

## 📑 Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Quick Start](#quick-start)
- [API Documentation](#api-documentation)
- [Development](#development)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Contributing](#contributing)

## ✅ Prerequisites

Before you begin, ensure you have the following:

*   **Python 3.11+** installed on your machine.
*   **Docker & Docker Compose** (optional, for containerized deployment).
*   A **Google Cloud Project** with the Gemini API enabled and an API key.
*   A **Supabase Project** with URL and Service Role/Anon key.

## 🛠️ Installation

### Option A: Docker (Recommended)

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/TheophilusChinomona/pdf-extraction.git
    cd pdf-extraction
    ```

2.  **Configure Environment:**
    Create a `.env` file from the example:
    ```bash
    cp .env.example .env
    ```
    Edit `.env` and add your keys:
    ```env
    GEMINI_API_KEY=your_gemini_key
    SUPABASE_URL=your_supabase_url
    SUPABASE_KEY=your_supabase_key
    ```

3.  **Run with Docker Compose:**
    ```bash
    docker-compose up --build
    ```
    The API will be available at `http://localhost:8000`.

### Option B: Local Setup

1.  **Create a Virtual Environment:**
    ```bash
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # Linux/Mac
    source venv/bin/activate
    ```

2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## ⚙️ Configuration

The application is configured via environment variables.

| Variable | Description | Default |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | **Required**. Your Google Gemini API key. | - |
| `SUPABASE_URL` | **Required**. Your Supabase project URL. | - |
| `SUPABASE_KEY` | **Required**. Supabase Anon or Service Role key. | - |
| `MODEL_NAME` | Gemini model version to use. | `gemini-3-flash-preview` |
| `ENABLE_HYBRID_MODE` | Enable local OCR + AI routing. Set `false` for AI-only. | `true` |
| `QUALITY_THRESHOLD` | Confidence score (0-1) to trigger AI fallback. | `0.7` |
| `MAX_FILE_SIZE_MB` | Maximum allowed upload size. | `200` |
| `BATCH_WORKERS` | Number of PDFs to process concurrently (CLI). | `1` |
| `BATCH_API_LIMIT` | Max concurrent Gemini API calls (CLI). | `3` |

## 🚀 Quick Start

### 1. Check Service Health
Ensure all systems are operational:
```bash
curl http://localhost:8000/health
```

### 2. Extract a Single PDF
Upload a local file for extraction:
```bash
curl -X POST "http://localhost:8000/api/extract" \
     -F "file=@/path/to/exam_paper.pdf"
```

**Response:**
```json
{
  "id": "550e8400-e29b...",
  "status": "completed",
  "metadata": {
    "subject": "Mathematics",
    "year": 2023,
    "grade": 12
  },
  "confidence_score": 0.98
}
```

### 3. Batch Process Local PDFs (CLI)

For bulk local file processing, use the built-in CLI tool with parallel processing support:

```bash
# Process all document_*.pdf files in Sample PDFS/ directory (sequential)
python -m app.cli batch-process

# Process with 5 workers in parallel
python -m app.cli batch-process --workers 5

# Process custom directory with specific pattern
python -m app.cli batch-process --directory /path/to/pdfs --pattern "*.pdf"

# Control API concurrency (prevent rate limits)
python -m app.cli batch-process --workers 10 --api-limit 3

# Get help
python -m app.cli batch-process --help
```

**CLI Options:**
- `--directory, -d`: Directory containing PDFs (default: Sample PDFS/)
- `--pattern, -p`: Glob pattern for PDF files (default: document_*.pdf)
- `--workers, -w`: Number of PDFs to process in parallel (default: 1)
- `--api-limit, -a`: Max concurrent Gemini API calls (default: 3)

**Performance:**
- Sequential (`--workers 1`): ~60s per PDF
- Parallel (`--workers 5`): ~4-5x faster for batches
- API limit prevents hitting Gemini rate quotas

**Output:**
- Renames PDFs to canonical filenames (e.g., `4257c821-business-studies-p1-gr12-may-june-2025-mg.pdf`)
- Saves JSON extraction results alongside each PDF
- Generates `_batch_summary.json` with overall statistics

## 📚 API Documentation

Once the server is running, interactive documentation is available:

*   **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
*   **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Key Endpoints

*   `POST /api/extract` - Upload and process a single PDF.
*   `POST /api/batch` - Upload multiple PDFs for background processing.
*   `GET /api/extractions/{id}` - Retrieve results for a specific job.
*   `GET /api/review-queue` - List items requiring manual review.

## 💻 Development

### Setup Development Environment
Follow the "Local Setup" instructions above.

### Running Tests
We use `pytest` for unit and integration testing.

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=app

# Run type checking
mypy app/
```

### Project Structure

```text
pdf-extraction/
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── cli.py               # CLI commands (batch processing, etc.)
│   ├── __main__.py          # Module entry point (python -m app.cli)
│   ├── config.py            # Environment configuration
│   ├── routers/             # API endpoints (extract, batch, etc.)
│   ├── services/            # Core logic (PDF extractor, batch processor, etc.)
│   │   ├── batch_processor.py   # Local file batch processing
│   │   ├── pdf_extractor.py     # PDF extraction logic
│   │   ├── memo_extractor.py    # Memo extraction logic
│   │   └── ...
│   ├── models/              # Pydantic data schemas
│   ├── db/                  # Database interactions
│   └── utils/               # Shared utilities (retry logic, etc.)
├── scripts/                 # Development scripts (Ralph agent, etc.)
├── tests/                   # Test suite
├── docker-compose.yml       # Container orchestration
└── requirements.txt         # Project dependencies
```


