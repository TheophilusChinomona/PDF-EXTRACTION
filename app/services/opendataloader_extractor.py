"""
OpenDataLoader PDF structure extraction service.

This module provides functions to extract PDF structure locally using OpenDataLoader,
including markdown conversion, tables, and bounding boxes. This is the first stage
of the hybrid extraction pipeline before sending to Gemini API.
"""

import json
import os
import tempfile
from typing import Dict, List, Any
from opendataloader_pdf import convert

from app.models.extraction import DocumentStructure


def calculate_quality_score(
    text_length: int,
    element_count: int,
    heading_count: int,
    tables: List[Dict[str, Any]]
) -> float:
    """
    Calculate quality score (0.0 to 1.0) for routing decisions.

    This score determines whether to use hybrid mode (OpenDataLoader + Gemini)
    or fallback to Gemini Vision API for low-quality extractions.

    Scoring criteria:
    - Text completeness (40%): >1000 chars = 0.4, >500 = 0.3, >100 = 0.2
    - Structure detection (30%): >50 elements = 0.3, >20 = 0.2, >5 = 0.1
    - Heading hierarchy (15%): >=5 headings = 0.15, >=3 = 0.1, >=1 = 0.05
    - Table extraction (15%): valid tables (>3 rows) = 0.15, some tables = 0.1

    Args:
        text_length: Total character count of extracted text
        element_count: Number of document elements extracted
        heading_count: Number of heading elements detected
        tables: List of extracted tables with their data

    Returns:
        Quality score between 0.0 and 1.0
    """
    score = 0.0

    # Text completeness (40%)
    if text_length > 1000:
        score += 0.4
    elif text_length > 500:
        score += 0.3
    elif text_length > 100:
        score += 0.2

    # Structure detection (30%)
    if element_count > 50:
        score += 0.3
    elif element_count > 20:
        score += 0.2
    elif element_count > 5:
        score += 0.1

    # Heading hierarchy (15%)
    if heading_count >= 5:
        score += 0.15
    elif heading_count >= 3:
        score += 0.1
    elif heading_count >= 1:
        score += 0.05

    # Table extraction (15%)
    # Count tables with >3 rows as "valid" (likely real tables, not artifacts)
    valid_tables = [t for t in tables if len(t.get("data", [])) > 3]
    if len(valid_tables) > 0:
        score += 0.15
    elif len(tables) > 0:
        score += 0.1

    # Cap at 1.0
    return min(score, 1.0)


def extract_pdf_structure(file_path: str) -> DocumentStructure:
    """
    Extract PDF structure using OpenDataLoader (local, fast, deterministic).

    This function performs local PDF parsing to extract:
    - Markdown representation of document content
    - Tables with bounding boxes
    - Bounding boxes for all document elements
    - Quality metrics for routing decisions

    Args:
        file_path: Path to the PDF file to process

    Returns:
        DocumentStructure containing markdown, tables, bounding boxes, and quality metrics

    Raises:
        FileNotFoundError: If the PDF file does not exist
        ValueError: If the file is not a valid PDF or cannot be processed
        Exception: For other processing errors with descriptive messages
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    # Create temporary directory for output files
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Convert PDF to JSON and Markdown using OpenDataLoader
            convert(
                input_path=file_path,
                output_dir=temp_dir,
                format="json,markdown",
                quiet=True
            )

            # Read JSON output file
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            json_path = os.path.join(temp_dir, f"{base_name}.json")
            markdown_path = os.path.join(temp_dir, f"{base_name}.md")

            # Parse JSON structure
            with open(json_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            # Read markdown content
            markdown = ""
            if os.path.exists(markdown_path):
                with open(markdown_path, 'r', encoding='utf-8') as f:
                    markdown = f.read()

            # Extract tables from JSON
            tables = []
            elements = json_data.get("elements", [])

            for elem in elements:
                if elem.get("type") == "table":
                    table_data = {
                        "caption": elem.get("text", ""),
                        "page": elem.get("page", 1),
                        "data": elem.get("table_data", []),
                    }
                    # Add bounding box if available
                    if "bbox" in elem and elem["bbox"]:
                        bbox = elem["bbox"]
                        table_data["bbox"] = {
                            "x1": float(bbox.get("x1", 0.0)),
                            "y1": float(bbox.get("y1", 0.0)),
                            "x2": float(bbox.get("x2", 0.0)),
                            "y2": float(bbox.get("y2", 0.0)),
                            "page": elem.get("page", 1)
                        }
                    tables.append(table_data)

            # Extract bounding boxes for all elements
            bounding_boxes: Dict[str, Dict[str, Any]] = {}
            for idx, elem in enumerate(elements):
                elem_type = elem.get("type", "unknown")
                elem_page = elem.get("page", 1)
                element_id = f"{elem_type}_{elem_page}_{idx}"

                if "bbox" in elem and elem["bbox"]:
                    bbox = elem["bbox"]
                    bounding_boxes[element_id] = {
                        "x1": float(bbox.get("x1", 0.0)),
                        "y1": float(bbox.get("y1", 0.0)),
                        "x2": float(bbox.get("x2", 0.0)),
                        "y2": float(bbox.get("y2", 0.0)),
                        "page": int(elem_page)
                    }

            # Calculate element count
            element_count = len(elements)

            # Count headings for quality scoring
            heading_count = sum(1 for elem in elements if elem.get("type") == "heading")

            # Calculate quality score for routing decisions
            quality_score = calculate_quality_score(
                text_length=len(markdown),
                element_count=element_count,
                heading_count=heading_count,
                tables=tables
            )

            return DocumentStructure(
                markdown=markdown,
                tables=tables,
                bounding_boxes=bounding_boxes,
                quality_score=quality_score,
                element_count=element_count
            )

        except FileNotFoundError as e:
            raise FileNotFoundError(f"PDF file not found: {file_path}") from e
        except Exception as e:
            # Provide clear error message for debugging
            raise ValueError(
                f"Failed to extract PDF structure from {file_path}: {str(e)}"
            ) from e
