from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


DEFAULT_STEP_KEYS = ("read", "highlight_ask", "summarize", "review")


class StudyFlowStepRead(BaseModel):
    id: UUID
    step_key: str
    step_index: int
    status: str
    payload_json: dict | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class StudyFlowRunRead(BaseModel):
    id: UUID
    flow_id: UUID
    resource_id: UUID | None = None
    current_step_key: str
    progress_json: dict | None = None
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    steps: list[StudyFlowStepRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class StudyFlowRead(BaseModel):
    id: UUID
    course_id: UUID
    name: str
    template_key: str
    status: str
    active_run: StudyFlowRunRead | None = None

    model_config = {"from_attributes": True}


class StudyFlowEnsureRequest(BaseModel):
    course_id: UUID
    name: str | None = None
    template_key: str = "default_retrieval"


class StudyFlowAttachResourceRequest(BaseModel):
    resource_id: UUID


class StudyFlowAdvanceRequest(BaseModel):
    step_key: str
    payload_json: dict | None = None
    complete: bool = False


class StudyFlowScoreRequest(BaseModel):
    source_text: str = Field(min_length=1)
    student_text: str = Field(min_length=1)


class StudyFlowScoreRead(BaseModel):
    score: float
    coverage: float
    verbatim_penalty: float
    feedback: str


class StudyFlowSaveNoteRequest(BaseModel):
    highlight: str = Field(default="", max_length=12000)
    student_text: str = Field(min_length=1, max_length=20000)
    step_key: str = Field(default="highlight_ask", max_length=64)
    kind: str = Field(default="comment", max_length=32)
    latex: str | None = Field(default=None, max_length=20000)
    page_number: int | None = Field(default=None, ge=1)
    section_hint: str | None = Field(default=None, max_length=200)


class StudyFlowSaveNoteResponse(BaseModel):
    notebook_id: str
    note_document_id: str
    note_page_id: str
    page_index: int
    notebook_title: str
    document_title: str


class StudyFlowInProgressItem(BaseModel):
    course_id: UUID
    course_name: str
    course_code: str | None = None
    run_id: UUID
    resource_id: UUID | None = None
    excerpt_id: str | None = None
    page: int | None = None
    label: str
    detail: str
    steps_done: int = 0
    steps_total: int = 0
