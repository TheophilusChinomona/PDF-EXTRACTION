from typing import List, Optional, Union, Dict
from pydantic import BaseModel, Field

# --- Essay Specific Models ---
class EssayStructure(BaseModel):
    """
    Captures the structured content for Section C essays.
    """
    introduction: List[str] = Field(..., description="List of valid introduction points")
    body_sections: List[Dict[str, Union[List[str], Dict[str, List[str]]]]] = Field(
        ..., 
        description="List of sub-topics. Each sub-topic contains a list of valid facts/points."
    )
    conclusion: List[str] = Field(..., description="List of valid conclusion points")

# --- Answer Models ---
class MemoQuestion(BaseModel):
    """
    Represents the 'Correct Answer' block for a specific question.
    """
    id: str = Field(..., description="The question number, e.g. 1.1 or 2.3")
    text: Optional[str] = Field(None, description="The topic/heading of the answer, e.g. 'Advantages of TQM'")
    type: Optional[str] = Field(None, description="e.g. 'Multiple Choice', 'Essay', 'Match Columns'")
    
    # The Critical Data: What is the correct answer?
    # We use Union to handle simple lists of facts OR complex structures
    model_answers: Optional[Union[List[str], Dict[str, List[str]]]] = Field(
        None, 
        description="A list of ALL valid facts listed in the memo. For TQM, this might be split into 'Positives' and 'Negatives'."
    )
    answers: Optional[List[Dict[str, str]]] = Field(
        None, 
        description="For sub-questions like 1.2.1, 1.2.2. Format: [{'sub_id': '1.2.1', 'value': 'Answer'}]"
    )
    
    # Grading Logic
    marks: Optional[int] = Field(None, description="Total marks allocated")
    marker_instruction: Optional[str] = Field(
        None, 
        description="CRITICAL instructions for the AI grader, e.g. 'Mark the first TWO only'."
    )
    essay_structure: Optional[EssayStructure] = Field(
        None, 
        description="Only populated for Essay questions (Section C)."
    )

class MemoSection(BaseModel):
    section_id: str = Field(..., description="SECTION A, SECTION B, etc.")
    questions: List[MemoQuestion]

class MarkingGuideline(BaseModel):
    meta: Dict[str, Union[str, int]] = Field(..., description="Subject, Year, Session, Total Marks")
    sections: List[MemoSection]