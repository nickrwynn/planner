from __future__ import annotations

import re
from pathlib import Path


REVISION_RE = re.compile(r'^revision\s*=\s*"([^"]+)"', re.MULTILINE)
DOWN_RE = re.compile(r'^down_revision\s*=\s*(.+)$', re.MULTILINE)


def _parse_revision(path: Path) -> tuple[str, str | None]:
    content = path.read_text(encoding="utf-8")
    rev_match = REVISION_RE.search(content)
    if not rev_match:
        raise RuntimeError(f"{path.name}: missing revision")
    revision = rev_match.group(1).strip()

    down_match = DOWN_RE.search(content)
    if not down_match:
        raise RuntimeError(f"{path.name}: missing down_revision")
    raw_down = down_match.group(1).strip().rstrip(",")
    if raw_down in {"None", "null"}:
        down_revision = None
    else:
        down_revision = raw_down.strip('"').strip("'")
    return revision, down_revision


def main() -> int:
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    files = sorted(versions_dir.glob("*.py"))
    if not files:
        raise RuntimeError("No migration files found")

    revisions: dict[str, Path] = {}
    down_revisions: set[str] = set()
    root_count = 0
    for path in files:
        revision, down_revision = _parse_revision(path)
        if revision in revisions:
            raise RuntimeError(f"Duplicate revision '{revision}' in {path.name} and {revisions[revision].name}")
        revisions[revision] = path
        if down_revision is None:
            root_count += 1
        else:
            down_revisions.add(down_revision)

    if root_count != 1:
        raise RuntimeError(f"Expected exactly one root migration, found {root_count}")

    missing = sorted([rev for rev in down_revisions if rev not in revisions])
    if missing:
        raise RuntimeError(f"down_revision references missing revisions: {missing}")

    print(f"Migration integrity OK ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
