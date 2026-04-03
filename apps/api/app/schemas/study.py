from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.ai import Citation


class GenerateBaseRequest(BaseModel):
    course_id: UUID | None = None
    resource_ids: list[UUID] = Field(default_factory=list, min_length=1)
    title: str | None = None


class SummarySection(BaseModel):
    heading: str
    bullets: list[str]
    citations: list[Citation] = Field(default_factory=list)


class SummaryResponse(BaseModel):
    artifact_id: UUID
    title: str
    sections: list[SummarySection]
    created_at: datetime


class Flashcard(BaseModel):
    question: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)


class FlashcardsResponse(BaseModel):
    artifact_id: UUID
    title: str
    cards: list[Flashcard]
    created_at: datetime


class QuizItem(BaseModel):
    question: str
    answer: str
    explanation: str | None = None
    citations: list[Citation] = Field(default_factory=list)


class QuizResponse(BaseModel):
    artifact_id: UUID
    title: str
    items: list[QuizItem]
    created_at: datetime


class SampleProblem(BaseModel):
    problem: str
    solution: str | None = None
    citations: list[Citation] = Field(default_factory=list)


class SampleProblemsResponse(BaseModel):
    artifact_id: UUID
    title: str
    problems: list[SampleProblem]
    created_at: datetime


class ArtifactListItem(BaseModel):
    id: UUID
    course_id: UUID | None
    artifact_type: str
    title: str
    source_resource_ids_json: list | None
    created_at: datetime

    model_config = {"from_attributes": True}


class StudyArtifactRead(BaseModel):
    id: UUID
    user_id: UUID
    course_id: UUID | None
    artifact_type: str
    title: str
    source_resource_ids_json: list | None
    content_json: dict | None
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ArtifactUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content_json: dict | None = None


class ArtifactRegenerateRequest(BaseModel):
    course_id: UUID | None = None
    resource_ids: list[UUID] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)


# --- LLM output validation (no citation fields; stored in metadata_json) ---


class LlmSummarySection(BaseModel):
    heading: str = Field(min_length=1)
    bullets: list[str] = Field(min_length=1)


class LlmSummaryContent(BaseModel):
    title: str | None = None
    sections: list[LlmSummarySection] = Field(min_length=1)


class LlmFlashcardItem(BaseModel):
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)


class LlmFlashcardsContent(BaseModel):
    title: str | None = None
    cards: list[LlmFlashcardItem] = Field(min_length=1)


class LlmQuizItem(BaseModel):
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    explanation: str | None = None


class LlmQuizContent(BaseModel):
    title: str | None = None
    items: list[LlmQuizItem] = Field(min_length=1)


class LlmProblemItem(BaseModel):
    problem: str = Field(min_length=1)
    solution: str | None = None


class LlmSampleProblemsContent(BaseModel):
    title: str | None = None
    problems: list[LlmProblemItem] = Field(min_length=1)

