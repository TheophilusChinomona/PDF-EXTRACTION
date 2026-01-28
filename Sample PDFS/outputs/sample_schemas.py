from typing import List, Optional, Dict, Union
from pydantic import BaseModel, Field

# --- Sub-Component Models ---

class MultipleChoiceOption(BaseModel):
    """
    Represents a single option in a multiple-choice question.
    Example: { "label": "A", "text": "Employment Equity Act" }
    """
    label: str = Field(..., description="The option identifier, e.g., 'A', 'B', 'C'")
    text: str = Field(..., description="The content of the option")

class MatchColumnItem(BaseModel):
    """
    Represents a single row in a 'Match Column A with B' question.
    """
    label: str = Field(..., description="The identifier, e.g., '1.3.1' or 'A'")
    text: str = Field(..., description="The content of the item")

class MatchData(BaseModel):
    """
    Specialized structure for questions where students must match items from two lists.
    We keep the lists separate to handle unequal lengths (distractors).
    """
    column_a_title: str = Field(default="COLUMN A")
    column_b_title: str = Field(default="COLUMN B")
    column_a_items: List[MatchColumnItem] = Field(..., description="Items in the first column")
    column_b_items: List[MatchColumnItem] = Field(..., description="Items in the second column (often contains distractors)")

# --- Main Question Model ---

class Question(BaseModel):
    """
    The universal question model. It uses Optional fields to handle 
    the variety of question types (MCQ, Essay, Match, Scenario-based).
    """
    id: str = Field(..., description="The full question number, e.g., '1.1.1' or '2.3'")
    text: str = Field(..., description="The actual question text")
    marks: Optional[int] = Field(None, description="Marks allocated to this specific question")
    
    # Contextual Fields (The 'Reasoning' Parts)
    scenario: Optional[str] = Field(
        None, 
        description="Mandatory for case studies. The text block (e.g. 'PETRA FARMING...') that this question refers to."
    )
    context: Optional[str] = Field(
        None, 
        description="AI description of visual elements like diagrams or graphs if present."
    )

    # Type-Specific Data Structures
    options: Optional[List[MultipleChoiceOption]] = Field(
        None, 
        description="List of options if this is a Multiple Choice Question"
    )
    match_data: Optional[MatchData] = Field(
        None, 
        description="Structured data for 'Match Column A and B' questions"
    )
    guide_table: Optional[List[Dict[str, str]]] = Field(
        None, 
        description="For questions that provide an empty table/guide to fill in (e.g. 'Use the table below')"
    )

# --- Hierarchical Models ---

class QuestionGroup(BaseModel):
    """
    Represents a major section or top-level question grouping.
    Example: 'QUESTION 1' or 'SECTION A'
    """
    group_id: str = Field(..., description="e.g., 'QUESTION 1'")
    title: str = Field(..., description="e.g., 'SECTION A (COMPULSORY)'")
    instructions: Optional[str] = Field(None, description="Specific instructions for this section, e.g. 'Answer ANY TWO'")
    questions: List[Question] = Field(default_factory=list)

class FullExamPaper(BaseModel):
    """
    The root object representing the entire extracted PDF.
    """
    subject: str = Field(..., description="e.g., 'Business Studies P1'")
    syllabus: str = Field(..., description="e.g., 'SC/NSC', 'IEB', 'CAPS'")
    year: int = Field(..., description="e.g., 2025")
    session: str = Field(..., description="e.g., 'MAY/JUNE' or 'NOV'")
    grade: str = Field(..., description="e.g., '12' or 'Grade 11'")
    total_marks: Optional[int] = Field(None, description="Total marks for the paper, e.g. 150")
    groups: List[QuestionGroup] = Field(..., description="List of all question sections found in the paper")