from typing import List, Optional, Union, Dict
from pydantic import BaseModel, Field

class MultipleChoiceOption(BaseModel):
    label: str = Field(..., description="A, B, C, or D")
    text: str = Field(..., description="The content of the option")

class Question(BaseModel):
    id: str = Field(..., description="The full number, e.g., 1.1.1")
    text: str = Field(..., description="The actual question text")
    marks: Optional[int] = Field(None)
    options: Optional[List[MultipleChoiceOption]] = Field(None, description="For MCQs")
    scenario: Optional[str] = Field(None, description="The 'Read the scenario' text if applicable")
    guide_table: Optional[List[Dict[str, str]]] = Field(None, description="JSON representation of tables like 2.3")
    parent_group: Optional[str] = Field(None, description="Links 1.1 to Question 1")

class QuestionGroup(BaseModel):
    group_id: str = Field(..., description="e.g., 'QUESTION 1' or 'SECTION A'")
    title: str = Field(..., description="The group heading")
    instructions: Optional[str] = Field(None)
    questions: List[Question]

class FullExamPaper(BaseModel):
    subject: str = Field(..., description="Business Studies P1")
    syllabus: str = Field(..., description="SC/NSC (found in the header box)")
    year: int = Field(..., description="2025")
    session: str = Field(..., description="May/June")
    grade: str = Field(..., description="12")
    total_marks: int = Field(150)
    groups: List[QuestionGroup]