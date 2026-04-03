from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMResult:
    content: str


def is_llm_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def chat_completion(*, system: str, user: str, model: str | None = None) -> LLMResult:
    """
    MVP LLM call: OpenAI Chat Completions.
    If not configured, raises RuntimeError (caller should fallback).
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    m = model or os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    resp = client.chat.completions.create(
        model=m,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return LLMResult(content=resp.choices[0].message.content or "")

