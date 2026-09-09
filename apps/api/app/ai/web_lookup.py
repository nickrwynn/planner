from __future__ import annotations

import re
from urllib.parse import quote

import httpx


def looks_like_definition_query(query: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return False
    if len(q.split()) <= 8 and re.search(
        r"\b(what is|what's|define|definition|meaning of|explain)\b",
        q,
    ):
        return True
    # Short noun-phrase questions often need general knowledge
    return bool(re.match(r"^(what|who|where|when|why|how)\b", q)) and len(q) < 120


def fetch_wikipedia_summary(query: str, *, timeout: float = 6.0) -> str | None:
    """Best-effort public summary for definitional questions (no API key)."""
    title = _guess_wiki_title(query)
    if not title:
        return None
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            res = client.get(url, headers={"Accept": "application/json", "User-Agent": "StudyFlows/1.0"})
            if res.status_code == 404:
                # search then fetch
                search = client.get(
                    "https://en.wikipedia.org/w/rest.php/v1/search/title",
                    params={"q": title, "limit": 1},
                    headers={"User-Agent": "StudyFlows/1.0"},
                )
                if search.status_code >= 400:
                    return None
                pages = (search.json() or {}).get("pages") or []
                if not pages:
                    return None
                hit = pages[0].get("key") or pages[0].get("title")
                if not hit:
                    return None
                res = client.get(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(str(hit))}",
                    headers={"Accept": "application/json", "User-Agent": "StudyFlows/1.0"},
                )
            if res.status_code >= 400:
                return None
            data = res.json()
            extract = (data.get("extract") or "").strip()
            label = (data.get("title") or title).strip()
            if not extract:
                return None
            return f"Wikipedia ({label}): {extract[:1200]}"
    except Exception:  # noqa: BLE001
        return None


def _guess_wiki_title(query: str) -> str | None:
    q = (query or "").strip()
    if not q:
        return None
    cleaned = re.sub(
        r"^(what is|what's|whats|define|definition of|meaning of|explain)\s+",
        "",
        q,
        flags=re.I,
    )
    cleaned = cleaned.strip(" ?!.\"'")
    cleaned = re.sub(r"^(a|an|the)\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) < 2 or len(cleaned) > 80:
        return None
    return cleaned
