from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NoteDocumentCreate(BaseModel):
    notebook_id: UUID
    title: str = Field(min_length=1, max_length=200)
    note_type: str | None = "typed"


class NoteDocumentRead(BaseModel):
    id: UUID
    user_id: UUID
    notebook_id: UUID
    title: str
    note_type: str | None
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NoteDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    note_type: str | None = None


class NotePageCreate(BaseModel):
    note_document_id: UUID
    page_index: int = Field(ge=0)
    text: str = Field(default="", max_length=20000)


class NotePageUpdate(BaseModel):
    text: str | None = Field(default=None, max_length=20000)
    page_data_json: dict | None = None


class NotePageRead(BaseModel):
    id: UUID
    user_id: UUID
    note_document_id: UUID
    resource_id: UUID | None
    page_index: int
    page_data_json: dict | None
    extracted_text: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

