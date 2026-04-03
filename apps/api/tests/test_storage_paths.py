from __future__ import annotations

import pytest

from app.services.storage.local_fs import LocalFilesystemStorage


def test_local_storage_rejects_path_escape(tmp_path):
    storage = LocalFilesystemStorage(str(tmp_path / "uploads"))
    with pytest.raises(ValueError, match="escapes storage root"):
        storage.put_bytes(relative_path="../outside.txt", data=b"x")


def test_local_storage_allows_nested_paths(tmp_path):
    storage = LocalFilesystemStorage(str(tmp_path / "uploads"))
    stored = storage.put_bytes(relative_path="safe/folder/file.txt", data=b"ok")
    assert stored.size_bytes == 2
