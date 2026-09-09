from __future__ import annotations

import base64
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LLMResult:
    content: str
    provider: str = "cursor"
    model_name: str | None = None


def is_llm_configured() -> bool:
    """True when Cursor API key is present (preferred agent backend)."""
    return bool(os.getenv("CURSOR_API_KEY", "").strip())


def _cursor_model_id() -> str:
    # Prefer explicit Auto / Router ids from the Cursor catalog.
    return (os.getenv("CURSOR_MODEL") or "auto").strip() or "auto"


def _cursor_cwd() -> str:
    """Sandboxed cwd so StudyFlows prompts don't mutate the app repo."""
    configured = os.getenv("CURSOR_AGENT_CWD", "").strip()
    if configured:
        Path(configured).mkdir(parents=True, exist_ok=True)
        return configured
    root = Path(tempfile.gettempdir()) / "planner-cursor-agent"
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


def _extract_result_text(result) -> str:
    text = getattr(result, "result", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    # Some SDK builds expose finished text via status + result fields only.
    status = getattr(result, "status", None)
    if status and status != "finished":
        raise RuntimeError(f"Cursor agent run status={status}")
    return (text or "").strip()


def chat_completion(
    *,
    system: str,
    user: str,
    model: str | None = None,
    grounding: str = "hybrid",
) -> LLMResult:
    """
    One-shot academic answer via Cursor Agent (Auto by default).

    Requires CURSOR_API_KEY. Model defaults to CURSOR_MODEL or "auto".
    grounding: "strict" | "hybrid" | "general"
    """
    api_key = os.getenv("CURSOR_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("CURSOR_API_KEY not set")

    from cursor_sdk import Agent, AgentOptions, LocalAgentOptions, ModelSelection

    model_id = (model or _cursor_model_id()).strip()
    # Router (Teams): auto-smart + optimize_for. Solo Auto fallback: id="auto".
    if model_id == "auto-smart":
        from cursor_sdk import ModelParameterValue

        selection = ModelSelection(
            id="auto-smart",
            params=[
                ModelParameterValue(
                    id="optimize_for",
                    value=(os.getenv("CURSOR_OPTIMIZE_FOR") or "balanced"),
                )
            ],
        )
    else:
        selection = ModelSelection(id=model_id)

    if grounding == "strict":
        ground_rule = (
            "Answer using only the sources/context in this message. "
            "If the answer is not present, say you could not find it in the provided materials."
        )
    elif grounding == "general":
        ground_rule = (
            "Answer helpfully from general academic knowledge. "
            "When course sources are present, prefer them and cite as [S#]."
        )
    else:
        ground_rule = (
            "Prefer the provided course sources and cite them as [S#] when used. "
            "If sources are missing or incomplete for a concept (definitions, background), "
            "answer using general academic knowledge and, when available, the web notes in this message. "
            "Never refuse a basic concept question just because it is not quoted in the sources — "
            "explain it clearly, then relate it to the course materials when possible."
        )

    prompt = (
        f"{system.strip()}\n\n"
        f"{user.strip()}\n\n"
        f"Instructions: {ground_rule} "
        "Do not edit files, run shell commands, or call tools. "
        "If the system message requires JSON, return JSON only with no markdown fences. "
        "Otherwise return the final answer as plain text only."
    )

    result = Agent.prompt(
        prompt,
        AgentOptions(
            api_key=api_key,
            model=selection,
            local=LocalAgentOptions(cwd=_cursor_cwd()),
        ),
    )
    content = _extract_result_text(result)
    if not content:
        raise RuntimeError("Cursor agent returned an empty answer")
    used_model = getattr(getattr(result, "model", None), "id", None) or model_id
    return LLMResult(content=content, provider="cursor", model_name=str(used_model))


def recognize_handwriting(*, image_png_base64: str, mode: str = "text") -> LLMResult:
    """
    Vision-style recognition via Cursor agent with an attached PNG.
    mode: "text" | "math"
    """
    api_key = os.getenv("CURSOR_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("CURSOR_API_KEY not set")

    from cursor_sdk import (
        Agent,
        AgentOptions,
        LocalAgentOptions,
        ModelSelection,
        SDKImage,
        UserMessage,
    )

    raw = image_png_base64.strip()
    if raw.startswith("data:"):
        # data:image/png;base64,....
        raw = raw.split(",", 1)[-1]
    # Validate base64 early
    base64.b64decode(raw, validate=False)

    if mode == "math":
        instruction = (
            "This image is handwritten math. Transcribe it. "
            "Return JSON only with keys text (plain reading) and latex (LaTeX without $$ wrappers). "
            "No markdown fences."
        )
    else:
        instruction = (
            "This image is handwriting. Transcribe it to plain text. "
            "Return JSON only with keys text and latex (latex may be null). "
            "No markdown fences."
        )

    model_id = _cursor_model_id()
    if model_id == "auto-smart":
        from cursor_sdk import ModelParameterValue

        selection = ModelSelection(
            id="auto-smart",
            params=[
                ModelParameterValue(
                    id="optimize_for",
                    value=(os.getenv("CURSOR_OPTIMIZE_FOR") or "balanced"),
                )
            ],
        )
    else:
        selection = ModelSelection(id=model_id)

    message = UserMessage(
        text=instruction,
        images=[SDKImage.data_image(raw, "image/png")],
    )
    result = Agent.prompt(
        message,
        AgentOptions(
            api_key=api_key,
            model=selection,
            local=LocalAgentOptions(cwd=_cursor_cwd()),
        ),
    )
    content = _extract_result_text(result)
    if not content:
        raise RuntimeError("Cursor agent returned empty handwriting recognition")
    used_model = getattr(getattr(result, "model", None), "id", None) or model_id
    return LLMResult(content=content, provider="cursor", model_name=str(used_model))
