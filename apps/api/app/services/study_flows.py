from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.course import Course
from app.models.resource import Resource
from app.models.resource_chunk import ResourceChunk
from app.models.study_flow import StudyFlow, StudyFlowRun, StudyFlowStep
from app.models.user import User
from app.schemas.study_flow import (
    DEFAULT_STEP_KEYS,
    StudyFlowAdvanceRequest,
    StudyFlowEnsureRequest,
    StudyFlowInProgressItem,
    StudyFlowRead,
    StudyFlowRunRead,
    StudyFlowScoreRead,
    StudyFlowStepRead,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


_WORD_RE = re.compile(r"[a-z0-9']+")


def _tokenize(text: str) -> set[str]:
    return {m.group(0) for m in _WORD_RE.finditer((text or "").lower()) if len(m.group(0)) > 2}


def score_summary(*, source_text: str, student_text: str) -> StudyFlowScoreRead:
    source_tokens = _tokenize(source_text)
    student_tokens = _tokenize(student_text)
    if not source_tokens or not student_tokens:
        return StudyFlowScoreRead(
            score=0.0,
            coverage=0.0,
            verbatim_penalty=0.0,
            feedback="Add more of your own wording that covers key ideas from the reading.",
        )

    overlap = source_tokens & student_tokens
    coverage = len(overlap) / max(len(source_tokens), 1)
    # Penalize near-copy when student text is mostly a subset of source with high length ratio.
    source_len = max(len(source_text.strip()), 1)
    student_len = len(student_text.strip())
    length_ratio = min(student_len / source_len, 1.0)
    verbatim_penalty = 0.0
    if coverage > 0.85 and length_ratio > 0.6:
        verbatim_penalty = min(0.4, (coverage - 0.7) * length_ratio)

    score = max(0.0, min(1.0, coverage * 0.9 + min(len(student_tokens), 40) / 80.0 - verbatim_penalty))
    if score >= 0.75 and verbatim_penalty < 0.15:
        feedback = "Strong coverage with your own phrasing. Ready for review cards."
    elif verbatim_penalty >= 0.15:
        feedback = "Too close to the source. Rewrite in your own words while keeping key concepts."
    elif coverage < 0.35:
        feedback = "Low coverage of source ideas. Re-read and include more of the main points."
    else:
        feedback = "Decent start. Expand on missing concepts before moving on."
    return StudyFlowScoreRead(
        score=round(score, 3),
        coverage=round(coverage, 3),
        verbatim_penalty=round(verbatim_penalty, 3),
        feedback=feedback,
    )


def _run_to_read(run: StudyFlowRun) -> StudyFlowRunRead:
    steps = sorted(run.steps or [], key=lambda s: s.step_index)
    return StudyFlowRunRead(
        id=run.id,
        flow_id=run.flow_id,
        resource_id=run.resource_id,
        current_step_key=run.current_step_key,
        progress_json=run.progress_json,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        steps=[StudyFlowStepRead.model_validate(s) for s in steps],
    )


def _flow_to_read(flow: StudyFlow, run: StudyFlowRun | None) -> StudyFlowRead:
    return StudyFlowRead(
        id=flow.id,
        course_id=flow.course_id,
        name=flow.name,
        template_key=flow.template_key,
        status=flow.status,
        active_run=_run_to_read(run) if run else None,
    )


def _create_run(db: Session, *, user: User, flow: StudyFlow) -> StudyFlowRun:
    run = StudyFlowRun(
        user_id=user.id,
        flow_id=flow.id,
        resource_id=None,
        current_step_key=DEFAULT_STEP_KEYS[0],
        progress_json={"completed_steps": []},
        status="in_progress",
        started_at=utcnow(),
    )
    db.add(run)
    db.flush()
    for idx, key in enumerate(DEFAULT_STEP_KEYS):
        db.add(
            StudyFlowStep(
                user_id=user.id,
                run_id=run.id,
                step_key=key,
                step_index=idx,
                status="active" if idx == 0 else "pending",
                payload_json=None,
            )
        )
    db.flush()
    return run


def ensure_flow(db: Session, *, user: User, course: Course, data: StudyFlowEnsureRequest) -> StudyFlowRead:
    template_key = data.template_key or "default_retrieval"
    flow = (
        db.execute(
            select(StudyFlow).where(
                StudyFlow.user_id == user.id,
                StudyFlow.course_id == course.id,
                StudyFlow.template_key == template_key,
            )
        )
        .scalars()
        .first()
    )
    if flow is None:
        flow = StudyFlow(
            user_id=user.id,
            course_id=course.id,
            name=data.name or "StudyFlow",
            template_key=template_key,
            status="active",
        )
        db.add(flow)
        db.flush()

    run = (
        db.execute(
            select(StudyFlowRun)
            .options(selectinload(StudyFlowRun.steps))
            .where(
                StudyFlowRun.user_id == user.id,
                StudyFlowRun.flow_id == flow.id,
                StudyFlowRun.status == "in_progress",
            )
            .order_by(StudyFlowRun.started_at.desc())
        )
        .scalars()
        .first()
    )
    if run is None:
        run = _create_run(db, user=user, flow=flow)
        db.refresh(run)
        run = (
            db.execute(
                select(StudyFlowRun)
                .options(selectinload(StudyFlowRun.steps))
                .where(StudyFlowRun.id == run.id)
            )
            .scalars()
            .first()
        )

    db.commit()
    return _flow_to_read(flow, run)


def get_flow_for_course(db: Session, *, user: User, course_id: UUID) -> StudyFlowRead | None:
    flow = (
        db.execute(
            select(StudyFlow).where(
                StudyFlow.user_id == user.id,
                StudyFlow.course_id == course_id,
                StudyFlow.template_key == "default_retrieval",
            )
        )
        .scalars()
        .first()
    )
    if not flow:
        return None
    run = (
        db.execute(
            select(StudyFlowRun)
            .options(selectinload(StudyFlowRun.steps))
            .where(
                StudyFlowRun.user_id == user.id,
                StudyFlowRun.flow_id == flow.id,
                StudyFlowRun.status.in_(("in_progress", "completed")),
            )
            .order_by(StudyFlowRun.started_at.desc())
        )
        .scalars()
        .first()
    )
    return _flow_to_read(flow, run)


def attach_resource(db: Session, *, user: User, run_id: UUID, resource_id: UUID) -> StudyFlowRunRead:
    run = (
        db.execute(
            select(StudyFlowRun)
            .options(selectinload(StudyFlowRun.steps))
            .where(StudyFlowRun.id == run_id, StudyFlowRun.user_id == user.id)
        )
        .scalars()
        .first()
    )
    if not run:
        raise ValueError("StudyFlow run not found")
    resource = (
        db.execute(
            select(Resource).where(Resource.id == resource_id, Resource.user_id == user.id)
        )
        .scalars()
        .first()
    )
    if not resource:
        raise ValueError("Resource not found")
    run.resource_id = resource.id
    progress = dict(run.progress_json or {})
    progress["resource_id"] = str(resource.id)
    progress["resource_title"] = resource.title
    run.progress_json = progress
    db.add(run)
    db.commit()
    db.refresh(run)
    return _run_to_read(run)


def advance_step(db: Session, *, user: User, run_id: UUID, data: StudyFlowAdvanceRequest) -> StudyFlowRunRead:
    run = (
        db.execute(
            select(StudyFlowRun)
            .options(selectinload(StudyFlowRun.steps))
            .where(StudyFlowRun.id == run_id, StudyFlowRun.user_id == user.id)
        )
        .scalars()
        .first()
    )
    if not run:
        raise ValueError("StudyFlow run not found")

    steps = {s.step_key: s for s in (run.steps or [])}
    step = steps.get(data.step_key)
    if not step:
        raise ValueError("Unknown step")

    if data.payload_json is not None:
        step.payload_json = {**(step.payload_json or {}), **data.payload_json}
        # StudyFlows v2 stores excerpt sequences on the run progress blob.
        v2 = data.payload_json.get("studyflow_v2")
        if isinstance(v2, dict):
            progress = dict(run.progress_json or {})
            progress.update(v2)
            run.progress_json = progress

    if data.complete:
        step.status = "completed"
        step.completed_at = utcnow()
        progress = dict(run.progress_json or {})
        completed = list(progress.get("completed_steps") or [])
        if data.step_key not in completed:
            completed.append(data.step_key)
        progress["completed_steps"] = completed
        run.progress_json = progress

        keys = list(DEFAULT_STEP_KEYS)
        idx = keys.index(data.step_key) if data.step_key in keys else -1
        if idx >= 0 and idx + 1 < len(keys):
            nxt = keys[idx + 1]
            run.current_step_key = nxt
            nxt_step = steps.get(nxt)
            if nxt_step and nxt_step.status == "pending":
                nxt_step.status = "active"
                db.add(nxt_step)
        else:
            run.current_step_key = data.step_key
            run.status = "completed"
            run.completed_at = utcnow()
    else:
        step.status = "active"
        run.current_step_key = data.step_key

    db.add(step)
    db.add(run)
    db.commit()
    db.refresh(run)
    return _run_to_read(run)


def list_resource_texts(db: Session, *, user: User, resource_id: UUID, limit: int = 50) -> list[dict]:
    rows = (
        db.execute(
            select(ResourceChunk)
            .where(
                ResourceChunk.resource_id == resource_id,
                ResourceChunk.user_id == user.id,
            )
            .order_by(ResourceChunk.chunk_index.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(c.id),
            "chunk_index": c.chunk_index,
            "page_number": c.page_number,
            "text": c.text,
        }
        for c in rows
    ]


def list_in_progress(db: Session, *, user: User, limit: int = 12) -> list[StudyFlowInProgressItem]:
    """Sidebar cards: active StudyFlow runs with unfinished excerpts or a saved place."""
    rows = (
        db.execute(
            select(StudyFlowRun, StudyFlow, Course)
            .join(StudyFlow, StudyFlow.id == StudyFlowRun.flow_id)
            .join(Course, Course.id == StudyFlow.course_id)
            .where(
                StudyFlowRun.user_id == user.id,
                StudyFlowRun.status == "in_progress",
                StudyFlow.status == "active",
            )
            .order_by(StudyFlowRun.updated_at.desc())
            .limit(40)
        )
        .all()
    )
    items: list[StudyFlowInProgressItem] = []
    for run, flow, course in rows:
        progress = dict(run.progress_json or {})
        excerpts = progress.get("excerpts") if isinstance(progress.get("excerpts"), list) else []
        bookmark = progress.get("bookmark") if isinstance(progress.get("bookmark"), dict) else None
        active_id = progress.get("active_excerpt_id")

        incomplete = []
        for raw in excerpts:
            if not isinstance(raw, dict):
                continue
            steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
            if not steps or any(isinstance(s, dict) and s.get("status") != "done" for s in steps):
                incomplete.append(raw)

        if not incomplete and not bookmark and not run.resource_id:
            continue

        chosen = None
        if active_id:
            chosen = next((e for e in incomplete if e.get("id") == active_id), None)
        if chosen is None and incomplete:
            chosen = incomplete[0]

        steps = chosen.get("steps") if chosen and isinstance(chosen.get("steps"), list) else []
        steps_done = sum(1 for s in steps if isinstance(s, dict) and s.get("status") == "done")
        steps_total = len(steps)
        page = None
        excerpt_id = None
        if chosen:
            excerpt_id = str(chosen.get("id") or "") or None
            try:
                page = int(chosen.get("page")) if chosen.get("page") is not None else None
            except (TypeError, ValueError):
                page = None
            text = str(chosen.get("text") or "").strip()
            label = text[:72] + ("…" if len(text) > 72 else "") if text else "Continue StudyFlow"
            detail = f"{steps_done}/{steps_total} steps" if steps_total else "In progress"
        elif bookmark:
            excerpt_id = str(bookmark.get("excerpt_id") or "") or None
            try:
                page = int(bookmark.get("page")) if bookmark.get("page") is not None else None
            except (TypeError, ValueError):
                page = None
            snippet = str(bookmark.get("snippet") or "").strip()
            label = snippet[:72] + ("…" if len(snippet) > 72 else "") if snippet else f"Resume p{page or '?'}"
            detail = f"Bookmarked p{page}" if page else "Saved place"
        else:
            label = "Continue StudyFlow"
            detail = "Textbook attached"

        items.append(
            StudyFlowInProgressItem(
                course_id=course.id,
                course_name=course.name,
                course_code=course.code,
                run_id=run.id,
                resource_id=run.resource_id,
                excerpt_id=excerpt_id,
                page=page,
                label=label,
                detail=detail,
                steps_done=steps_done,
                steps_total=steps_total,
            )
        )
        if len(items) >= limit:
            break
    return items
