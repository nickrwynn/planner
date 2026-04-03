from __future__ import annotations

from app.models.user import User


def _mk_user(db_session, email: str) -> User:
    u = User(email=email, name=email.split("@", 1)[0])
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def test_resource_ownership_enforced(client, db_session):
    u1 = _mk_user(db_session, "owner1@test.dev")
    u2 = _mk_user(db_session, "owner2@test.dev")
    h1 = {"X-User-Id": str(u1.id)}
    h2 = {"X-User-Id": str(u2.id)}

    c = client.post("/courses", json={"name": "Owned Course"}, headers=h1)
    assert c.status_code == 200
    course_id = c.json()["id"]

    created = client.post(
        "/resources",
        json={"course_id": course_id, "title": "Private Resource", "resource_type": "pdf"},
        headers=h1,
    )
    assert created.status_code == 200
    rid = created.json()["id"]

    assert client.get(f"/resources/{rid}", headers=h2).status_code == 404
    assert client.delete(f"/resources/{rid}", headers=h2).status_code == 404
    assert client.post(f"/resources/{rid}/reindex", json={}, headers=h2).status_code == 404
    assert client.get(f"/resources/{rid}/jobs", headers=h2).status_code == 404
    assert client.get(f"/resources/{rid}/chunks", headers=h2).status_code == 404


def test_task_ownership_enforced(client, db_session):
    u1 = _mk_user(db_session, "taskowner1@test.dev")
    u2 = _mk_user(db_session, "taskowner2@test.dev")
    h1 = {"X-User-Id": str(u1.id)}
    h2 = {"X-User-Id": str(u2.id)}

    c = client.post("/courses", json={"name": "Task Course"}, headers=h1)
    assert c.status_code == 200
    course_id = c.json()["id"]
    t = client.post("/tasks", json={"course_id": course_id, "title": "Private Task"}, headers=h1)
    assert t.status_code == 200
    tid = t.json()["id"]

    assert client.get(f"/tasks/{tid}", headers=h2).status_code == 404
    assert client.patch(f"/tasks/{tid}", json={"title": "hijack"}, headers=h2).status_code == 404
    assert client.delete(f"/tasks/{tid}", headers=h2).status_code == 404


def test_notebook_and_notes_ownership_enforced(client, db_session):
    u1 = _mk_user(db_session, "noteowner1@test.dev")
    u2 = _mk_user(db_session, "noteowner2@test.dev")
    h1 = {"X-User-Id": str(u1.id)}
    h2 = {"X-User-Id": str(u2.id)}

    c = client.post("/courses", json={"name": "Notes Course"}, headers=h1)
    assert c.status_code == 200
    course_id = c.json()["id"]
    nb = client.post("/notebooks", json={"course_id": course_id, "title": "NB"}, headers=h1)
    assert nb.status_code == 200
    notebook_id = nb.json()["id"]

    doc = client.post(
        "/note-documents",
        json={"notebook_id": notebook_id, "title": "Doc 1", "note_type": "typed"},
        headers=h1,
    )
    assert doc.status_code == 200
    doc_id = doc.json()["id"]
    page = client.post(
        "/note-pages",
        json={"note_document_id": doc_id, "page_index": 0, "text": "private page"},
        headers=h1,
    )
    assert page.status_code == 200
    page_id = page.json()["id"]

    assert client.get(f"/notebooks/{notebook_id}", headers=h2).status_code == 404
    assert client.get(f"/note-documents/{doc_id}", headers=h2).status_code == 404
    assert client.get(f"/note-pages/{page_id}", headers=h2).status_code == 404
    assert client.delete(f"/note-pages/{page_id}", headers=h2).status_code == 404


def test_ai_conversation_ownership_enforced(client, db_session):
    u1 = _mk_user(db_session, "aiowner1@test.dev")
    u2 = _mk_user(db_session, "aiowner2@test.dev")
    h1 = {"X-User-Id": str(u1.id)}
    h2 = {"X-User-Id": str(u2.id)}

    ask = client.post("/ai/ask", json={"message": "hello from user1"}, headers=h1)
    assert ask.status_code == 200
    cid = ask.json()["conversation_id"]

    assert client.get(f"/ai/conversations/{cid}/messages", headers=h2).status_code == 404
    assert client.patch(f"/ai/conversations/{cid}?title=hack", headers=h2).status_code == 404
    assert client.delete(f"/ai/conversations/{cid}", headers=h2).status_code == 404
