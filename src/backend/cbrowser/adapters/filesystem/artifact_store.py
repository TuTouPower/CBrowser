"""Per-profile artifact file storage kept outside browser user data."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import unicodedata
import uuid
from collections.abc import AsyncIterable
from pathlib import Path

_MAX_NAME_BYTES = 255
_WINDOWS_ILLEGAL = re.compile(r'[<>:"/\\|?*]')
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{n}" for n in range(1, 10)),
    *(f"LPT{n}" for n in range(1, 10)),
}
_PROFILE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CHUNK_SIZE = 1024 * 1024
RESERVE_BYTES = 16 * 1024 * 1024

_CONTENT_TYPE_RE = re.compile(
    r"^[a-z0-9][a-z0-9!#$&^_.+\-]*/[a-z0-9][a-z0-9!#$&^_.+\-]*$"
)


class ArtifactError(Exception):
    """Base class for artifact failures that map to HTTP errors."""


class ArtifactNotFound(ArtifactError):
    pass


class ArtifactInvalidName(ArtifactError):
    pass


class ArtifactInvalidContentType(ArtifactError):
    pass


class ArtifactTooLarge(ArtifactError):
    pass


class ArtifactQuotaExceeded(ArtifactError):
    pass


class ArtifactInsufficientStorage(ArtifactError):
    pass


def safe_filename(name: str | None, fallback: str = "file") -> str:
    """Return a single portable path component for a user-supplied filename."""
    cleaned = unicodedata.normalize("NFC", (name or "").strip())
    cleaned = cleaned.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _CONTROL_CHARS.sub("", cleaned)
    cleaned = _WINDOWS_ILLEGAL.sub("_", cleaned).rstrip(". ")
    if cleaned in ("", ".", ".."):
        return fallback
    stem, _, _ = cleaned.partition(".")
    if stem.upper() in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    if len(cleaned.encode("utf-8")) <= _MAX_NAME_BYTES:
        return cleaned
    stem, dot, ext = cleaned.rpartition(".")
    suffix = f"{dot}{ext}" if dot else ""
    while suffix and len(suffix.encode("utf-8")) > _MAX_NAME_BYTES - 1:
        suffix = suffix[:-1]
    room = _MAX_NAME_BYTES - len(suffix.encode("utf-8"))
    while len(stem.encode("utf-8")) > room:
        stem = stem[:-1]
    return f"{stem}{suffix}" or fallback


def validate_content_type(content_type: str | None) -> str:
    """Normalize a declared media type for either exchange entry point.

    File exchange allows arbitrary content, including executables (user
    decision D2=A): a declared type is metadata, never a safety proof, so
    no type is rejected for what the bytes might be. Upload and download
    ingest share this single normalization: parameters are dropped, the
    value is lower-cased, a missing type defaults to
    ``application/octet-stream``, and only values that are illegal as
    header values (empty, control characters, not a ``type/subtype``
    token pair) are rejected.
    """
    normalized = (content_type or "application/octet-stream").split(";", 1)[0]
    normalized = normalized.strip().lower()
    if not _CONTENT_TYPE_RE.fullmatch(normalized):
        raise ArtifactInvalidContentType("Invalid content type")
    return normalized


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _move(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(source, target)
    except OSError:
        shutil.copy2(source, target)
        source.unlink(missing_ok=True)


class ArtifactStore:
    """Files live under ``{root}/{profile}/uploads|downloads`` only."""

    def __init__(
        self,
        root: Path | str,
        *,
        runtime_uid: int = 1000,
        runtime_gid: int = 1000,
    ):
        self.root = Path(root).resolve()
        self.runtime_uid = runtime_uid
        self.runtime_gid = runtime_gid

    def _apply_runtime_permissions(self, path: Path, *, directory: bool) -> None:
        """Make an artifact entry usable only by the Browser runtime user."""
        stat = path.stat()
        if stat.st_uid != self.runtime_uid or stat.st_gid != self.runtime_gid:
            if os.geteuid() == 0 or os.geteuid() == self.runtime_uid:
                try:
                    os.chown(
                        path, self.runtime_uid, self.runtime_gid, follow_symlinks=False
                    )
                except OSError as exc:
                    raise ArtifactError(
                        f"Cannot assign artifact ownership: {type(exc).__name__}"
                    ) from None
        os.chmod(path, 0o750 if directory else 0o640)

    @staticmethod
    def validate_artifact_id(artifact_id: str) -> str:
        if not _ARTIFACT_ID.fullmatch(artifact_id) or ".." in artifact_id:
            raise ArtifactInvalidName("Invalid artifact id")
        return artifact_id

    def profile_dir(self, profile_id: str) -> Path:
        if not _PROFILE_ID.fullmatch(profile_id) or ".." in profile_id:
            raise ArtifactInvalidName("Invalid profile id")
        return self.root / profile_id

    def uploads_dir(self, profile_id: str) -> Path:
        return self.profile_dir(profile_id) / "uploads"

    def downloads_dir(self, profile_id: str) -> Path:
        return self.profile_dir(profile_id) / "downloads"

    def ensure_profile(self, profile_id: str) -> None:
        for directory in (
            self.uploads_dir(profile_id),
            self.downloads_dir(profile_id),
        ):
            directory.mkdir(parents=True, exist_ok=True, mode=0o750)
            self._apply_runtime_permissions(directory, directory=True)

    def free_bytes(self) -> int:
        self.root.mkdir(parents=True, exist_ok=True)
        return shutil.disk_usage(self.root).free

    def check_space(self, incoming: int) -> None:
        if incoming < 0:
            raise ArtifactInvalidName("Invalid artifact size")
        if self.free_bytes() < incoming + RESERVE_BYTES:
            raise ArtifactInsufficientStorage("Insufficient disk space")

    def upload_target(self, profile_id: str, artifact_id: str, name: str) -> Path:
        self.validate_artifact_id(artifact_id)
        return self.uploads_dir(profile_id) / artifact_id / safe_filename(name)

    def download_target(self, profile_id: str, artifact_id: str, name: str) -> Path:
        self.validate_artifact_id(artifact_id)
        return self.downloads_dir(profile_id) / artifact_id / safe_filename(name)

    def container_path(
        self, profile_id: str, artifact_id: str, name: str, kind: str
    ) -> str:
        self.validate_artifact_id(artifact_id)
        safe = safe_filename(name)
        if kind == "download":
            return f"/exchange/downloads/{artifact_id}/{safe}"
        return f"/exchange/uploads/{artifact_id}/{safe}"

    def ensure_inside_profile(self, profile_id: str, path: Path) -> Path:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.profile_dir(profile_id).resolve()):
            raise ArtifactInvalidName("Artifact path escapes the Profile")
        return resolved

    async def write_upload(
        self,
        profile_id: str,
        artifact_id: str,
        name: str,
        chunks: AsyncIterable[bytes],
        *,
        max_bytes: int,
    ) -> tuple[int, str, Path]:
        """Stream to a private temp file, then publish atomically."""
        self.ensure_profile(profile_id)
        target = self.upload_target(profile_id, artifact_id, name)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        self._apply_runtime_permissions(target.parent, directory=True)
        temp = target.parent / f".incoming-{uuid.uuid4().hex}"
        digest = hashlib.sha256()
        total = 0
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise ArtifactTooLarge(f"upload exceeds {max_bytes} bytes")
                    digest.update(chunk)
                    await asyncio.to_thread(handle.write, chunk)
                await asyncio.to_thread(handle.flush)
                await asyncio.to_thread(os.fsync, handle.fileno())
            os.replace(temp, target)
            # Same durability contract as the shared atomic write: the
            # rename is only durable once the directory is synced (t062).
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            self._apply_runtime_permissions(target, directory=False)
            return total, digest.hexdigest(), target
        except BaseException:
            temp.unlink(missing_ok=True)
            raise

    def discard_upload(self, profile_id: str, artifact_id: str) -> None:
        shutil.rmtree(self.uploads_dir(profile_id) / artifact_id, ignore_errors=True)

    def import_download(
        self,
        profile_id: str,
        artifact_id: str,
        source: Path,
        name: str,
    ) -> tuple[int, str, Path]:
        """Move a completed browser download into its canonical artifact directory."""
        safe = self.ensure_inside_profile(profile_id, source)
        if not safe.is_file():
            raise ArtifactNotFound("Downloaded file is missing")
        target = self.download_target(profile_id, artifact_id, name)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        self._apply_runtime_permissions(target.parent, directory=True)
        _move(safe, target)
        self._apply_runtime_permissions(target, directory=False)
        try:
            return target.stat().st_size, sha256_file(target), target
        except BaseException:
            self.restore_download(profile_id, target, safe)
            raise

    def restore_download(self, profile_id: str, target: Path, source: Path) -> None:
        """Move an imported download back when metadata persistence fails."""
        safe_target = self.ensure_inside_profile(profile_id, target)
        safe_source = self.resolve_download_source(profile_id, str(source))
        if safe_target.is_file():
            safe_source.parent.mkdir(parents=True, exist_ok=True)
            _move(safe_target, safe_source)

    def resolve_download_source(self, profile_id: str, raw_path: str) -> Path:
        """Accept a host path or the in-container /exchange/downloads path."""
        prefix = "/exchange/downloads/"
        candidate = (
            Path(raw_path)
            if not raw_path.startswith(prefix)
            else self.downloads_dir(profile_id) / raw_path[len(prefix) :]
        )
        resolved = self.ensure_inside_profile(profile_id, candidate)
        downloads = self.downloads_dir(profile_id).resolve()
        if not resolved.is_relative_to(downloads):
            raise ArtifactInvalidName("Download path is not in the downloads directory")
        return resolved

    def delete(self, profile_id: str, storage_path: str | None) -> None:
        """Remove one managed artifact file.

        A recorded path that escapes the profile directory is an error the
        caller must surface (the deletion intent stays pending), never a
        silent skip and never a recursive directory removal.
        """
        if not storage_path:
            return
        target = self.ensure_inside_profile(profile_id, Path(storage_path))
        target.unlink(missing_ok=True)
        root = self.profile_dir(profile_id).resolve()
        if target.parent not in (
            self.downloads_dir(profile_id).resolve(),
            self.uploads_dir(profile_id).resolve(),
        ) and target.parent.is_relative_to(root):
            try:
                target.parent.rmdir()
            except OSError:
                pass

    def remove_profile(self, profile_id: str) -> None:
        shutil.rmtree(self.profile_dir(profile_id), ignore_errors=True)
