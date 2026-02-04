"""Normalize subject, grade, paper number, and session for exam set matching."""

import re
from typing import Optional, Union

SUBJECT_MAPPINGS: dict[str, str] = {
    "maths": "Mathematics",
    "math": "Mathematics",
    "mathematics": "Mathematics",
    "mathematical literacy": "Mathematical Literacy",
    "math lit": "Mathematical Literacy",
    "physical science": "Physical Sciences",
    "physical sciences": "Physical Sciences",
    "physics": "Physical Sciences",
    "life science": "Life Sciences",
    "life sciences": "Life Sciences",
    "biology": "Life Sciences",
    "business studies": "Business Studies",
    "bus studies": "Business Studies",
    "accounting": "Accounting",
    "acc": "Accounting",
    "economics": "Economics",
    "eco": "Economics",
    "geography": "Geography",
    "geo": "Geography",
    "history": "History",
    "his": "History",
    "english": "English",
    "english hl": "English Home Language",
    "english fal": "English First Additional Language",
    "afrikaans": "Afrikaans",
    "afrikaans hl": "Afrikaans Home Language",
    "afrikaans fal": "Afrikaans First Additional Language",
}

SESSION_MAPPINGS: dict[str, str] = {
    "may": "May/June",
    "june": "May/June",
    "may/june": "May/June",
    "may-june": "May/June",
    "nov": "November",
    "november": "November",
    "feb": "February/March",
    "march": "February/March",
    "feb/march": "February/March",
    "feb-march": "February/March",
    "supplementary": "February/March",
}


def normalize_subject(subject: str) -> str:
    """Normalize subject names for matching. Unknown subjects preserved with title case."""
    if not subject or not subject.strip():
        return subject.strip() if subject else ""
    key = subject.strip().lower()
    return SUBJECT_MAPPINGS.get(key, subject.strip().title())


def normalize_grade(grade: Union[str, int]) -> Optional[int]:
    """Extract integer from 'Grade 12', 'Gr 12', etc. Returns None if unparseable."""
    if isinstance(grade, int):
        return grade
    s = str(grade).strip()
    match = re.search(r"\d+", s)
    return int(match.group()) if match else None


def normalize_paper_number(paper: Union[str, int]) -> int:
    """Extract integer from 'P1', 'Paper 1', etc. Defaults to 1 if unparseable."""
    if isinstance(paper, int):
        return paper
    s = str(paper).strip()
    match = re.search(r"\d+", s)
    return int(match.group()) if match else 1


def normalize_session(session: str) -> str:
    """Normalize session names. Case-insensitive."""
    if not session or not session.strip():
        return session.strip() if session else ""
    key = session.strip().lower()
    return SESSION_MAPPINGS.get(key, session.strip())
