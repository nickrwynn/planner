from __future__ import annotations

import json
import re


def parse_llm_json_object(text: str) -> dict:
    """
    Extract a single JSON object from LLM output (handles markdown fences and extra prose).
    """
    s = text.strip()
    fence = re.match(r"^```(?:json)?\s*\n", s)
    if fence:
        s = s[fence.end() :]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3].rstrip()

    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        s = s[start : end + 1]

    return json.loads(s)
