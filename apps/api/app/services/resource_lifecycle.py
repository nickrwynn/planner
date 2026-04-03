from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.resource import Resource
from app.models.resource_lifecycle_event import ResourceLifecycleEvent

ALLOWED_LIFECYCLE_TRANSITIONS: dict[str, set[str]] = {
    "uploaded": {"queued", "parsing", "skipped", "failed"},
    "queued": {"uploaded", "parsing", "skipped", "failed"},
    "parsing": {"parsed", "skipped", "failed"},
    "parsed": {"chunked", "skipped", "failed"},
    "chunked": {"indexed", "skipped", "failed"},
    "indexed": {"searchable", "failed"},
    "searchable": {"uploaded", "queued", "parsing", "failed"},
    "skipped": {"uploaded", "queued", "parsing", "failed"},
    "failed": {"uploaded", "queued", "parsing", "failed"},
}


def _next_seq(db: Session, *, resource_id) -> int:
    current = db.scalar(
        select(func.max(ResourceLifecycleEvent.seq)).where(ResourceLifecycleEvent.resource_id == resource_id)
    )
    pending = max(
        (
            int(event.seq or 0)
            for event in db.new
            if isinstance(event, ResourceLifecycleEvent) and event.resource_id == resource_id
        ),
        default=0,
    )
    return max(int(current or 0), pending) + 1


def record_resource_event(
    db: Session,
    *,
    resource: Resource,
    event_type: str,
    from_state: str | None = None,
    to_state: str | None = None,
    error_code: str | None = None,
    details: dict | None = None,
    occurred_at: datetime | None = None,
) -> ResourceLifecycleEvent:
    ts = occurred_at or datetime.now(UTC)
    event = ResourceLifecycleEvent(
        user_id=resource.user_id,
        resource_id=resource.id,
        seq=_next_seq(db, resource_id=resource.id),
        from_state=from_state,
        to_state=to_state or (resource.lifecycle_state or "uploaded"),
        event_type=event_type,
        error_code=error_code,
        details_json=details,
        occurred_at=ts,
    )
    resource.last_lifecycle_event_at = ts
    db.add(event)
    db.add(resource)
    return event


def merge_event_details(
    details: dict | None,
    *,
    trace: dict | None = None,
) -> dict | None:
    """
    Merge lifecycle details with optional trace context.

    `trace` is intentionally free-form so worker/job metadata can be added
    without forcing schema changes for every operational signal.
    """
    if not details and not trace:
        return None
    merged: dict = {}
    if details:
        merged.update(details)
    if trace:
        merged.update(trace)
    return merged


def transition_resource_lifecycle(
    resource: Resource,
    next_state: str,
    *,
    db: Session | None = None,
    event_type: str = "lifecycle.transition",
    error_code: str | None = None,
    details: dict | None = None,
    occurred_at: datetime | None = None,
    allow_noop_event: bool = False,
) -> None:
    current = resource.lifecycle_state or "uploaded"
    if next_state == current:
        if db is not None and allow_noop_event:
            record_resource_event(
                db,
                resource=resource,
                event_type=event_type,
                from_state=current,
                to_state=current,
                error_code=error_code,
                details=details,
                occurred_at=occurred_at,
            )
        return
    allowed = ALLOWED_LIFECYCLE_TRANSITIONS.get(current, set())
    if next_state not in allowed:
        raise ValueError(f"Illegal lifecycle transition: {current} -> {next_state}")
    resource.lifecycle_state = next_state
    if db is not None:
        record_resource_event(
            db,
            resource=resource,
            event_type=event_type,
            from_state=current,
            to_state=next_state,
            error_code=error_code,
            details=details,
            occurred_at=occurred_at,
        )
