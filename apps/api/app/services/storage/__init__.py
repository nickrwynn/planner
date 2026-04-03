from app.services.storage.base import StorageService, StoredObject
from app.services.storage.local_fs import LocalFilesystemStorage
from app.services.storage.s3 import S3StorageService


def get_storage_service(settings) -> StorageService:
    backend = str(getattr(settings, "storage_backend", "local")).lower().strip()
    if backend == "s3":
        bucket = str(getattr(settings, "s3_bucket", "")).strip()
        if not bucket:
            raise RuntimeError("S3 storage backend selected but S3_BUCKET is empty")
        return S3StorageService(
            bucket=bucket,
            region=getattr(settings, "s3_region", None),
            endpoint_url=getattr(settings, "s3_endpoint_url", None),
        )
    return LocalFilesystemStorage(settings.storage_root)

