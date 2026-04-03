from __future__ import annotations

from sqlalchemy import select

from app.models.course import Course
from app.models.note_document import NoteDocument
from app.models.notebook import Notebook
from app.models.resource_chunk import ResourceChunk
from app.models.user import User
from app.services import notes as notes_service


class _FakeEmbeddingsProvider:
    def embed_query(self, text: str) -> list[float]:
        return [0.5, 0.5]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.25, 0.75] for _ in texts]


def test_notes_crud(client):
    # Create course + notebook
    res = client.post("/courses", json={"name": "Course for Notes"})
    assert res.status_code == 200
    course_id = res.json()["id"]

    res = client.post("/notebooks", json={"course_id": course_id, "title": "Notebook for Notes"})
    assert res.status_code == 200
    notebook_id = res.json()["id"]

    # Create note document
    res = client.post("/note-documents", json={"notebook_id": notebook_id, "title": "Doc 1", "note_type": "typed"})
    assert res.status_code == 200
    doc_id = res.json()["id"]

    # Create note page
    res = client.post("/note-pages", json={"note_document_id": doc_id, "page_index": 0, "text": "hello world"})
    assert res.status_code == 200
    page_id = res.json()["id"]
    assert res.json()["extracted_text"] == "hello world"
    assert res.json()["resource_id"] is not None

    # Update note page
    res = client.patch(f"/note-pages/{page_id}", json={"text": "updated text"})
    assert res.status_code == 200
    assert res.json()["extracted_text"] == "updated text"

    # Delete note page
    res = client.delete(f"/note-pages/{page_id}")
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # Delete note document
    res = client.delete(f"/note-documents/{doc_id}")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_note_page_chunks_receive_embeddings_when_provider_configured(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.indexing.embeddings.get_embeddings_provider",
        lambda: _FakeEmbeddingsProvider(),
    )

    user = User(email="nemb@test.dev", name="N")
    db_session.add(user)
    db_session.commit()
    course = Course(user_id=user.id, name="C")
    db_session.add(course)
    db_session.commit()
    nb = Notebook(user_id=user.id, course_id=course.id, title="NB")
    db_session.add(nb)
    db_session.commit()
    doc = NoteDocument(user_id=user.id, notebook_id=nb.id, title="D", note_type="typed")
    db_session.add(doc)
    db_session.commit()

    page = notes_service.create_note_page(
        db_session, user=user, doc_id=doc.id, page_index=0, text="hello embed note"
    )
    assert page.resource_id is not None
    chunks = list(
        db_session.execute(
            select(ResourceChunk).where(ResourceChunk.resource_id == page.resource_id)
        ).scalars().all()
    )
    assert len(chunks) >= 1
    assert chunks[0].embedding == [0.25, 0.75]

