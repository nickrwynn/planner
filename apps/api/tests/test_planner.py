from __future__ import annotations

from datetime import UTC, datetime, timedelta


def test_planner_next_empty(client):
    res = client.get("/planner/next")
    assert res.status_code == 200
    data = res.json()
    assert data["task"] is None
    assert data["reasons"] == []


def test_planner_next_picks_open_task(client):
    r = client.post("/courses", json={"name": "P Course"})
    assert r.status_code == 200
    course_id = r.json()["id"]
    r = client.post("/tasks", json={"course_id": course_id, "title": "Do reading", "status": "todo"})
    assert r.status_code == 200

    res = client.get("/planner/next")
    assert res.status_code == 200
    data = res.json()
    assert data["task"] is not None
    assert data["task"]["title"] == "Do reading"
    assert len(data["reasons"]) >= 1


def test_planner_prefers_overdue_task(client):
    r = client.post("/courses", json={"name": "Priority Course"})
    assert r.status_code == 200
    course_id = r.json()["id"]
    now = datetime.now(UTC)

    due_future = (now + timedelta(days=1)).isoformat()
    due_past = (now - timedelta(hours=6)).isoformat()
    r1 = client.post(
        "/tasks",
        json={"course_id": course_id, "title": "Future task", "status": "todo", "due_at": due_future},
    )
    assert r1.status_code == 200
    r2 = client.post(
        "/tasks",
        json={"course_id": course_id, "title": "Overdue task", "status": "todo", "due_at": due_past},
    )
    assert r2.status_code == 200

    res = client.get("/planner/next")
    assert res.status_code == 200
    data = res.json()
    assert data["task"]["title"] == "Overdue task"
    assert any("overdue" in reason for reason in data["reasons"])
