from __future__ import annotations

from uuid import UUID

from pydantic import ValidationError

from sqlalchemy.orm import Session

from app.ai.json_utils import parse_llm_json_object
from app.ai.llm import chat_completion, is_llm_configured
from app.ai.retrieval import retrieve_chunks
from app.models.study_artifact import StudyArtifact
from app.schemas.ai import Citation
from app.schemas.study import (
    LlmFlashcardsContent,
    LlmQuizContent,
    LlmSampleProblemsContent,
    LlmSummaryContent,
)


def _sources_block(chunks) -> str:
    lines: list[str] = []
    for i, c in enumerate(chunks, start=1):
        lines.append(f"[S{i}] resource={c.resource_id} page={c.page_number or '-'} chunk={c.chunk_index}\n{c.text}")
    return "\n\n".join(lines) if lines else "(no sources found)"


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
        raise RuntimeError("LLM not configured (set OPENAI_API_KEY)")


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


def generate_summary(
    db: Session,
    *,
    user_id: UUID,
    course_id: UUID | None,
    resource_ids: list[UUID],
    title: str | None,
) -> StudyArtifact:
    _ensure_llm()
    chunks = retrieve_chunks(db, user_id=user_id, query="summarize key concepts", course_id=course_id, resource_ids=resource_ids, k=12)
    sources = _sources_block(chunks)
    system = "You generate study artifacts grounded in sources. Output STRICT JSON only."
    user = (
        f"Create a structured summary as JSON: {{\"title\": str, \"sections\": [{{\"heading\": str, \"bullets\": [str]}}]}}.\n"
        f"Use concise bullets.\n\nSources:\n{sources}"
    )
    content = chat_completion(system=system, user=user).content
    obj = _validate_summary(parse_llm_json_object(content))
    artifact = StudyArtifact(
        user_id=user_id,
        course_id=course_id,
        artifact_type="summary",
        title=title or obj.get("title") or "Summary",
        source_resource_ids_json=[str(rid) for rid in resource_ids],
        content_json=obj,
        metadata_json={"citations": [c.model_dump(mode="json") for c in _citations_from_chunks(chunks)]},
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def generate_flashcards(db: Session, *, user_id: UUID, course_id: UUID | None, resource_ids: list[UUID], title: str | None) -> StudyArtifact:
    _ensure_llm()
    chunks = retrieve_chunks(db, user_id=user_id, query="flashcards key facts", course_id=course_id, resource_ids=resource_ids, k=12)
    sources = _sources_block(chunks)
    system = "You generate flashcards grounded in sources. Output STRICT JSON only."
    user = (
        "Return JSON: {\"title\": str, \"cards\": [{\"question\": str, \"answer\": str}]}\n\n"
        f"Sources:\n{sources}"
    )
    obj = _validate_flashcards(parse_llm_json_object(chat_completion(system=system, user=user).content))
    artifact = StudyArtifact(
        user_id=user_id,
        course_id=course_id,
        artifact_type="flashcards",
        title=title or obj.get("title") or "Flashcards",
        source_resource_ids_json=[str(rid) for rid in resource_ids],
        content_json=obj,
        metadata_json={"citations": [c.model_dump(mode="json") for c in _citations_from_chunks(chunks)]},
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def generate_quiz(db: Session, *, user_id: UUID, course_id: UUID | None, resource_ids: list[UUID], title: str | None) -> StudyArtifact:
    _ensure_llm()
    chunks = retrieve_chunks(db, user_id=user_id, query="quiz questions", course_id=course_id, resource_ids=resource_ids, k=14)
    sources = _sources_block(chunks)
    system = "You generate quiz items grounded in sources. Output STRICT JSON only."
    user = (
        "Return JSON: {\"title\": str, \"items\": [{\"question\": str, \"answer\": str, \"explanation\": str}]}\n\n"
        f"Sources:\n{sources}"
    )
    obj = _validate_quiz(parse_llm_json_object(chat_completion(system=system, user=user).content))
    artifact = StudyArtifact(
        user_id=user_id,
        course_id=course_id,
        artifact_type="quiz",
        title=title or obj.get("title") or "Quiz",
        source_resource_ids_json=[str(rid) for rid in resource_ids],
        content_json=obj,
        metadata_json={"citations": [c.model_dump(mode="json") for c in _citations_from_chunks(chunks)]},
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def generate_sample_problems(
    db: Session, *, user_id: UUID, course_id: UUID | None, resource_ids: list[UUID], title: str | None
) -> StudyArtifact:
    _ensure_llm()
    chunks = retrieve_chunks(db, user_id=user_id, query="sample problems", course_id=course_id, resource_ids=resource_ids, k=14)
    sources = _sources_block(chunks)
    system = "You generate sample problems grounded in sources. Output STRICT JSON only."
    user = (
        "Return JSON: {\"title\": str, \"problems\": [{\"problem\": str, \"solution\": str}]}\n\n"
        f"Sources:\n{sources}"
    )
    obj = _validate_sample_problems(parse_llm_json_object(chat_completion(system=system, user=user).content))
    artifact = StudyArtifact(
        user_id=user_id,
        course_id=course_id,
        artifact_type="sample_problems",
        title=title or obj.get("title") or "Sample Problems",
        source_resource_ids_json=[str(rid) for rid in resource_ids],
        content_json=obj,
        metadata_json={"citations": [c.model_dump(mode="json") for c in _citations_from_chunks(chunks)]},
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact

