from __future__ import annotations

from uuid import UUID

from pydantic import ValidationError

from sqlalchemy.orm import Session

from app.ai.json_utils import parse_llm_json_object
from app.ai.llm import chat_completion, is_llm_configured
from app.ai.retrieval import PageRange, retrieve_chunks
from app.models.study_artifact import StudyArtifact
from app.schemas.ai import Citation
from app.schemas.study import (
    LlmFlashcardsContent,
    LlmQuizContent,
    LlmSampleProblemsContent,
    LlmSummaryContent,
)
from app.services.resource_sections import list_resource_sections

_FRONT_MATTER_RULE = (
    "Ignore copyright pages, title pages, publisher blurbs, tables of contents, "
    "author bios, series lists, and 'about this book' preface material. "
    "Use only substantive chapter/section content from the sources."
)

_STUDY_ARTIFACT_NONEMPTY = (
    "Never return empty content arrays. If sources are thin, still produce the best "
    "possible study items grounded in whatever body text is present."
)


def _sources_block(chunks, *, context_text: str | None = None) -> str:
    parts: list[str] = []
    if context_text and context_text.strip():
        parts.append(f"[Highlight]\n{context_text.strip()}")
    lines: list[str] = []
    for i, c in enumerate(chunks, start=1):
        lines.append(f"[S{i}] resource={c.resource_id} page={c.page_number or '-'} chunk={c.chunk_index}\n{c.text}")
    if lines:
        parts.append("\n\n".join(lines))
    return "\n\n".join(parts) if parts else "(no sources found)"


def _citations_from_chunks(chunks) -> list[Citation]:
    return [
        Citation(
            resource_id=c.resource_id,
            page_number=c.page_number,
            chunk_id=c.chunk_id,
            chunk_index=c.chunk_index,
            snippet=c.text[:300],
        )
        for c in chunks
    ]


def _ensure_llm() -> None:
    if not is_llm_configured():
        raise RuntimeError("LLM not configured (set CURSOR_API_KEY)")


def _validate_summary(obj: dict) -> dict:
    try:
        return LlmSummaryContent.model_validate(obj).model_dump(mode="json")
    except ValidationError as e:
        raise ValueError(f"Invalid summary JSON shape: {e}") from e


def _validate_flashcards(obj: dict) -> dict:
    try:
        return LlmFlashcardsContent.model_validate(obj).model_dump(mode="json")
    except ValidationError as e:
        raise ValueError(f"Invalid flashcards JSON shape: {e}") from e


def _validate_quiz(obj: dict) -> dict:
    try:
        return LlmQuizContent.model_validate(obj).model_dump(mode="json")
    except ValidationError as e:
        raise ValueError(f"Invalid quiz JSON shape: {e}") from e


def _validate_sample_problems(obj: dict) -> dict:
    try:
        return LlmSampleProblemsContent.model_validate(obj).model_dump(mode="json")
    except ValidationError as e:
        raise ValueError(f"Invalid sample problems JSON shape: {e}") from e


def _resolve_scope(
    db: Session,
    *,
    user_id: UUID,
    resource_ids: list[UUID],
    section_keys: list[str] | None,
    page_start: int | None,
    page_end: int | None,
) -> tuple[list[PageRange] | None, str, dict]:
    """
    Resolve section keys / explicit pages into page ranges + retrieval query hint + metadata.
    """
    meta: dict = {
        "section_keys": list(section_keys or []),
        "page_start": page_start,
        "page_end": page_end,
    }
    ranges: list[PageRange] = []
    labels: list[str] = []

    keys = [k.strip() for k in (section_keys or []) if k and k.strip()]
    if keys and resource_ids:
        # Use first selected textbook resource for TOC lookup (typical Study Lab usage).
        from app.models.user import User

        user = db.get(User, user_id)
        if user:
            for rid in resource_ids:
                try:
                    sections = list_resource_sections(db, user=user, resource_id=rid)
                except ValueError:
                    continue
                by_key = {s.key: s for s in sections}
                for key in keys:
                    sec = by_key.get(key)
                    if not sec:
                        continue
                    labels.append(f"{sec.key} {sec.title}".strip())
                    if sec.page_start is not None:
                        end = sec.page_end if sec.page_end is not None else sec.page_start
                        ranges.append(PageRange(start=int(sec.page_start), end=int(end)))
                if ranges:
                    break

    if page_start is not None or page_end is not None:
        start = int(page_start or 1)
        end = int(page_end or page_start or start)
        if end < start:
            start, end = end, start
        ranges.append(PageRange(start=start, end=end))
        labels.append(f"pages {start}-{end}")

    # Dedupe overlapping ranges lightly
    unique: list[PageRange] = []
    seen: set[tuple[int, int]] = set()
    for r in ranges:
        tup = (r.start, r.end)
        if tup in seen:
            continue
        seen.add(tup)
        unique.append(r)

    scope_label = "; ".join(labels[:6]) if labels else "selected readings"
    meta["resolved_page_ranges"] = [{"start": r.start, "end": r.end} for r in unique]
    meta["scope_label"] = scope_label
    return (unique or None), scope_label, meta


def _retrieve_for_artifact(
    db: Session,
    *,
    user_id: UUID,
    course_id: UUID | None,
    resource_ids: list[UUID],
    base_query: str,
    section_keys: list[str] | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
    k: int = 12,
    context_text: str | None = None,
):
    ranges, scope_label, scope_meta = _resolve_scope(
        db,
        user_id=user_id,
        resource_ids=resource_ids,
        section_keys=section_keys,
        page_start=page_start,
        page_end=page_end,
    )
    query = f"{base_query} {scope_label}".strip()
    chunks = retrieve_chunks(
        db,
        user_id=user_id,
        query=query,
        course_id=course_id,
        resource_ids=resource_ids,
        k=k,
        page_ranges=ranges,
    )
    if not chunks and not (context_text and context_text.strip()):
        if ranges:
            raise ValueError(
                f"No indexed text found in page range for scope '{scope_label}'. "
                "Reindex the PDF or pick a different section."
            )
        raise ValueError("No indexed text found for this resource. Highlight text or reindex the PDF.")
    if context_text and context_text.strip():
        scope_meta = {**scope_meta, "highlight_context": True}
    return chunks, scope_label, scope_meta


def generate_summary(
    db: Session,
    *,
    user_id: UUID,
    course_id: UUID | None,
    resource_ids: list[UUID],
    title: str | None,
    section_keys: list[str] | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
) -> StudyArtifact:
    _ensure_llm()
    chunks, scope_label, scope_meta = _retrieve_for_artifact(
        db,
        user_id=user_id,
        course_id=course_id,
        resource_ids=resource_ids,
        base_query="definition example theorem formula exercise concept",
        section_keys=section_keys,
        page_start=page_start,
        page_end=page_end,
        k=12,
    )
    sources = _sources_block(chunks)
    system = (
        "You generate study artifacts grounded in sources. Output STRICT JSON only. "
        + _FRONT_MATTER_RULE
        + " "
        + _STUDY_ARTIFACT_NONEMPTY
    )
    user = (
        'Create a structured chapter summary as JSON: '
        '{"title": str, "sections": [{"heading": str, "bullets": [str]}]}.\n'
        f"Scope: {scope_label}. Focus on definitions, theorems, worked examples, and techniques "
        "from the body text in this scope only.\n"
        f"Use concise bullets. Include at least 2 sections.\n\nSources:\n{sources}"
    )
    content = chat_completion(system=system, user=user).content
    obj = _validate_summary(parse_llm_json_object(content))
    default_title = title or obj.get("title") or f"Summary · {scope_label}"
    artifact = StudyArtifact(
        user_id=user_id,
        course_id=course_id,
        artifact_type="summary",
        title=default_title,
        source_resource_ids_json=[str(rid) for rid in resource_ids],
        content_json=obj,
        metadata_json={
            "citations": [c.model_dump(mode="json") for c in _citations_from_chunks(chunks)],
            "scope": scope_meta,
        },
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def generate_flashcards(
    db: Session,
    *,
    user_id: UUID,
    course_id: UUID | None,
    resource_ids: list[UUID],
    title: str | None,
    section_keys: list[str] | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
    context_text: str | None = None,
) -> StudyArtifact:
    _ensure_llm()
    chunks, scope_label, scope_meta = _retrieve_for_artifact(
        db,
        user_id=user_id,
        course_id=course_id,
        resource_ids=resource_ids,
        base_query="definition formula theorem property example concept",
        section_keys=section_keys,
        page_start=page_start,
        page_end=page_end,
        k=12,
        context_text=context_text,
    )
    sources = _sources_block(chunks, context_text=context_text)
    system = (
        "You generate flashcards grounded in sources. Output STRICT JSON only. "
        + _FRONT_MATTER_RULE
        + " "
        + _STUDY_ARTIFACT_NONEMPTY
    )
    user = (
        'Return JSON: {"title": str, "cards": [{"question": str, "answer": str}]}\n'
        f"Scope: {scope_label}. Make cards from definitions, formulas, and key facts in this scope.\n"
        "Produce at least 5 cards. Never return an empty cards array.\n\n"
        f"Sources:\n{sources}"
    )
    obj = _validate_flashcards(parse_llm_json_object(chat_completion(system=system, user=user).content))
    artifact = StudyArtifact(
        user_id=user_id,
        course_id=course_id,
        artifact_type="flashcards",
        title=title or obj.get("title") or f"Flashcards · {scope_label}",
        source_resource_ids_json=[str(rid) for rid in resource_ids],
        content_json=obj,
        metadata_json={
            "citations": [c.model_dump(mode="json") for c in _citations_from_chunks(chunks)],
            "scope": scope_meta,
        },
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def generate_quiz(
    db: Session,
    *,
    user_id: UUID,
    course_id: UUID | None,
    resource_ids: list[UUID],
    title: str | None,
    section_keys: list[str] | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
    context_text: str | None = None,
) -> StudyArtifact:
    _ensure_llm()
    chunks, scope_label, scope_meta = _retrieve_for_artifact(
        db,
        user_id=user_id,
        course_id=course_id,
        resource_ids=resource_ids,
        base_query="example exercise compute solve apply method",
        section_keys=section_keys,
        page_start=page_start,
        page_end=page_end,
        k=14,
        context_text=context_text,
    )
    sources = _sources_block(chunks, context_text=context_text)
    system = (
        "You generate quiz items grounded in sources. Output STRICT JSON only. "
        + _FRONT_MATTER_RULE
        + " "
        + _STUDY_ARTIFACT_NONEMPTY
    )
    user = (
        'Return JSON: {"title": str, "items": [{"question": str, "answer": str, "explanation": str}]}\n'
        f"Scope: {scope_label}. Write short quiz items that test understanding of this scope.\n"
        "Produce at least 4 items. Never return an empty items array.\n\n"
        f"Sources:\n{sources}"
    )
    obj = _validate_quiz(parse_llm_json_object(chat_completion(system=system, user=user).content))
    artifact = StudyArtifact(
        user_id=user_id,
        course_id=course_id,
        artifact_type="quiz",
        title=title or obj.get("title") or f"Quiz · {scope_label}",
        source_resource_ids_json=[str(rid) for rid in resource_ids],
        content_json=obj,
        metadata_json={
            "citations": [c.model_dump(mode="json") for c in _citations_from_chunks(chunks)],
            "scope": scope_meta,
        },
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def generate_sample_problems(
    db: Session,
    *,
    user_id: UUID,
    course_id: UUID | None,
    resource_ids: list[UUID],
    title: str | None,
    section_keys: list[str] | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
    context_text: str | None = None,
) -> StudyArtifact:
    _ensure_llm()
    chunks, scope_label, scope_meta = _retrieve_for_artifact(
        db,
        user_id=user_id,
        course_id=course_id,
        resource_ids=resource_ids,
        base_query="worked example exercise solution compute apply",
        section_keys=section_keys,
        page_start=page_start,
        page_end=page_end,
        k=14,
        context_text=context_text,
    )
    sources = _sources_block(chunks, context_text=context_text)
    system = (
        "You generate sample problems grounded in sources. Output STRICT JSON only. "
        + _FRONT_MATTER_RULE
        + " "
        + _STUDY_ARTIFACT_NONEMPTY
    )
    user = (
        'Return JSON: {"title": str, "problems": [{"problem": str, "solution": str}]}\n'
        f"Scope: {scope_label}. Prefer adapting worked examples from this scope into practice problems.\n"
        "Produce at least 2 problems. Never return an empty problems array.\n\n"
        f"Sources:\n{sources}"
    )
    obj = _validate_sample_problems(parse_llm_json_object(chat_completion(system=system, user=user).content))
    artifact = StudyArtifact(
        user_id=user_id,
        course_id=course_id,
        artifact_type="sample_problems",
        title=title or obj.get("title") or f"Sample Problems · {scope_label}",
        source_resource_ids_json=[str(rid) for rid in resource_ids],
        content_json=obj,
        metadata_json={
            "citations": [c.model_dump(mode="json") for c in _citations_from_chunks(chunks)],
            "scope": scope_meta,
        },
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact
