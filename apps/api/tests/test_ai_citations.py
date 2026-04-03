from __future__ import annotations

from uuid import UUID

from app.models.resource import Resource
from app.models.resource_chunk import ResourceChunk


class _FakeLLMResult:
    def __init__(self, content: str):
        self.content = content


def test_ai_ask_returns_grounded_citations_when_model_references_invalid_source(client, db_session, monkeypatch):
    created_course = client.post("/courses", json={"name": "AI Citation Course"})
    assert created_course.status_code == 200
    course = created_course.json()

    created_resource = client.post(
        "/resources",
        json={"course_id": course["id"], "title": "Source Doc", "resource_type": "file"},
    )
    assert created_resource.status_code == 200
    rid = created_resource.json()["id"]

    res = db_session.get(Resource, UUID(rid))
    assert res is not None
    res.index_status = "done"
    res.parse_status = "parsed"
    res.ocr_status = "skipped"
    res.lifecycle_state = "searchable"
    db_session.add(res)
    db_session.commit()

    chunk = ResourceChunk(
        user_id=UUID(course["user_id"]),
        resource_id=res.id,
        chunk_index=0,
        page_number=None,
        text="Ground truth source text.",
    )
    db_session.add(chunk)
    db_session.commit()

    monkeypatch.setattr("app.api.routes.ai.is_llm_configured", lambda: True)
    monkeypatch.setattr(
        "app.api.routes.ai.chat_completion",
        lambda **kwargs: _FakeLLMResult("Model answer with bad citation [S999]."),
    )

    ask = client.post("/ai/ask", json={"message": "ground truth source", "course_id": course["id"], "top_k": 5})
    assert ask.status_code == 200
    body = ask.json()
    assert len(body["citations"]) >= 1
    assert "Invalid citation references removed" in body["answer"]
