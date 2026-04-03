from __future__ import annotations

from app.services.storage.base import StoredObject, StorageService


class S3StorageService(StorageService):
    """Minimal S3-compatible storage implementation (feature-flagged)."""

    def __init__(self, *, bucket: str, region: str | None = None, endpoint_url: str | None = None) -> None:
        self._bucket = bucket
        try:
            import boto3  # type: ignore
        except ImportError as e:
            raise RuntimeError("boto3 is required for S3 storage backend") from e
        self._client = boto3.client("s3", region_name=region, endpoint_url=endpoint_url)

    def put_bytes(self, *, relative_path: str, data: bytes) -> StoredObject:
        key = relative_path.lstrip("/")
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        return StoredObject(storage_path=f"s3://{self._bucket}/{key}", size_bytes=len(data))

    def delete(self, *, relative_path: str) -> None:
        key = relative_path.lstrip("/")
        self._client.delete_object(Bucket=self._bucket, Key=key)
