from __future__ import annotations

import os
from pathlib import Path

from app.services.storage.base import StoredObject, StorageService


class LocalFilesystemStorage(StorageService):
    def __init__(self, root_dir: str) -> None:
        self._root = Path(root_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _full_path(self, relative_path: str) -> Path:
        rel = Path(relative_path.lstrip("/"))
        full = (self._root / rel).resolve()
        try:
            full.relative_to(self._root)
        except ValueError as e:
            raise ValueError("Invalid storage path: path escapes storage root") from e
        return full

    def put_bytes(self, *, relative_path: str, data: bytes) -> StoredObject:
        full = self._full_path(relative_path)
        full.parent.mkdir(parents=True, exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)
        return StoredObject(storage_path=str(full), size_bytes=len(data))

    def delete(self, *, relative_path: str) -> None:
        full = self._full_path(relative_path)
        try:
            os.remove(full)
        except FileNotFoundError:
            return

