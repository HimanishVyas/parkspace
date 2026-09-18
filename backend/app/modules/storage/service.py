"""File storage abstraction.

V1 ships a local-filesystem backend served under MEDIA_URL. An S3-compatible
backend can be added by implementing `Storage` and selecting it in get_storage().
"""
import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import ValidationFailed

# Magic-byte signatures -> extension. We never trust the client's filename or content type.
_SIGNATURES: list[tuple[bytes, int, str]] = [
    (b"\xff\xd8\xff", 0, "jpg"),
    (b"\x89PNG\r\n\x1a\n", 0, "png"),
    (b"WEBP", 8, "webp"),
]


@dataclass
class StoredFile:
    key: str
    url: str


class Storage(Protocol):
    async def save(self, content: bytes, *, folder: str, extension: str) -> StoredFile: ...

    async def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str, base_url: str):
        self.root = Path(root)
        self.base_url = base_url.rstrip("/")

    async def save(self, content: bytes, *, folder: str, extension: str) -> StoredFile:
        key = f"{folder}/{uuid.uuid4().hex}.{extension}"
        path = self.root / key
        await asyncio.to_thread(self._write, path, content)
        return StoredFile(key=key, url=f"{self.base_url}/{key}")

    @staticmethod
    def _write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    async def delete(self, key: str) -> None:
        path = (self.root / key).resolve()
        if self.root.resolve() in path.parents and path.exists():
            await asyncio.to_thread(path.unlink)


def get_storage() -> Storage:
    return LocalStorage(settings.media_root, settings.media_url)


def detect_image_extension(content: bytes) -> str | None:
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    for signature, offset, ext in _SIGNATURES:
        if ext != "webp" and content[offset : offset + len(signature)] == signature:
            return ext
    return None


async def read_validated_image(file: UploadFile) -> tuple[bytes, str]:
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise ValidationFailed(
            f"File too large (max {settings.max_upload_bytes // (1024 * 1024)} MB)", code="FILE_TOO_LARGE"
        )
    if not content:
        raise ValidationFailed("Empty file", code="INVALID_FILE")
    ext = detect_image_extension(content)
    if ext is None:
        raise ValidationFailed("Only JPEG, PNG or WEBP images are allowed", code="INVALID_FILE_TYPE")
    return content, ext
