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

from app.ai.llm import chat_completion, is_llm_configured, recognize_handwriting
from app.ai.retrieval import retrieve_chunks
from app.ai.json_utils import parse_llm_json_object
from app.api.deps import get_current_user, get_db_from_request
from app.models.ai_conversation import AIConversation
from app.models.ai_message import AIMessage
from app.models.ai_usage_log import AIUsageLog
from app.schemas.ai import (
    AiStatusResponse,
    AskRequest,
    AskResponse,
    Citation,
    CompleteRequest,
    CompleteResponse,
    ConversationRead,
    HandwritingRequest,
    HandwritingResponse,
    MessageRead,
)
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
    context = "\n\n".join(context_lines) if context_lines else "(no course sources retrieved)"

    from app.ai.web_lookup import fetch_wikipedia_summary, looks_like_definition_query

    web_note = None
    if payload.allow_web_lookup and (not chunks or looks_like_definition_query(payload.message)):
        web_note = fetch_wikipedia_summary(payload.message)

    system = (
        "You are an academic assistant for students. "
        "When course sources are provided, prefer them and cite as [S#]. "
        "For definitions and background concepts (e.g. sample space, derivative, mitosis), "
        "always give a clear explanation even if those words are not in the sources. "
        "Then connect the explanation to the course materials when possible. "
        "If web notes are present, you may use them for background and say so briefly."
    )

    web_block = f"\n\nWeb notes:\n{web_note}" if web_note else ""
    user_prompt = (
        f"Question:\n{payload.message}\n\nCourse sources:\n{context}{web_block}\n\n"
        "Answer helpfully. Cite course sources as [S1], [S2] when you use them."
    )

    grounding = "strict"
    if payload.allow_general_knowledge:
        grounding = "hybrid" if chunks else "general"

    if is_llm_configured() and (chunks or payload.allow_general_knowledge):
        try:
            llm = chat_completion(system=system, user=user_prompt, grounding=grounding)
            answer = llm.content
            provider = getattr(llm, "provider", None) or "cursor"
            model_name = getattr(llm, "model_name", None) or os.getenv("CURSOR_MODEL", "auto")
        except Exception as exc:
            provider = "fallback"
            model_name = None
            if chunks:
                answer = (
                    f"Cursor agent failed ({exc}). Here are the most relevant source snippets:\n\n"
                    + "\n\n".join([f"[S{i}] {c.text[:400]}" for i, c in enumerate(chunks, start=1)])
                ).strip()
            else:
                answer = (
                    f"Cursor agent failed ({exc}). "
                    "I couldn't generate an answer right now — try again in a moment."
                )
    else:
        # Deterministic fallback for local dev without API keys
        provider = "fallback"
        model_name = None
        if not chunks:
            answer = (
                "No indexed sources were retrieved and the LLM is not configured "
                "(set CURSOR_API_KEY). Upload/reindex resources or configure AI to answer concept questions."
            )
        else:
            answer = (
                "LLM is not configured (set CURSOR_API_KEY). Here are the most relevant source snippets:\n\n"
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


@router.get("/status", response_model=AiStatusResponse)
def ai_status(user=Depends(get_current_user)):
    _ = user
    configured = is_llm_configured()
    model = os.getenv("CURSOR_MODEL", "auto") if configured else None
    if configured:
        return AiStatusResponse(
            configured=True,
            provider="cursor",
            model=model,
            message=f"Cursor agent ready (model={model}).",
        )
    return AiStatusResponse(
        configured=False,
        provider=None,
        model=None,
        message=(
            "Set CURSOR_API_KEY for Ask and Study Lab (Cursor Auto). "
            "Handwriting recognition runs on-device and does not need a key."
        ),
    )


_COMPLETE_SYSTEM = (
    "You continue a student's note in progress. Reply with ONLY the continuation text "
    "that should follow immediately after the given text — no quotes, no preamble, no "
    "restating what they wrote. Keep it to at most one short sentence (max 15 words). "
    "Match their tone and terminology. If no sensible continuation exists, reply with "
    "nothing at all."
)


@router.post("/complete", response_model=CompleteResponse)
def complete(payload: CompleteRequest, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    """Cloud backup for text completion; on-device handles the common case."""
    if not is_llm_configured():
        return CompleteResponse(completion="", provider=None)

    start = time.perf_counter()
    try:
        llm = chat_completion(
            system=_COMPLETE_SYSTEM,
            user=payload.text,
            grounding="general",
        )
    except Exception:
        # Never surface a completion failure to the editor — just offer nothing.
        return CompleteResponse(completion="", provider=None)

    text = (llm.content or "").strip().strip('"')
    # Guard against a chatty model returning a paragraph.
    if len(text) > 160:
        text = text[:160].rsplit(" ", 1)[0]

    _record_ai_usage(
        db,
        user_id=user.id,
        endpoint="/ai/complete",
        status="ok",
        provider=llm.provider,
        model_name=llm.model_name,
        metadata_json={"latency_ms": round((time.perf_counter() - start) * 1000, 2)},
    )
    return CompleteResponse(completion=text, provider=llm.provider)


@router.post("/handwriting", response_model=HandwritingResponse)
def handwriting(payload: HandwritingRequest, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    if not is_llm_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Cloud handwriting refinement is not configured (CURSOR_API_KEY). "
                "On-device recognition still works; only math/LaTeX needs the cloud."
            ),
        )
    start = time.perf_counter()
    try:
        llm = recognize_handwriting(image_png_base64=payload.image_base64, mode=payload.mode)
        try:
            obj = parse_llm_json_object(llm.content)
            text = str(obj.get("text") or "").strip()
            latex_raw = obj.get("latex")
            latex = str(latex_raw).strip() if latex_raw not in (None, "", "null") else None
        except Exception:
            text = llm.content.strip()
            latex = None
        if not text and latex:
            text = latex
        if not text:
            raise RuntimeError("No text recognized from handwriting")
        _record_ai_usage(
            db,
            user_id=user.id,
            endpoint="/ai/handwriting",
            status="ok",
            provider=llm.provider,
            model_name=llm.model_name,
            metadata_json={
                "mode": payload.mode,
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            },
        )
        return HandwritingResponse(
            text=text,
            latex=latex,
            provider=llm.provider,
            model_name=llm.model_name,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _record_ai_usage(
            db,
            user_id=user.id,
            endpoint="/ai/handwriting",
            status="error",
            provider="cursor",
            model_name=os.getenv("CURSOR_MODEL", "auto"),
            metadata_json={"error": str(exc)[:400]},
        )
        raise HTTPException(status_code=502, detail=f"Handwriting recognition failed: {exc}") from exc



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
        gen_kwargs = dict(
            user_id=user.id,
            course_id=course_id,
            resource_ids=source_ids,
            title=title,
            section_keys=payload.section_keys,
            page_start=payload.page_start,
            page_end=payload.page_end,
        )
        if art.artifact_type == "summary":
            new_art = generate_summary(db, **gen_kwargs)
        elif art.artifact_type == "flashcards":
            new_art = generate_flashcards(db, **gen_kwargs)
        elif art.artifact_type == "quiz":
            new_art = generate_quiz(db, **gen_kwargs)
        elif art.artifact_type == "sample_problems":
            new_art = generate_sample_problems(db, **gen_kwargs)
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
    obj = art.content_json or {}
    lines = [f"# {art.title}", ""]
    if art.artifact_type == "summary":
        for section in obj.get("sections") or []:
            lines.append(f"## {section.get('heading') or 'Section'}")
            for bullet in section.get("bullets") or []:
                lines.append(f"- {bullet}")
            lines.append("")
    elif art.artifact_type == "flashcards":
        for i, card in enumerate(obj.get("cards") or [], start=1):
            lines.append(f"## Card {i}")
            lines.append(f"**Q:** {card.get('question') or ''}")
            lines.append(f"**A:** {card.get('answer') or ''}")
            lines.append("")
    elif art.artifact_type == "quiz":
        for i, item in enumerate(obj.get("items") or [], start=1):
            lines.append(f"## Q{i}. {item.get('question') or ''}")
            lines.append(f"**Answer:** {item.get('answer') or ''}")
            if item.get("explanation"):
                lines.append(f"**Explanation:** {item['explanation']}")
            lines.append("")
    elif art.artifact_type == "sample_problems":
        for i, problem in enumerate(obj.get("problems") or [], start=1):
            lines.append(f"## Problem {i}")
            lines.append(problem.get("problem") or "")
            lines.append("")
            lines.append(f"**Solution:** {problem.get('solution') or ''}")
            lines.append("")
    else:
        lines.append("```json")
        lines.append(json.dumps(obj, indent=2))
        lines.append("```")
    return {"markdown": "\n".join(lines).strip() + "\n"}


@router.post("/summaries", response_model=SummaryResponse)
def summaries(payload: GenerateBaseRequest, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    try:
        art = generate_summary(
            db,
            user_id=user.id,
            course_id=payload.course_id,
            resource_ids=payload.resource_ids,
            title=payload.title,
            section_keys=payload.section_keys,
            page_start=payload.page_start,
            page_end=payload.page_end,
        )
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
        metadata_json={"resource_count": len(payload.resource_ids), "section_keys": payload.section_keys},
    )
    return SummaryResponse(artifact_id=art.id, title=art.title, sections=obj.get("sections", []), created_at=art.created_at)


@router.post("/flashcards", response_model=FlashcardsResponse)
def flashcards(payload: GenerateBaseRequest, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    try:
        art = generate_flashcards(
            db,
            user_id=user.id,
            course_id=payload.course_id,
            resource_ids=payload.resource_ids,
            title=payload.title,
            section_keys=payload.section_keys,
            page_start=payload.page_start,
            page_end=payload.page_end,
            context_text=payload.context_text,
        )
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
        metadata_json={"resource_count": len(payload.resource_ids), "section_keys": payload.section_keys},
    )
    return FlashcardsResponse(artifact_id=art.id, title=art.title, cards=obj.get("cards", []), created_at=art.created_at)


@router.post("/quizzes", response_model=QuizResponse)
def quizzes(payload: GenerateBaseRequest, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    try:
        art = generate_quiz(
            db,
            user_id=user.id,
            course_id=payload.course_id,
            resource_ids=payload.resource_ids,
            title=payload.title,
            section_keys=payload.section_keys,
            page_start=payload.page_start,
            page_end=payload.page_end,
            context_text=payload.context_text,
        )
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
        metadata_json={"resource_count": len(payload.resource_ids), "section_keys": payload.section_keys},
    )
    return QuizResponse(artifact_id=art.id, title=art.title, items=obj.get("items", []), created_at=art.created_at)


@router.post("/sample-problems", response_model=SampleProblemsResponse)
def sample_problems(payload: GenerateBaseRequest, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    try:
        art = generate_sample_problems(
            db,
            user_id=user.id,
            course_id=payload.course_id,
            resource_ids=payload.resource_ids,
            title=payload.title,
            section_keys=payload.section_keys,
            page_start=payload.page_start,
            page_end=payload.page_end,
            context_text=payload.context_text,
        )
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
        metadata_json={"resource_count": len(payload.resource_ids), "section_keys": payload.section_keys},
    )
    return SampleProblemsResponse(artifact_id=art.id, title=art.title, problems=obj.get("problems", []), created_at=art.created_at)

