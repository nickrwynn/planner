from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class StoredObject:
    storage_path: str
    size_bytes: int


class StorageService(ABC):
    @abstractmethod
    def put_bytes(self, *, relative_path: str, data: bytes) -> StoredObject: ...

    @abstractmethod
    def delete(self, *, relative_path: str) -> None: ...

