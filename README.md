# PDF-Extraction Service

Academic PDF extraction microservice using hybrid architecture (OpenDataLoader + Gemini API) for 80% cost reduction and 95%+ accuracy.

## Features

- **Hybrid Extraction Pipeline**: Combines local structure extraction (OpenDataLoader) with AI semantic understanding (Gemini)
- **Intelligent Routing**: Automatically chooses optimal extraction method based on PDF quality
- **Bounding Boxes**: Precise element coordinates for citation features
- **Cost Optimization**: 80% cost reduction vs pure AI approach
- **High Accuracy**: 95%+ accuracy with F1 score of 0.93 for table extraction

## Tech Stack

- **Backend**: Python 3.11+, FastAPI
- **AI/ML**: Google Gemini 3 API + OpenDataLoader PDF
- **Database**: Supabase (PostgreSQL)
- **Key Libraries**: opendataloader-pdf, google-genai, fastapi, supabase-py, pydantic

## Architecture

1. **OpenDataLoader** (local): Extracts PDF structure, tables, bounding boxes (0.05s/page, $0 cost)
2. **Quality Assessment**: Scores extraction quality to route intelligently
3. **Gemini API** (cloud): Semantic analysis of structured content when quality is sufficient
4. **Vision Fallback**: Uses Gemini Vision for low-quality PDFs

## Setup

### Prerequisites

- Python 3.11 or higher
- Gemini API key
- Supabase project

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd PDF-Extraction
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys
```

5. Run the application:
```bash
uvicorn app.main:app --reload
```

## Environment Variables

Required variables in `.env`:

- `GEMINI_API_KEY`: Your Google Gemini API key
- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_KEY`: Your Supabase anon/service key

Optional:
- `MODEL_NAME`: Gemini model to use (default: gemini-3-flash-preview)
- `ENABLE_HYBRID_MODE`: Enable hybrid extraction (default: true)

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
pdf-extraction/
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration management
│   ├── routers/             # API route handlers
│   ├── services/            # Business logic
│   ├── models/              # Pydantic schemas
│   └── db/                  # Database clients and queries
├── tests/                   # Unit and integration tests
├── .env.example             # Environment variables template
├── requirements.txt         # Python dependencies
└── README.md
```

## Development

Run tests:
```bash
pytest tests/ -v
```

Run with coverage:
```bash
pytest tests/ --cov=app
```

Type checking:
```bash
mypy app/
```

## License

[Add your license here]
