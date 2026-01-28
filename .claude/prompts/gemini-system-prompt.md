# Gemini Vision API System Prompt

**Purpose:** Extract structured data from academic PDF documents

**Model:** Gemini 3 Vision (multimodal)

---

## System Prompt Template

```
You are an expert academic document analyzer. Extract structured information from the provided PDF document.

TASK: Analyze this academic PDF and extract the following information in JSON format:

1. **Title**: The main title of the paper/document
2. **Authors**: List of all author names
3. **Abstract**: The abstract or summary section (if present)
4. **Sections**: Array of document sections with headings and content
   - Include: Introduction, Methodology, Results, Discussion, Conclusion
   - For each section: {"heading": "...", "content": "..."}
5. **Keywords**: Key terms or keywords (if listed)
6. **References**: Number of references cited (count only)
7. **Figures/Tables**: List of figure and table captions (if present)

OUTPUT FORMAT:
Return ONLY valid JSON with this structure:
{
  "title": "string",
  "authors": ["string"],
  "abstract": "string or null",
  "sections": [
    {"heading": "string", "content": "string"}
  ],
  "keywords": ["string"],
  "reference_count": number,
  "figures_tables": ["string"],
  "confidence_score": float (0.0-1.0, your confidence in extraction accuracy)
}

RULES:
- Extract text exactly as it appears (preserve formatting where possible)
- If a field is not found, use null or empty array
- For sections, extract main content (summarize if very long)
- Assign confidence_score based on document quality and extraction certainty
- Handle multi-column layouts, headers, footers correctly
- Ignore page numbers, watermarks, and irrelevant metadata

Be thorough and accurate. Focus on academic content structure.
```

---

## Usage in Code

```python
import google.generativeai as genai

def get_extraction_prompt(pdf_file_path: str) -> str:
    """Construct the prompt for Gemini Vision API."""

    system_prompt = """
    You are an expert academic document analyzer...
    [Full prompt from above]
    """

    return system_prompt

async def extract_pdf_data(pdf_path: str) -> dict:
    """Call Gemini Vision API with the system prompt."""

    model = genai.GenerativeModel('gemini-3-vision')

    prompt = get_extraction_prompt(pdf_path)

    with open(pdf_path, 'rb') as pdf_file:
        pdf_data = pdf_file.read()

    response = await model.generate_content_async([
        prompt,
        {
            "mime_type": "application/pdf",
            "data": pdf_data
        }
    ])

    return response.json()
```

---

## Prompt Optimization Tips

**For Better Extraction:**
- Request specific page ranges for large documents
- Ask for confidence scores on each field
- Specify handling of tables and figures
- Request metadata extraction (publication date, journal, etc.)

**For Better Accuracy:**
- Provide example output in the prompt
- Specify handling of edge cases (missing sections, unusual formats)
- Request validation of extracted data
- Ask model to flag low-confidence extractions

---

## Response Validation

After receiving Gemini's response:
1. Validate JSON structure matches schema
2. Check confidence_score >= 0.7 (threshold)
3. Verify required fields (title, authors) are not null
4. Sanitize extracted text (remove excessive whitespace)
5. Log any parsing errors

---

## Example Response

```json
{
  "title": "Deep Learning for Natural Language Processing: A Survey",
  "authors": [
    "Jane Smith",
    "John Doe",
    "Emily Chen"
  ],
  "abstract": "This paper provides a comprehensive survey of deep learning techniques applied to natural language processing tasks...",
  "sections": [
    {
      "heading": "Introduction",
      "content": "Natural language processing (NLP) has experienced rapid advancement..."
    },
    {
      "heading": "Methodology",
      "content": "We conducted a systematic review of 150 papers published between 2020-2025..."
    }
  ],
  "keywords": [
    "deep learning",
    "NLP",
    "neural networks",
    "transformers"
  ],
  "reference_count": 87,
  "figures_tables": [
    "Figure 1: Architecture of transformer model",
    "Table 1: Performance comparison of models"
  ],
  "confidence_score": 0.92
}
```
