from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class SearchHit(BaseModel):
    resource_id: UUID
    resource_title: str
    resource_type: str | None = None
    chunk_id: UUID
    chunk_index: int
    page_number: int | None
    snippet: str
    score: float | None = None

    model_config = {"from_attributes": True}

