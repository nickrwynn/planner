from __future__ import annotations

from pathlib import Path
import sys


def _extract_type_block(ts: str, type_name: str) -> str:
    marker = f"export type {type_name} = {{"
    start = ts.find(marker)
    if start < 0:
        raise RuntimeError(f"Type {type_name} missing from apps/web/lib/types.ts")
    end = ts.find("};", start)
    if end < 0:
        raise RuntimeError(f"Type {type_name} block is not closed in apps/web/lib/types.ts")
    return ts[start : end + 2]


def _check_fields(block: str, fields: set[str], label: str) -> None:
    missing = sorted([field for field in fields if f"{field}:" not in block and f"{field}?:" not in block])
    if missing:
        raise RuntimeError(f"{label} is missing fields from API schema: {missing}")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "apps" / "api"))

    from app.schemas.resource import ResourceRead
    from app.schemas.task import TaskRead

    ts_path = repo_root / "apps" / "web" / "lib" / "types.ts"
    ts = ts_path.read_text(encoding="utf-8")

    resource_block = _extract_type_block(ts, "Resource")
    task_block = _extract_type_block(ts, "Task")
    _check_fields(resource_block, set(ResourceRead.model_fields.keys()), "Resource")
    _check_fields(task_block, set(TaskRead.model_fields.keys()), "Task")
    print("Web/API contract check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
