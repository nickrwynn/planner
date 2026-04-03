from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.user import User
from app.services import tasks as task_service


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def next_open_task(db: Session, *, user: User) -> tuple[Task | None, list[str]]:
    """
    Deterministic "what to do now" score with due date, weight, and effort signals.
    """
    tasks = task_service.list_tasks(db, user=user, course_id=None)
    open_tasks = [t for t in tasks if (t.status or "").lower() != "done"]
    if not open_tasks:
        return None, []

    now = datetime.now(timezone.utc)

    def score_task(t: Task) -> float:
        score = 0.0
        created_at = _as_utc(t.created_at)
        if t.due_at is None:
            score += 10.0
        else:
            due_at = _as_utc(t.due_at)
            delta_hours = (due_at - now).total_seconds() / 3600.0
            if delta_hours < 0:
                score += 100.0 + min(abs(delta_hours), 240.0) / 2.0
            else:
                score += max(0.0, 60.0 - min(delta_hours, 120.0) / 2.0)
        if t.weight is not None:
            score += min(max(float(t.weight), 0.0), 100.0) / 2.0
        if t.estimated_minutes is not None:
            # Slightly prefer lower-effort wins when urgency is similar.
            score -= min(max(float(t.estimated_minutes), 0.0), 300.0) / 30.0
        # Recency tie-breaker influence.
        score += min((now - created_at).total_seconds() / 3600.0, 24.0) / 100.0
        return score

    open_tasks.sort(
        key=lambda t: (
            -score_task(t),
            _as_utc(t.due_at).timestamp() if t.due_at else float("inf"),
            -_as_utc(t.created_at).timestamp(),
        )
    )
    winner = open_tasks[0]
    reasons: list[str] = []
    reasons.append(f"score={score_task(winner):.2f}")
    if winner.due_at is not None:
        if _as_utc(winner.due_at) < now:
            reasons.append("overdue")
        else:
            reasons.append("near due date among open tasks")
    else:
        reasons.append("no due date fallback")
    if winner.weight is not None:
        reasons.append(f"course weight {winner.weight}")
    if winner.estimated_minutes is not None:
        reasons.append(f"estimated {winner.estimated_minutes} minutes")
    return winner, reasons


def upcoming_open_tasks(db: Session, *, user: User, limit: int = 8) -> list[Task]:
    tasks = task_service.list_tasks(db, user=user, course_id=None)
    open_tasks = [t for t in tasks if (t.status or "").lower() != "done"]
    if not open_tasks:
        return []

    now = datetime.now(timezone.utc)

    def sort_key(t: Task) -> tuple:
        if t.due_at is None:
            return (2, float("inf"), -_as_utc(t.created_at).timestamp())
        due_at = _as_utc(t.due_at)
        if due_at < now:
            return (0, due_at.timestamp(), -_as_utc(t.created_at).timestamp())
        return (1, due_at.timestamp(), -_as_utc(t.created_at).timestamp())

    open_tasks.sort(key=sort_key)
    return open_tasks[: max(1, limit)]
