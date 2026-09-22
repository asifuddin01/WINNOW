"""Storage backends. Local disk today; S3 arrives with the production compose file."""

from pathlib import Path

from app.config import Settings
from app.storage.base import Storage, TooLargeError, new_key
from app.storage.local import LocalStorage


def create_storage(settings: Settings) -> Storage:
    """The backend this instance is configured for."""
    if settings.storage_backend == "s3":
        raise NotImplementedError(
            "S3 storage arrives with the production deployment; use STORAGE_BACKEND=local."
        )
    return LocalStorage(Path(settings.storage_path))


__all__ = ["LocalStorage", "Storage", "TooLargeError", "create_storage", "new_key"]
