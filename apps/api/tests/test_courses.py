from __future__ import annotations


def test_courses_crud(client):
    # Create
    res = client.post("/courses", json={"name": "Test Course", "code": "TST101"})
    assert res.status_code == 200
    course = res.json()
    assert course["name"] == "Test Course"
    course_id = course["id"]

    # List
    res = client.get("/courses")
    assert res.status_code == 200
    courses = res.json()
    assert any(c["id"] == course_id for c in courses)

    # Get
    res = client.get(f"/courses/{course_id}")
    assert res.status_code == 200

    # Update
    res = client.patch(f"/courses/{course_id}", json={"name": "Updated Course"})
    assert res.status_code == 200
    assert res.json()["name"] == "Updated Course"

    # Delete
    res = client.delete(f"/courses/{course_id}")
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # Get after delete
    res = client.get(f"/courses/{course_id}")
    assert res.status_code == 404

