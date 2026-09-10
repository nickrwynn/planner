from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.resource_chunk import ResourceChunk
from app.models.user import User
from app.services import resources as resource_service

# TOC lines like "1.2Random sampling 4", "1.2 Random sampling 4", or — in books
# whose contents pages carry no page numbers — plain "1.1 Systems of Equations".
# The title cannot contain digits, so a trailing number is unambiguously a page.
_TOC_SECTION_RE = re.compile(
    r"(?m)^\s*(\d+\.\d+)\s*([A-Za-z][^0-9\n]{2,120}?)(?:\s+(\d{1,4}))?\s*$"
)
# TOC chapter lines: "Chapter 1Experiments with random outcomes 1"
_TOC_CHAPTER_RE = re.compile(
    r"(?m)^\s*Chapter\s+(\d+)\s*([A-Za-z][^0-9\n]{2,120}?)(?:\s+(\d{1,4}))?\s*$",
    re.IGNORECASE,
)
# Many books number chapters bare in the contents: "1 Matrices and Equations".
# Requiring a capitalised title keeps this off stray numbers in body text.
_TOC_BARE_CHAPTER_RE = re.compile(
    r"(?m)^\s*([1-9]\d?)\s+([A-Z][^0-9\n]{3,120}?)(?:\s+(\d{1,4}))?\s*$"
)
# Body running headers / section starts: "1.2. Random sampling 5"
_BODY_SECTION_RE = re.compile(
    r"(?m)^\s*(\d+\.\d+)\.\s+([A-Za-z][^\n]{2,100}?)\s+\d{1,4}\s*$"
)
# Body chapter openers sometimes appear as a lone chapter title line.
_BODY_CHAPTER_TITLE_RE = re.compile(
    r"(?m)^\s*(\d+)\s*\n\s*([A-Z][^\n]{8,100})\s*$"
)

_BAD_TITLE_START = re.compile(
    r"^(exercise|example|fact|figure|theorem|lemma|corollary|appendix|answers?\b|index\b|bibliography\b)",
    re.IGNORECASE,
)
_BAD_TITLE_WORDS = re.compile(
    r"\b(illustrates|shows|asks|assuming|exercise|example|inequality|identity|below|above|verify|deduced)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ResourceSection:
    key: str
    title: str
    kind: str  # section | chapter
    page_start: int | None
    page_end: int | None
    chunk_index_start: int


def _clean_title(raw: str) -> str:
    t = re.sub(r"\s+", " ", raw).strip(" .-–—:\t")
    # Strip trailing page numbers accidentally left in title
    t = re.sub(r"\s+\d{1,4}$", "", t).strip()
    # Drop end markers like ± ♣
    t = t.replace("±", "").replace("♣", "").strip()
    return t[:120]


def _section_sort_key(key: str) -> tuple:
    if key.startswith("ch") and key[2:].isdigit():
        return (int(key[2:]), -1)
    if "." in key:
        a, b = key.split(".", 1)
        if a.isdigit() and b.isdigit():
            return (int(a), int(b))
    return (9999, 9999)


def _is_plausible_title(title: str) -> bool:
    t = title.strip()
    if len(t) < 4:
        return False
    if _BAD_TITLE_START.search(t):
        return False
    if _BAD_TITLE_WORDS.search(t):
        return False
    # Prefer titles that look like headings (start with a letter, not a lowercase verb-heavy clause)
    if t[0].islower():
        return False
    # Reject answer-key style math leftovers, e.g. "F(x)=⎧" or "MY(t)=ebtMX(at)".
    if "=" in t:
        return False
    return True


def _parse_toc_entries(text: str) -> list[tuple[str, str, str, int | None]]:
    """
    Return list of (kind, key, title, printed_page).

    The printed page is None for contents pages that list no page numbers; those
    entries are still worth keeping, since the body scan can locate them.
    """
    out: list[tuple[str, str, str, int | None]] = []
    seen_chapters: set[str] = set()

    def add_chapter(number: str, raw_title: str, printed: str | None) -> None:
        title = _clean_title(raw_title)
        if not _is_plausible_title(title) or number in seen_chapters:
            return
        seen_chapters.add(number)
        out.append(("chapter", f"ch{number}", title, int(printed) if printed else None))

    for m in _TOC_CHAPTER_RE.finditer(text):
        add_chapter(m.group(1), m.group(2), m.group(3))
    for m in _TOC_BARE_CHAPTER_RE.finditer(text):
        add_chapter(m.group(1), m.group(2), m.group(3))

    for m in _TOC_SECTION_RE.finditer(text):
        title = _clean_title(m.group(2))
        if title.lower().startswith("exercise"):
            continue
        if not _is_plausible_title(title):
            continue
        out.append(("section", m.group(1), title, int(m.group(3)) if m.group(3) else None))
    return out


def _scan_body_for_heading(
    rows: list[ResourceChunk],
    *,
    pattern: re.Pattern[str],
    title: str,
    skip_chunks: frozenset[int],
) -> tuple[int | None, int]:
    title_token = title.split()[0] if title.split() else ""
    for ch in rows:
        text = ch.text or ""
        # Skip contents pages — they are not body starts. Only the first page of a
        # multi-page contents says "Contents", so the identified pages are passed
        # in; otherwise every entry listed overleaf resolves to the contents page.
        if ch.chunk_index in skip_chunks:
            continue
        if re.search(r"(?i)^\s*contents\b", text) or "Contents" in text[:40]:
            continue
        m = pattern.search(text)
        if not m:
            continue
        found_title = _clean_title(m.group(1))
        if title_token and title_token.lower() not in found_title.lower() and found_title.lower()[:4] != title.lower()[:4]:
            # Allow soft mismatch but prefer token overlap
            title_words = {w.lower() for w in title.split() if len(w) > 3}
            found_words = {w.lower() for w in found_title.split() if len(w) > 3}
            if title_words and found_words and not (title_words & found_words):
                continue
        return ch.page_number, ch.chunk_index
    return None, 10**9


def _find_body_pdf_page(
    rows: list[ResourceChunk],
    *,
    key: str,
    title: str,
    skip_chunks: frozenset[int] = frozenset(),
) -> tuple[int | None, int]:
    """Locate first body heading for this section; return (pdf_page, chunk_index)."""
    # Books differ on whether the section number is followed by a period. Try the
    # dotted form first so books that use it keep the anchors they already had,
    # and require a capitalised title in the bare form to avoid matching the
    # decimals and cross-references that litter mathematical prose.
    for pattern in (
        re.compile(rf"(?m)^\s*{re.escape(key)}\.\s+([A-Za-z][^\n]{{2,100}})"),
        re.compile(rf"(?m)^\s*{re.escape(key)}\s+([A-Z][^\n]{{2,100}})"),
    ):
        page, chunk_index = _scan_body_for_heading(
            rows, pattern=pattern, title=title, skip_chunks=skip_chunks
        )
        if page is not None:
            return page, chunk_index
    return None, 10**9


def list_resource_sections(
    db: Session,
    *,
    user: User,
    resource_id: UUID,
    scan_limit: int = 4000,
) -> list[ResourceSection]:
    """
    Discover chapter/section headings primarily from the Contents TOC, then map
    each entry to the PDF page where the body section begins.
    """
    resource = resource_service.get_resource_for_user(db, user=user, resource_id=resource_id)
    if not resource:
        raise ValueError("Resource not found")

    rows = list(
        db.execute(
            select(ResourceChunk)
            .where(
                ResourceChunk.resource_id == resource_id,
                ResourceChunk.user_id == user.id,
            )
            .order_by(ResourceChunk.chunk_index.asc())
            .limit(scan_limit)
        )
        .scalars()
        .all()
    )
    if not rows:
        return []

    # 1) Parse TOC from early "Contents" pages
    toc_by_key: dict[str, tuple[str, str, int | None]] = {}
    toc_chunk_index = 0
    toc_chunks: set[int] = set()
    for ch in rows:
        text = ch.text or ""
        entries = _parse_toc_entries(text)
        # Only harvest from the contents itself, since body pages mimic TOC lines
        # in two ways. Running headers read "<page number> <chapter title>", and
        # the answer key at the back numbers its answers "3.49", "4.19".
        #
        # A contents page lists many entries at once; a body page offers at most
        # its own heading and a running header. That density is what separates
        # them, because later pages of a multi-page contents carry neither the
        # word "Contents" nor, in some books, any page numbers.
        if len(entries) < 3:
            continue
        looks_like_contents = "Contents" in text or "CONTENTS" in text
        if not looks_like_contents and (ch.page_number or 0) > 40:
            continue
        toc_chunks.add(ch.chunk_index)
        toc_chunk_index = min(toc_chunk_index or ch.chunk_index, ch.chunk_index)
        for kind, key, title, printed in entries:
            # First TOC hit wins (front matter TOC before later repeats)
            if key not in toc_by_key:
                toc_by_key[key] = (kind, title, printed)

    if not toc_by_key:
        # Fallback: body headings only (strict), never exercise/cross-ref noise.
        body_hits: dict[str, tuple[str, str, int | None, int]] = {}
        for ch in rows:
            text = ch.text or ""
            if "Contents" in text[:60]:
                continue
            for m in _BODY_SECTION_RE.finditer(text):
                key = m.group(1)
                title = _clean_title(m.group(2))
                if not _is_plausible_title(title):
                    continue
                if key not in body_hits:
                    body_hits[key] = ("section", title, ch.page_number, ch.chunk_index)
        ordered = sorted(body_hits.items(), key=lambda kv: _section_sort_key(kv[0]))
        return _with_page_ends(
            [
                ResourceSection(
                    key=key,
                    title=title,
                    kind=kind,
                    page_start=page_start,
                    page_end=None,
                    chunk_index_start=chunk_start,
                )
                for key, (kind, title, page_start, chunk_start) in ordered
            ]
        )

    # 2) Map TOC printed pages → PDF pages via body heading search + linear offset
    anchors: list[tuple[int, int]] = []  # (printed, pdf)
    resolved: dict[str, tuple[str, str, int | None, int]] = {}
    for key, (kind, title, printed) in toc_by_key.items():
        pdf_page, chunk_idx = _find_body_pdf_page(
            rows, key=key, title=title, skip_chunks=frozenset(toc_chunks)
        )
        if pdf_page is not None:
            # Only entries that printed a page can anchor the printed→PDF offset.
            if printed is not None:
                anchors.append((printed, pdf_page))
            resolved[key] = (kind, title, pdf_page, chunk_idx)
        else:
            resolved[key] = (kind, title, None, 10**9)

    offset = None
    if anchors:
        # Median (pdf - printed)
        diffs = sorted(pdf - printed for printed, pdf in anchors)
        offset = diffs[len(diffs) // 2]

    for key, (kind, title, pdf_page, chunk_idx) in list(resolved.items()):
        if pdf_page is not None:
            continue
        printed = toc_by_key[key][2]
        # Contents pages without page numbers leave nothing to offset from, so
        # such entries keep whatever the body scan found, or no page at all.
        if offset is not None and printed is not None:
            resolved[key] = (kind, title, max(1, printed + offset), chunk_idx)

    # A chapter opener rarely repeats its own number as a body heading, so fall
    # back to where its first section begins.
    for key, (kind, title, pdf_page, chunk_idx) in list(resolved.items()):
        if kind != "chapter" or pdf_page is not None:
            continue
        number = key[2:]
        starts = [
            (found[2], found[3])
            for other, found in resolved.items()
            if found[0] == "section" and other.startswith(f"{number}.") and found[2] is not None
        ]
        if starts:
            first_page, first_chunk = min(starts)
            resolved[key] = (kind, title, first_page, min(first_chunk, chunk_idx))

    ordered_keys = sorted(resolved.keys(), key=_section_sort_key)
    sections = [
        ResourceSection(
            key=key,
            title=resolved[key][1],
            kind=resolved[key][0],
            page_start=resolved[key][2],
            page_end=None,
            chunk_index_start=resolved[key][3] if resolved[key][3] < 10**9 else toc_chunk_index,
        )
        for key in ordered_keys
    ]
    return _with_page_ends(sections)


def _with_page_ends(sections: list[ResourceSection]) -> list[ResourceSection]:
    out: list[ResourceSection] = []
    for i, sec in enumerate(sections):
        page_end = sec.page_end
        if page_end is None and sec.page_start is not None and i + 1 < len(sections):
            nxt = sections[i + 1].page_start
            if nxt is not None and nxt >= sec.page_start:
                page_end = max(sec.page_start, nxt - 1)
            else:
                page_end = sec.page_start
        elif page_end is None:
            page_end = sec.page_start
        out.append(
            ResourceSection(
                key=sec.key,
                title=sec.title,
                kind=sec.kind,
                page_start=sec.page_start,
                page_end=page_end,
                chunk_index_start=sec.chunk_index_start,
            )
        )
    return out
