"""Firebase Storage adapter for organization evidence uploads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .config import Settings

try:  # pragma: no cover - optional dependency in local dev
    from google.api_core.exceptions import NotFound
    from google.cloud import storage
    from google.oauth2 import service_account
except Exception:  # pragma: no cover - optional dependency in local dev
    NotFound = None
    storage = None
    service_account = None


class EvidenceStorageError(RuntimeError):
    """Base storage adapter error."""


class EvidenceStorageUnavailable(EvidenceStorageError):
    """Raised when Firebase storage is not configured or dependency is missing."""


class EvidenceObjectNotFound(EvidenceStorageError):
    """Raised when the uploaded object does not exist in storage."""


@dataclass(frozen=True)
class UploadSession:
    """Signed upload session metadata."""

    upload_url: str
    upload_method: str
    upload_headers: dict[str, str]
    expires_at: datetime
    storage_uri: str
    object_path: str


@dataclass(frozen=True)
class StoredObjectInfo:
    """Minimal object metadata loaded from storage."""

    size_bytes: int
    content_type: str


class FirebaseEvidenceStorageAdapter:
    """Create signed upload URLs and validate uploaded Firebase objects."""

    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings
        self._bucket_name = settings.firebase_storage_bucket.strip()
        self._client = None
        self._bucket = None
        self._init_error: str | None = None
        self._initialize()

    @property
    def available(self) -> bool:
        return self._bucket is not None

    def create_upload_session(self, *, object_path: str, content_type: str) -> UploadSession:
        blob = self._blob(object_path)
        now = datetime.now(tz=timezone.utc)
        expires_at = now + timedelta(seconds=max(self._settings.evidence_upload_url_ttl_seconds, 60))
        upload_url = blob.generate_signed_url(
            version="v4",
            expiration=expires_at,
            method="PUT",
            content_type=content_type,
        )
        return UploadSession(
            upload_url=upload_url,
            upload_method="PUT",
            upload_headers={"Content-Type": content_type},
            expires_at=expires_at,
            storage_uri=f"gs://{self._bucket_name}/{object_path}",
            object_path=object_path,
        )

    def get_object_info(self, *, object_path: str) -> StoredObjectInfo:
        blob = self._blob(object_path)
        try:
            blob.reload()
        except Exception as exc:  # pragma: no cover - network/provider exceptions
            if NotFound is not None and isinstance(exc, NotFound):
                raise EvidenceObjectNotFound(f"Uploaded object missing: {object_path}") from exc
            message = str(exc).strip() or "Failed to load object metadata."
            raise EvidenceStorageError(message) from exc

        size_bytes = int(getattr(blob, "size", 0) or 0)
        content_type = str(getattr(blob, "content_type", "") or "")
        if size_bytes <= 0:
            raise EvidenceObjectNotFound(f"Uploaded object has invalid size: {object_path}")
        return StoredObjectInfo(size_bytes=size_bytes, content_type=content_type)

    def compute_sha256(self, *, object_path: str) -> str:
        blob = self._blob(object_path)
        try:
            payload = blob.download_as_bytes()
        except Exception as exc:  # pragma: no cover - network/provider exceptions
            if NotFound is not None and isinstance(exc, NotFound):
                raise EvidenceObjectNotFound(f"Uploaded object missing: {object_path}") from exc
            message = str(exc).strip() or "Failed to read uploaded object."
            raise EvidenceStorageError(message) from exc

        digest = hashlib.sha256(payload).hexdigest()
        return digest

    def _initialize(self) -> None:
        if storage is None:
            self._init_error = "google-cloud-storage dependency is not installed."
            return

        if not self._bucket_name:
            self._init_error = "REPORT_GENERATION_FIREBASE_STORAGE_BUCKET is not configured."
            return

        credentials = None
        raw_credentials = self._settings.firebase_credentials_json.strip()
        try:
            if raw_credentials:
                if raw_credentials.startswith("{"):
                    if service_account is None:
                        raise EvidenceStorageUnavailable("google-auth dependency is missing for JSON credentials.")
                    credentials_info = json.loads(raw_credentials)
                    credentials = service_account.Credentials.from_service_account_info(credentials_info)
                else:
                    if service_account is None:
                        raise EvidenceStorageUnavailable("google-auth dependency is missing for credentials file.")
                    credentials_path = Path(raw_credentials).expanduser()
                    credentials = service_account.Credentials.from_service_account_file(str(credentials_path))

            self._client = storage.Client(
                project=self._settings.firebase_project_id or None,
                credentials=credentials,
            )
            self._bucket = self._client.bucket(self._bucket_name)
        except EvidenceStorageUnavailable as exc:
            self._init_error = str(exc)
        except Exception as exc:  # pragma: no cover - provider misconfiguration
            self._init_error = str(exc).strip() or "Unable to initialize Firebase storage adapter."

    def _blob(self, object_path: str) -> Any:
        if self._bucket is None:
            message = self._init_error or "Firebase storage adapter is unavailable."
            raise EvidenceStorageUnavailable(message)
        return self._bucket.blob(object_path)
