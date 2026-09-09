from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

import httpx


class CanvasAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def normalize_canvas_base_url(base_url: str) -> str:
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        raise CanvasAPIError("Canvas base URL is required")
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CanvasAPIError("Canvas base URL must be a valid http(s) URL")
    return f"{parsed.scheme}://{parsed.netloc}"


def normalize_session_cookie(raw: str) -> str:
    """Accept raw cookie value or a full `canvas_session=...` / Cookie header snippet."""
    value = (raw or "").strip()
    if not value:
        raise CanvasAPIError("Canvas session cookie is required")
    # Full Cookie header with multiple pairs
    if "canvas_session=" in value and (";" in value or value.startswith("canvas_session=")):
        parts = [p.strip() for p in value.split(";") if p.strip()]
        for part in parts:
            if part.lower().startswith("canvas_session="):
                value = part.split("=", 1)[1].strip()
                break
    elif value.lower().startswith("canvas_session="):
        value = value.split("=", 1)[1].strip()
    # Strip wrapping quotes
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]
    if not value:
        raise CanvasAPIError("Canvas session cookie is empty")
    return value


class CanvasClient:
    def __init__(
        self,
        *,
        base_url: str,
        access_token: str | None = None,
        session_cookie: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = normalize_canvas_base_url(base_url)
        self.access_token = (access_token or "").strip() or None
        self.session_cookie = normalize_session_cookie(session_cookie) if session_cookie else None
        self.timeout = timeout
        if not self.access_token and not self.session_cookie:
            raise CanvasAPIError("Canvas access token or session cookie is required")

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        if self.session_cookie:
            headers["Cookie"] = f"canvas_session={self.session_cookie}"
        return headers

    def _url(self, path: str) -> str:
        return urljoin(f"{self.base_url}/", path.lstrip("/"))

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                res = client.get(self._url(path), headers=self._headers(), params=params)
        except httpx.HTTPError as exc:
            raise CanvasAPIError(f"Canvas request failed: {exc}") from exc
        if res.status_code >= 400:
            detail = res.text[:300] if res.text else res.reason_phrase
            raise CanvasAPIError(f"Canvas API error ({res.status_code}): {detail}", status_code=res.status_code)
        if not res.content:
            return None
        return res.json()

    def get_paginated(self, path: str, *, params: dict[str, Any] | None = None) -> list[dict]:
        items: list[dict] = []
        next_params = dict(params or {})
        next_params.setdefault("per_page", 100)
        url = self._url(path)
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                while url:
                    res = client.get(url, headers=self._headers(), params=next_params if url == self._url(path) else None)
                    if res.status_code >= 400:
                        detail = res.text[:300] if res.text else res.reason_phrase
                        raise CanvasAPIError(
                            f"Canvas API error ({res.status_code}): {detail}",
                            status_code=res.status_code,
                        )
                    payload = res.json()
                    if isinstance(payload, list):
                        items.extend([x for x in payload if isinstance(x, dict)])
                    link = res.headers.get("Link") or res.headers.get("link") or ""
                    url = _next_link(link)
                    next_params = None
        except httpx.HTTPError as exc:
            raise CanvasAPIError(f"Canvas request failed: {exc}") from exc
        return items

    def get_self(self) -> dict:
        data = self.get_json("/api/v1/users/self")
        if not isinstance(data, dict):
            raise CanvasAPIError("Unexpected Canvas /users/self response")
        return data

    def list_active_courses(self) -> list[dict]:
        return self.get_paginated(
            "/api/v1/courses",
            params={
                "enrollment_state": "active",
                "include[]": ["term", "syllabus_body"],
            },
        )

    def list_assignments(self, course_id: str | int) -> list[dict]:
        return self.get_paginated(
            f"/api/v1/courses/{course_id}/assignments",
            params={"include[]": ["all_dates"]},
        )

    def list_course_files(self, course_id: str | int) -> list[dict]:
        return self.get_paginated(
            f"/api/v1/courses/{course_id}/files",
            params={"sort": "updated_at", "order": "desc"},
        )

    def get_file(self, file_id: str | int) -> dict:
        data = self.get_json(f"/api/v1/files/{file_id}")
        if not isinstance(data, dict):
            raise CanvasAPIError("Unexpected Canvas file response")
        return data

    def list_modules(self, course_id: str | int) -> list[dict]:
        return self.get_paginated(
            f"/api/v1/courses/{course_id}/modules",
            params={"include[]": ["items"]},
        )

    def list_module_items(self, course_id: str | int, module_id: str | int) -> list[dict]:
        """Full item list when include[]=items on modules is truncated."""
        return self.get_paginated(
            f"/api/v1/courses/{course_id}/modules/{module_id}/items",
            params={},
        )

    def get_page(self, course_id: str | int, page_url: str) -> dict:
        data = self.get_json(f"/api/v1/courses/{course_id}/pages/{page_url}")
        if not isinstance(data, dict):
            raise CanvasAPIError("Unexpected Canvas page response")
        return data

    def download_bytes(self, url: str, *, max_bytes: int = 20 * 1024 * 1024) -> bytes:
        if not url:
            raise CanvasAPIError("Missing download URL")
        try:
            with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                with client.stream("GET", url, headers=self._headers()) as res:
                    if res.status_code >= 400:
                        detail = res.read()[:200]
                        raise CanvasAPIError(
                            f"Canvas download error ({res.status_code}): {detail!r}",
                            status_code=res.status_code,
                        )
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in res.iter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise CanvasAPIError("Canvas file exceeds download size limit", status_code=413)
                        chunks.append(chunk)
                    return b"".join(chunks)
        except CanvasAPIError:
            raise
        except httpx.HTTPError as exc:
            raise CanvasAPIError(f"Canvas download failed: {exc}") from exc


def _next_link(link_header: str) -> str | None:
    # RFC 5988: <url>; rel="next"
    for part in link_header.split(","):
        chunk = part.strip()
        if 'rel="next"' not in chunk and "rel=next" not in chunk:
            continue
        if chunk.startswith("<") and ">" in chunk:
            return chunk[1 : chunk.index(">")]
    return None
