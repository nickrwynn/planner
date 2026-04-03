from __future__ import annotations


def test_tasks_crud(client):
    # Create a course first
    res = client.post("/courses", json={"name": "Course for Tasks"})
    assert res.status_code == 200
    course_id = res.json()["id"]

    # Create task
    res = client.post("/tasks", json={"course_id": course_id, "title": "Task 1"})
    assert res.status_code == 200
    task = res.json()
    task_id = task["id"]
    assert task["title"] == "Task 1"

    # List tasks (course scoped)
    res = client.get(f"/courses/{course_id}/tasks")
    assert res.status_code == 200
    assert any(t["id"] == task_id for t in res.json())

    # Update
    res = client.patch(f"/tasks/{task_id}", json={"status": "done"})
    assert res.status_code == 200
    assert res.json()["status"] == "done"

    # Get
    res = client.get(f"/tasks/{task_id}")
    assert res.status_code == 200
    assert res.json()["id"] == task_id

    # Delete
    res = client.delete(f"/tasks/{task_id}")
    assert res.status_code == 200
    assert res.json()["ok"] is True

