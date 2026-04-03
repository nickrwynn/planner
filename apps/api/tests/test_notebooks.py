from __future__ import annotations


def test_notebooks_crud(client):
    # Create course
    res = client.post("/courses", json={"name": "Course for Notebooks"})
    assert res.status_code == 200
    course_id = res.json()["id"]

    # Create notebook
    res = client.post("/notebooks", json={"course_id": course_id, "title": "Notebook 1"})
    assert res.status_code == 200
    notebook = res.json()
    notebook_id = notebook["id"]

    # List notebooks
    res = client.get("/notebooks", params={"course_id": course_id})
    assert res.status_code == 200
    assert any(n["id"] == notebook_id for n in res.json())

    # Update notebook
    res = client.patch(f"/notebooks/{notebook_id}", json={"title": "Notebook Updated"})
    assert res.status_code == 200
    assert res.json()["title"] == "Notebook Updated"

    # Delete
    res = client.delete(f"/notebooks/{notebook_id}")
    assert res.status_code == 200
    assert res.json()["ok"] is True

