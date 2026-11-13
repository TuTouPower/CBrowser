"""Artifact service: quota, atomic upload, download reconciliation."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import uuid
from collections.abc import AsyncIterable
from dataclasses import dataclass
from pathlib import Path

from cbrowser.adapters.database.artifact_repository import ArtifactRepository
from cbrowser.adapters.filesystem.artifact_store import (
    ArtifactInvalidName,
    ArtifactNotFound,
    ArtifactQuotaExceeded,
    ArtifactStore,
    safe_filename,
    sha256_file,
    validate_content_type,
)
from cbrowser.domain.models import Artifact
from cbrowser.shared.profile_locks import ProfileLockRegistry

logger = logging.getLogger("cbrowser.services.artifacts")


@dataclass(frozen=True)
class IngestDownloadResult:
    artifact: Artifact | None
    reason: str

    @property
    def created(self) -> bool:
        return self.reason == "created"


class ArtifactService:
    def __init__(
        self,
        repository: ArtifactRepository,
        store: ArtifactStore,
        *,
        max_artifact_bytes: int = 256 * 1024 * 1024,
        max_artifacts_per_profile: int = 200,
        max_profile_bytes: int = 2 * 1024 * 1024 * 1024,
    ):
        self.repository = repository
        self.store = store
        self.max_artifact_bytes = max_artifact_bytes
        self.max_artifacts_per_profile = max_artifacts_per_profile
        self.max_profile_bytes = max_profile_bytes
        self._locks = ProfileLockRegistry()

    @property
    def locks_idle(self) -> bool:
        """Whether no per-profile artifact lock is registered."""
        return self._locks.is_idle

    async def _check_quota(
        self, profile_id: str, incoming: int, *, check_disk: bool = True
    ) -> int:
        artifacts = await self.repository.list_artifacts(profile_id)
        if len(artifacts) >= self.max_artifacts_per_profile:
            raise ArtifactQuotaExceeded(
                f"profile already holds {len(artifacts)} artifacts"
            )
        used = sum(item.size for item in artifacts if item.state == "ready")
        if incoming and used + incoming > self.max_profile_bytes:
            raise ArtifactQuotaExceeded("profile artifact storage quota exceeded")
        if check_disk:
            self.store.check_space(incoming)
        return used

    async def upload(
        self,
        profile_id: str,
        name: str,
        content_type: str | None,
        chunks: AsyncIterable[bytes],
        *,
        size_hint: int = 0,
    ) -> Artifact:
        async with self._locks.lock(profile_id):
            if not await self.repository.profile_exists(profile_id):
                raise ArtifactNotFound("Profile not found")
            safe_name = safe_filename(name)
            if not safe_name or safe_name in (".", ".."):
                raise ArtifactInvalidName("Invalid filename")
            media_type = validate_content_type(content_type)
            used = await self._check_quota(
                profile_id, min(size_hint, self.max_artifact_bytes)
            )
            artifact_id = str(uuid.uuid4())
            try:
                size, digest, path = await self.store.write_upload(
                    profile_id,
                    artifact_id,
                    safe_name,
                    chunks,
                    max_bytes=self.max_artifact_bytes,
                )
                if used + size > self.max_profile_bytes:
                    raise ArtifactQuotaExceeded(
                        "profile artifact storage quota exceeded"
                    )
                # Re-assert the quota immediately before the write transaction;
                # the per-profile lock keeps this atomic with the insert.
                await self._check_quota(profile_id, size, check_disk=False)
                return await self.repository.create_artifact(
                    profile_id=profile_id,
                    artifact_id=artifact_id,
                    name=safe_name,
                    size=size,
                    kind="upload",
                    state="ready",
                    content_type=media_type,
                    sha256=digest,
                    storage_path=str(path),
                )
            except BaseException:
                await asyncio.to_thread(
                    self.store.discard_upload, profile_id, artifact_id
                )
                raise

    async def list(self, profile_id: str) -> list[Artifact]:
        return await self.repository.list_artifacts(profile_id)

    async def get(self, profile_id: str, artifact_id: str) -> Artifact:
        self.store.validate_artifact_id(artifact_id)
        artifact = await self.repository.get_artifact(profile_id, artifact_id)
        if artifact is None:
            raise ArtifactNotFound("Artifact not found")
        return artifact

    async def content_path(
        self, profile_id: str, artifact_id: str
    ) -> tuple[Artifact, Path]:
        artifact = await self.get(profile_id, artifact_id)
        if artifact.state != "ready" or not artifact.storage_path:
            raise ArtifactNotFound("Artifact is not ready")
        try:
            path = self.store.ensure_inside_profile(
                profile_id, Path(artifact.storage_path)
            )
        except ArtifactInvalidName as exc:
            raise ArtifactNotFound("Artifact path is invalid") from exc
        if not path.is_file():
            raise ArtifactNotFound("Artifact file is missing")
        return artifact, path

    async def delete(self, profile_id: str, artifact_id: str) -> None:
        """Delete an artifact as a resumable two-phase operation.

        The intent is persisted in the database first; only then is the
        file removed and the metadata row dropped. Any failure leaves the
        intent in place so a retry or a post-restart resume can finish
        the job: while the intent is pending, repeating the call is
        idempotent. Once the deletion has completed, a further call
        reports the artifact as not found (the API maps this to 404),
        which is the defined end-state signal for callers.
        """
        self.store.validate_artifact_id(artifact_id)
        async with self._locks.lock(profile_id):
            artifact = await self.repository.mark_delete_requested(
                profile_id, artifact_id
            )
            if artifact is None:
                raise ArtifactNotFound("Artifact not found")
            await self._complete_deletion(artifact)

    async def _complete_deletion(self, artifact: Artifact) -> None:
        await asyncio.to_thread(
            self.store.delete, artifact.profile_id, artifact.storage_path
        )
        await self.repository.delete_artifact(artifact.profile_id, artifact.id)

    async def resume_pending_deletions(self) -> int:
        """Finish deletions whose intent survived a process restart.

        Returns the number completed. A deletion that still fails keeps
        its intent and is reported, never silently dropped. Even listing
        the pending intents is best-effort: a transient storage failure
        at startup must not abort the application — the intents remain
        persisted and the next start retries them.
        """
        try:
            pending = await self.repository.list_pending_deletions()
        except Exception:  # noqa: BLE001 - startup resume is best-effort
            logger.warning(
                "Could not list pending artifact deletions; "
                "they will be retried on the next start",
                exc_info=True,
            )
            return 0
        completed = 0
        for artifact in pending:
            try:
                async with self._locks.lock(artifact.profile_id):
                    fresh = await self.repository.get_artifact(
                        artifact.profile_id, artifact.id
                    )
                    if fresh is None or fresh.delete_requested_at is None:
                        continue
                    await self._complete_deletion(fresh)
                completed += 1
            except Exception as exc:  # noqa: BLE001 - keep intent, continue others
                logger.warning(
                    "Pending artifact deletion not completed: profile=%s "
                    "artifact=%s error_type=%s",
                    artifact.profile_id,
                    artifact.id,
                    type(exc).__name__,
                )
        return completed

    async def remove_profile(self, profile_id: str) -> None:
        async with self._locks.lock(profile_id):
            await self.repository.delete_profile_artifacts(profile_id)
            await asyncio.to_thread(self.store.remove_profile, profile_id)

    def container_path(self, artifact: Artifact) -> str | None:
        if artifact.state != "ready":
            return None
        return self.store.container_path(
            artifact.profile_id, artifact.id, artifact.name, artifact.kind
        )

    async def ingest_download(
        self,
        profile_id: str,
        *,
        runtime_instance_id: str,
        path: str,
        name: str,
        sha256: str | None,
        size: int | None,
        content_type: str | None,
    ) -> IngestDownloadResult:
        """Register a completed download, deduplicating by path and checksum.

        The reporting instance must be trusted for the profile (currently
        bound or present in its runtime history): a late report from a
        terminated-but-legitimate instance is accepted, an unknown or
        forged instance id is rejected before any file is touched.
        """
        async with self._locks.lock(profile_id):
            if not await self.repository.profile_exists(profile_id):
                raise ArtifactNotFound("Profile not found")
            if not await self.repository.is_trusted_instance(
                profile_id, runtime_instance_id
            ):
                logger.warning(
                    "Download ingest rejected: profile=%s reason=unknown_instance",
                    profile_id,
                )
                return IngestDownloadResult(None, "unknown_instance")
            source = self.store.resolve_download_source(profile_id, path)
            if not source.is_file():
                logger.info(
                    "Download ingest skipped: profile=%s reason=missing", profile_id
                )
                return IngestDownloadResult(None, "missing")
            actual_size = source.stat().st_size
            actual_sha = await asyncio.to_thread(sha256_file, source)
            if sha256 and sha256 != actual_sha:
                logger.warning(
                    "Download ingest rejected: profile=%s reason=checksum_mismatch",
                    profile_id,
                )
                return IngestDownloadResult(None, "checksum_mismatch")
            if size is not None and size != actual_size:
                logger.warning(
                    "Download ingest rejected: profile=%s reason=size_mismatch",
                    profile_id,
                )
                return IngestDownloadResult(None, "size_mismatch")
            safe_name = safe_filename(name or source.name, fallback="download")
            raw_type = (
                content_type
                or mimetypes.guess_type(safe_name)[0]
                or "application/octet-stream"
            )
            # Same normalization as uploads: declared types are kept as
            # metadata (executables included); illegal header values reject
            # the ingest instead of being silently re-marked.
            media_type = validate_content_type(raw_type)

            duplicate = await self.repository.find_download_duplicate(
                profile_id,
                sha256=actual_sha,
                storage_path=str(source),
            )
            if duplicate is not None:
                return IngestDownloadResult(duplicate, "duplicate")

            await self._check_quota(profile_id, actual_size)
            artifact_id = str(uuid.uuid4())
            try:
                moved_size, digest, target = await asyncio.to_thread(
                    self.store.import_download,
                    profile_id,
                    artifact_id,
                    source,
                    safe_name,
                )
            except ArtifactNotFound:
                logger.warning(
                    "Download ingest failed: profile=%s reason=source_vanished",
                    profile_id,
                )
                return IngestDownloadResult(None, "source_vanished")
            try:
                # Re-assert quota immediately before the write transaction while
                # the per-profile lock excludes concurrent uploads.
                await self._check_quota(
                    profile_id, moved_size, check_disk=False
                )
                created = await self.repository.create_artifact(
                    profile_id=profile_id,
                    artifact_id=artifact_id,
                    name=safe_name,
                    size=moved_size,
                    kind="download",
                    state="ready",
                    content_type=media_type,
                    sha256=digest,
                    storage_path=str(target),
                )
                return IngestDownloadResult(created, "created")
            except BaseException:
                await asyncio.to_thread(
                    self.store.restore_download, profile_id, target, source
                )
                raise
