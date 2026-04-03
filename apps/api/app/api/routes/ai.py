from __future__ import annotations

import json
import os
import re
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.llm import chat_completion, is_llm_configured
from app.ai.retrieval import retrieve_chunks
from app.api.deps import get_current_user, get_db_from_request
from app.models.ai_conversation import AIConversation
from app.models.ai_message import AIMessage
from app.models.ai_usage_log import AIUsageLog
from app.schemas.ai import AskRequest, AskResponse, Citation, ConversationRead, MessageRead
from app.schemas.study import (
    ArtifactRegenerateRequest,
    ArtifactListItem,
    ArtifactUpdateRequest,
    FlashcardsResponse,
    GenerateBaseRequest,
    QuizResponse,
    SampleProblemsResponse,
    StudyArtifactRead,
    SummaryResponse,
)
from app.ai.study_lab import (
    generate_flashcards,
    generate_quiz,
    generate_sample_problems,
    generate_summary,
)
from app.models.study_artifact import StudyArtifact

router = APIRouter(prefix="/ai", tags=["ai"])


def _record_ai_usage(
    db: Session,
    *,
    user_id,
    endpoint: str,
    status: str,
    metadata_json: dict | None = None,
    provider: str | None = None,
    model_name: str | None = None,
) -> None:
    log = AIUsageLog(
        user_id=user_id,
        endpoint=endpoint,
        status=status,
        provider=provider,
        model_name=model_name,
        metadata_json=metadata_json,
    )
    db.add(log)
    db.commit()


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    q = (
        select(AIConversation)
        .where(AIConversation.user_id == user.id)
        .order_by(AIConversation.updated_at.desc())
        .limit(limit)
    )
    return list(db.execute(q).scalars().all())


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageRead])
def list_conversation_messages(
    conversation_id: UUID,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    convo = db.get(AIConversation, conversation_id)
    if not convo or convo.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    q = (
        select(AIMessage)
        .where(
            AIMessage.conversation_id == conversation_id,
            AIMessage.user_id == user.id,
        )
        .order_by(AIMessage.created_at.asc())
    )
    return list(db.execute(q).scalars().all())


@router.patch("/conversations/{conversation_id}", response_model=ConversationRead)
def rename_conversation(
    conversation_id: UUID,
    title: str = Query(min_length=1, max_length=200),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    convo = db.get(AIConversation, conversation_id)
    if not convo or convo.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    convo.title = title.strip()
    db.add(convo)
    db.commit()
    db.refresh(convo)
    return convo


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    convo = db.get(AIConversation, conversation_id)
    if not convo or convo.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete(convo)
    db.commit()
    return {"ok": True}


@router.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    start = time.perf_counter()
    # Conversation handling
    convo: AIConversation | None = None
    if payload.conversation_id:
        convo = db.get(AIConversation, payload.conversation_id)
        if convo and convo.user_id != user.id:
            convo = None

    if convo is None:
        convo = AIConversation(user_id=user.id, course_id=payload.course_id, title=None, mode="ask")
        db.add(convo)
        db.commit()
        db.refresh(convo)

    # Store user message
    user_msg = AIMessage(
        user_id=user.id,
        conversation_id=convo.id,
        role="user",
        content=payload.message,
        citations_json=None,
    )
    db.add(user_msg)
    db.commit()

    # Retrieval
    chunks = retrieve_chunks(
        db,
        user_id=user.id,
        query=payload.message,
        course_id=payload.course_id,
        resource_ids=payload.resource_ids,
        k=payload.top_k,
    )

    all_citations = [
        Citation(
            resource_id=c.resource_id,
            page_number=c.page_number,
            chunk_id=c.chunk_id,
            chunk_index=c.chunk_index,
            snippet=c.text[:300],
        )
        for c in chunks
    ]

    context_lines: list[str] = []
    for i, c in enumerate(chunks, start=1):
        context_lines.append(
            f"[S{i}] resource={c.resource_id} page={c.page_number or '-'} chunk={c.chunk_index}\n{c.text}"
        )
    context = "\n\n".join(context_lines) if context_lines else "(no sources found)"

    system = (
        "You are an academic assistant. Use the provided sources when possible. "
        "If you use a source, cite it as [S#]. If no sources, say so explicitly."
    )

    user_prompt = f"Question:\n{payload.message}\n\nSources:\n{context}\n\nAnswer with citations like [S1], [S2]."

    if is_llm_configured() and chunks:
        model_name = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        answer = chat_completion(system=system, user=user_prompt).content
        provider = "openai"
    else:
        # Deterministic fallback for local dev without API keys
        provider = "fallback"
        model_name = None
        if not chunks:
            answer = (
                "No indexed sources were retrieved for your query. "
                "Upload or reindex relevant resources and try again."
            )
        else:
            answer = (
                "LLM is not configured (set OPENAI_API_KEY). Here are the most relevant source snippets:\n\n"
                + "\n\n".join([f"[S{i}] {c.text[:400]}" for i, c in enumerate(chunks, start=1)])
            ).strip()

    citations = all_citations
    if chunks:
        cited_ids = {int(m.group(1)) for m in re.finditer(r"\[S(\d+)\]", answer)}
        invalid = sorted([idx for idx in cited_ids if idx < 1 or idx > len(chunks)])
        valid = sorted([idx for idx in cited_ids if 1 <= idx <= len(chunks)])
        if invalid:
            answer = f"{answer}\n\n[system] Invalid citation references removed: {invalid}"
        if valid:
            citations = [all_citations[idx - 1] for idx in valid]
        else:
            # If model responded without explicit citations, return top retrieved chunks
            # so clients can still render grounded sources.
            citations = all_citations[: min(3, len(all_citations))]

    assistant_msg = AIMessage(
        user_id=user.id,
        conversation_id=convo.id,
        role="assistant",
        content=answer,
        citations_json=[c.model_dump(mode="json") for c in citations],
    )
    db.add(assistant_msg)
    db.commit()
    _record_ai_usage(
        db,
        user_id=user.id,
        endpoint="/ai/ask",
        status="ok",
        provider=provider,
        model_name=model_name,
        metadata_json={
            "top_k": payload.top_k,
            "retrieved_chunks": len(chunks),
            "citations": len(citations),
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
        },
    )

    return AskResponse(conversation_id=convo.id, answer=answer, citations=citations)


@router.get("/artifacts", response_model=list[ArtifactListItem])
def list_artifacts(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    q = (
        select(StudyArtifact)
        .where(StudyArtifact.user_id == user.id)
        .order_by(StudyArtifact.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(q).scalars().all())


@router.get("/artifacts/{artifact_id}", response_model=StudyArtifactRead)
def get_artifact(artifact_id: UUID, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    art = db.get(StudyArtifact, artifact_id)
    if not art or art.user_id != user.id:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return art


@router.patch("/artifacts/{artifact_id}", response_model=StudyArtifactRead)
def update_artifact(
    artifact_id: UUID,
    payload: ArtifactUpdateRequest,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    art = db.get(StudyArtifact, artifact_id)
    if not art or art.user_id != user.id:
        raise HTTPException(status_code=404, detail="Artifact not found")
    patch = payload.model_dump(exclude_unset=True)
    if "title" in patch and patch["title"] is not None:
        art.title = patch["title"]
    if "content_json" in patch:
        art.content_json = patch["content_json"]
    db.add(art)
    db.commit()
    db.refresh(art)
    return art


@router.post("/artifacts/{artifact_id}/regenerate", response_model=StudyArtifactRead)
def regenerate_artifact(
    artifact_id: UUID,
    payload: ArtifactRegenerateRequest,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    art = db.get(StudyArtifact, artifact_id)
    if not art or art.user_id != user.id:
        raise HTTPException(status_code=404, detail="Artifact not found")

    source_ids = payload.resource_ids or []
    if not source_ids:
        source_ids = [UUID(str(x)) for x in (art.source_resource_ids_json or [])]
    if not source_ids:
        raise HTTPException(status_code=422, detail="No source resources available to regenerate artifact")

    course_id = payload.course_id if payload.course_id is not None else art.course_id
    title = payload.title or art.title

    try:
        if art.artifact_type == "summary":
            new_art = generate_summary(db, user_id=user.id, course_id=course_id, resource_ids=source_ids, title=title)
        elif art.artifact_type == "flashcards":
            new_art = generate_flashcards(db, user_id=user.id, course_id=course_id, resource_ids=source_ids, title=title)
        elif art.artifact_type == "quiz":
            new_art = generate_quiz(db, user_id=user.id, course_id=course_id, resource_ids=source_ids, title=title)
        elif art.artifact_type == "sample_problems":
            new_art = generate_sample_problems(db, user_id=user.id, course_id=course_id, resource_ids=source_ids, title=title)
        else:
            raise HTTPException(status_code=422, detail=f"Unsupported artifact type: {art.artifact_type}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return new_art


@router.get("/artifacts/{artifact_id}/export")
def export_artifact(
    artifact_id: UUID,
    format: str = Query(default="json", pattern="^(json|markdown)$"),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    art = db.get(StudyArtifact, artifact_id)
    if not art or art.user_id != user.id:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if format == "json":
        return {
            "id": str(art.id),
            "title": art.title,
            "artifact_type": art.artifact_type,
            "content_json": art.content_json,
            "metadata_json": art.metadata_json,
            "source_resource_ids_json": art.source_resource_ids_json,
        }
    payload = {
        "title": art.title,
        "artifact_type": art.artifact_type,
        "content_json": art.content_json,
    }
    markdown = f"# {art.title}\n\n```json\n{json.dumps(payload, indent=2)}\n```\n"
    return {"markdown": markdown}


@router.post("/summaries", response_model=SummaryResponse)
def summaries(payload: GenerateBaseRequest, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    try:
        art = generate_summary(db, user_id=user.id, course_id=payload.course_id, resource_ids=payload.resource_ids, title=payload.title)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    obj = art.content_json or {}
    _record_ai_usage(
        db,
        user_id=user.id,
        endpoint="/ai/summaries",
        status="ok",
        metadata_json={"resource_count": len(payload.resource_ids)},
    )
    return SummaryResponse(artifact_id=art.id, title=art.title, sections=obj.get("sections", []), created_at=art.created_at)


@router.post("/flashcards", response_model=FlashcardsResponse)
def flashcards(payload: GenerateBaseRequest, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    try:
        art = generate_flashcards(db, user_id=user.id, course_id=payload.course_id, resource_ids=payload.resource_ids, title=payload.title)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    obj = art.content_json or {}
    _record_ai_usage(
        db,
        user_id=user.id,
        endpoint="/ai/flashcards",
        status="ok",
        metadata_json={"resource_count": len(payload.resource_ids)},
    )
    return FlashcardsResponse(artifact_id=art.id, title=art.title, cards=obj.get("cards", []), created_at=art.created_at)


@router.post("/quizzes", response_model=QuizResponse)
def quizzes(payload: GenerateBaseRequest, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    try:
        art = generate_quiz(db, user_id=user.id, course_id=payload.course_id, resource_ids=payload.resource_ids, title=payload.title)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    obj = art.content_json or {}
    _record_ai_usage(
        db,
        user_id=user.id,
        endpoint="/ai/quizzes",
        status="ok",
        metadata_json={"resource_count": len(payload.resource_ids)},
    )
    return QuizResponse(artifact_id=art.id, title=art.title, items=obj.get("items", []), created_at=art.created_at)


@router.post("/sample-problems", response_model=SampleProblemsResponse)
def sample_problems(payload: GenerateBaseRequest, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    try:
        art = generate_sample_problems(db, user_id=user.id, course_id=payload.course_id, resource_ids=payload.resource_ids, title=payload.title)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    obj = art.content_json or {}
    _record_ai_usage(
        db,
        user_id=user.id,
        endpoint="/ai/sample-problems",
        status="ok",
        metadata_json={"resource_count": len(payload.resource_ids)},
    )
    return SampleProblemsResponse(artifact_id=art.id, title=art.title, problems=obj.get("problems", []), created_at=art.created_at)

