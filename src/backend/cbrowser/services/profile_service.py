"""Profile service coordinating domain operations, persistence, and diagnostics."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from cbrowser.adapters.database.repository import (
    ProfileRepository,
)
from cbrowser.domain.models import (
    ConfigVersionSnapshot,
    Profile,
    ProfileConfig,
    ProfileRuntime,
    RuntimeEvent,
    Tag,
    generate_fingerprint_seed,
)
from diagnostics import emit_runtime_event_log
from sqlalchemy.exc import DBAPIError, IntegrityError

logger = logging.getLogger("cbrowser.services.profile_service")


class ProfileServiceError(Exception):
    pass


class ProfileNotFoundError(ProfileServiceError):
    def __init__(self, profile_id: str):
        super().__init__(f"Profile {profile_id} not found")
        self.profile_id = profile_id


class DatabaseLockError(ProfileServiceError):
    def __init__(self, message: str = "Database busy or locked, retryable operation"):
        super().__init__(message)


class StaleInstanceError(ProfileServiceError):
    def __init__(self, profile_id: str, instance_id: str):
        super().__init__(
            f"Stale runtime instance {instance_id} for profile {profile_id}"
        )
        self.profile_id = profile_id
        self.instance_id = instance_id


class ConstraintViolationError(ProfileServiceError):
    def __init__(self, message: str = "Database constraint violation occurred"):
        super().__init__(message)


class ProfileOperationConflictError(ProfileServiceError):
    pass


class InvalidProfileNameError(ProfileServiceError):
    pass


class ProfileRunningError(ProfileServiceError):
    def __init__(self, profile_id: str, operation: str):
        super().__init__(f"Stop profile {profile_id} before {operation}")
        self.profile_id = profile_id
        self.operation = operation


class ProfileLockRegistry:
    """Per-profile locks whose entries disappear once no task uses them."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def lock(self, profile_id: str) -> AsyncIterator[None]:
        lock = self._locks.setdefault(profile_id, asyncio.Lock())
        try:
            async with lock:
                yield
        finally:
            if (
                self._locks.get(profile_id) is lock
                and not lock.locked()
                and not getattr(lock, "_waiters", None)
            ):
                self._locks.pop(profile_id, None)


_SKIP_COPY_FILES = frozenset({"SingletonLock", "SingletonCookie", "SingletonSocket"})


def _manifest(root: Path) -> dict[str, tuple[str, int | str]]:
    entries: dict[str, tuple[str, int | str]] = {}
    if not root.is_dir():
        return entries
    for path in sorted(root.rglob("*")):
        if path.name in _SKIP_COPY_FILES:
            continue
        relative = str(path.relative_to(root))
        if path.is_symlink():
            entries[relative] = ("link", os.readlink(path))
        elif path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
            entries[relative] = ("file", f"{digest.hexdigest()}:{path.stat().st_size}")
    return entries


def _apply_copy_ownership(root: Path, uid: int, gid: int) -> None:
    def _own(path: Path, *, directory: bool) -> None:
        if path.is_symlink():
            return
        stat = path.stat()
        if stat.st_uid != uid or stat.st_gid != gid:
            # Host-direct development cannot chown to another uid; it keeps the
            # developer owner but never falls back to world-writable modes.
            if os.geteuid() == 0 or os.geteuid() == uid:
                os.chown(path, uid, gid, follow_symlinks=False)
        os.chmod(path, 0o700 if directory else 0o600)

    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        _own(base, directory=True)
        for name in dirnames:
            _own(base / name, directory=True)
        for name in filenames:
            _own(base / name, directory=False)


def _cleanup_copy(path: Path, profile_id: str) -> None:
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.warning(
            "Copy cleanup failed: profile=%s path=%s error_type=%s",
            profile_id,
            path,
            type(exc).__name__,
        )


def _copy_user_data(
    source: Path, target: Path, *, uid: int = 1000, gid: int = 1000
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if not source.is_dir():
        _apply_copy_ownership(target, uid, gid)
        return
    shutil.copytree(
        source,
        target,
        symlinks=True,
        dirs_exist_ok=True,
        ignore=lambda _directory, names: [
            name for name in names if name in _SKIP_COPY_FILES
        ],
    )
    _apply_copy_ownership(target, uid, gid)


async def _copy_user_data_to_completion(
    source: Path, target: Path, *, uid: int = 1000, gid: int = 1000
) -> None:
    worker = asyncio.ensure_future(
        asyncio.to_thread(_copy_user_data, source, target, uid=uid, gid=gid)
    )
    cancelled: asyncio.CancelledError | None = None
    while not worker.done():
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError as exc:
            cancelled = exc
        except Exception:
            pass
    if cancelled is not None:
        raise cancelled
    worker.result()


class ProfileService:
    def __init__(
        self,
        repo: ProfileRepository,
        *,
        runtime_uid: int = 1000,
        runtime_gid: int = 1000,
    ):
        self._repo = repo
        self.runtime_uid = runtime_uid
        self.runtime_gid = runtime_gid
        self._locks = ProfileLockRegistry()

    async def _replay_if_committed(
        self,
        operation_id: str | None,
        *,
        expected_action: str,
        expected_entity_id: str | None,
        details_match: Callable[[dict[str, Any]], bool],
        conflict_message: str,
    ) -> Profile | None:
        """Return the committed result for a replayed operation, else None."""
        if not operation_id:
            return None
        audit = await self._repo.get_audit_event(operation_id)
        if audit is None:
            return None
        try:
            details = json.loads(audit["details"])
        except (TypeError, ValueError):
            raise ProfileOperationConflictError(conflict_message) from None
        if (
            audit["action"] != expected_action
            or (
                expected_entity_id is not None
                and audit["entity_id"] != expected_entity_id
            )
            or not isinstance(details, dict)
            or not details_match(details)
        ):
            raise ProfileOperationConflictError(conflict_message)
        existing = await self._repo.get_profile(audit["entity_id"])
        if existing is None:
            raise ProfileOperationConflictError(
                "Operation ID references a missing profile"
            )
        return existing

    @staticmethod
    def _clone_dir(source: Profile, clone_id: str) -> Path:
        source_path = Path(source.user_data_dir)
        profiles_root = source_path.parent.parent
        return profiles_root / clone_id / "profile"

    def _handle_db_error(self, exc: DBAPIError) -> None:
        if isinstance(exc, IntegrityError):
            raise ConstraintViolationError(
                "Database constraint violation occurred"
            ) from None

        orig = getattr(exc, "orig", None)
        code = getattr(orig, "sqlite_errorcode", None)
        name = getattr(orig, "sqlite_errorname", "")
        if (code is not None and (code & 0xFF) in (5, 6)) or name in (
            "SQLITE_BUSY",
            "SQLITE_LOCKED",
        ):
            raise DatabaseLockError(
                "Database is temporarily locked, please retry"
            ) from None
        raise exc

    async def create_profile(
        self,
        config: ProfileConfig,
        tags: list[Tag] | None = None,
        *,
        profile_id: str | None = None,
        operation_id: str | None = None,
        req_payload: dict[str, Any] | None = None,
    ) -> Profile:
        try:
            return await self._repo.create_profile(
                config=config,
                tags=tags,
                profile_id=profile_id,
                operation_id=operation_id,
                req_payload=req_payload,
            )
        except DBAPIError as e:
            self._handle_db_error(e)

    async def get_profile(self, profile_id: str) -> Profile:
        try:
            profile = await self._repo.get_profile(profile_id)
            if not profile:
                raise ProfileNotFoundError(profile_id)
            return profile
        except DBAPIError as e:
            self._handle_db_error(e)

    async def list_profiles(self) -> list[Profile]:
        try:
            return await self._repo.list_profiles()
        except DBAPIError as e:
            self._handle_db_error(e)

    async def update_profile(
        self,
        profile_id: str,
        patch_data: dict[str, Any] | ProfileConfig,
        tags: list[Tag] | None = None,
        *,
        operation_id: str | None = None,
    ) -> Profile:
        try:
            profile = await self._repo.update_profile(
                profile_id=profile_id,
                patch_data=patch_data,
                tags=tags,
                operation_id=operation_id,
            )
            if not profile:
                raise ProfileNotFoundError(profile_id)
            return profile
        except DBAPIError as e:
            self._handle_db_error(e)

    async def delete_profile(self, profile_id: str) -> bool:
        try:
            async with self._locks.lock(profile_id):
                deleted = await self._repo.delete_profile(profile_id)
                if not deleted:
                    raise ProfileNotFoundError(profile_id)
                return True
        except DBAPIError as e:
            self._handle_db_error(e)

    async def list_config_versions(
        self, profile_id: str
    ) -> list[ConfigVersionSnapshot]:
        try:
            await self.get_profile(profile_id)
            return await self._repo.list_config_versions(profile_id)
        except DBAPIError as e:
            self._handle_db_error(e)

    async def get_config_version(
        self, profile_id: str, version: int
    ) -> ConfigVersionSnapshot:
        try:
            await self.get_profile(profile_id)
            snapshot = await self._repo.get_config_version(profile_id, version)
            if not snapshot:
                raise ProfileNotFoundError(f"{profile_id}/versions/{version}")
            return snapshot
        except DBAPIError as e:
            self._handle_db_error(e)

    async def get_runtime(self, profile_id: str) -> ProfileRuntime:
        try:
            await self.get_profile(profile_id)
            rt = await self._repo.get_runtime(profile_id)
            if not rt:
                raise ProfileNotFoundError(profile_id)
            return rt
        except DBAPIError as e:
            self._handle_db_error(e)

    async def bind_runtime_instance(
        self,
        profile_id: str,
        runtime_instance_id: str,
        config_version: int = 1,
        expected_current_instance: str | None = None,
    ) -> ProfileRuntime:
        try:
            async with self._locks.lock(profile_id):
                await self.get_profile(profile_id)
                rt = await self._repo.bind_runtime_instance(
                    profile_id,
                    runtime_instance_id,
                    config_version,
                    expected_current_instance,
                )
            if not rt:
                raise ProfileNotFoundError(profile_id)
            return rt
        except DBAPIError as e:
            self._handle_db_error(e)

    async def report_observed_state(
        self,
        profile_id: str,
        runtime_instance_id: str,
        observed_state: str,
        config_version: int | None = None,
        reason: str | None = None,
    ) -> ProfileRuntime:
        try:
            await self.get_profile(profile_id)
            rt = await self._repo.report_observed_state(
                profile_id, runtime_instance_id, observed_state, config_version, reason
            )
            if not rt:
                raise StaleInstanceError(profile_id, runtime_instance_id)
            return rt
        except DBAPIError as e:
            self._handle_db_error(e)

    async def set_desired_state(
        self, profile_id: str, desired_state: str, *, operation_id: str | None = None
    ) -> ProfileRuntime:
        try:
            async with self._locks.lock(profile_id):
                await self.get_profile(profile_id)
                rt = await self._repo.set_desired_state(
                    profile_id, desired_state, operation_id=operation_id
                )
                if not rt:
                    raise ProfileNotFoundError(profile_id)
                return rt
        except DBAPIError as e:
            self._handle_db_error(e)

    async def process_runtime_event(self, event: RuntimeEvent) -> dict[str, Any]:
        """Process runtime event and emit safe structured diagnostics log."""
        try:
            outcome = await self._repo.consume_runtime_event(event)
            emit_runtime_event_log(
                event_id=event.event_id,
                profile_id=event.profile_id,
                runtime_instance_id=event.runtime_instance_id,
                event_type=event.event_type,
                exit_code=event.exit_code,
                exit_reason=event.exit_reason,
                config_version=event.config_version,
                outcome=outcome,
            )
            return {
                "status": "ok",
                "outcome": outcome,
                "event_id": event.event_id,
                "profile_id": event.profile_id,
            }
        except DBAPIError as e:
            self._handle_db_error(e)

    async def duplicate_profile(
        self,
        profile_id: str,
        *,
        include_browser_state: bool = False,
        name: str | None = None,
        operation_id: str | None = None,
    ) -> Profile:
        try:
            async with self._locks.lock(profile_id):
                source = await self.get_profile(profile_id)
                clone_name = self._validated_clone_name(source, name)
                expected_source = (
                    f"duplicate:{profile_id}:"
                    f"{int(include_browser_state)}:"
                    f"{clone_name}"
                )
                replayed = await self._replay_if_committed(
                    operation_id,
                    expected_action="create_profile",
                    expected_entity_id=None,
                    details_match=lambda details: details.get("source")
                    == expected_source,
                    conflict_message="Operation ID was used for a different action",
                )
                if replayed is not None:
                    return replayed
                if include_browser_state:
                    runtime = await self.get_runtime(profile_id)
                    if not (
                        runtime.desired_state == "stopped"
                        and runtime.observed_state == "stopped"
                    ):
                        raise ProfileRunningError(profile_id, "copying browser state")

                clone_id = str(uuid.uuid4())
                clone_dir = self._clone_dir(source, clone_id)
                try:
                    if include_browser_state:
                        await _copy_user_data_to_completion(
                            Path(source.user_data_dir),
                            clone_dir,
                            uid=self.runtime_uid,
                            gid=self.runtime_gid,
                        )
                        source_manifest = await asyncio.to_thread(
                            _manifest, Path(source.user_data_dir)
                        )
                        clone_manifest = await asyncio.to_thread(_manifest, clone_dir)
                        if source_manifest != clone_manifest:
                            raise ProfileServiceError(
                                "Copied browser state does not match the source"
                            )
                        runtime = await self.get_runtime(profile_id)
                        if not (
                            runtime.desired_state == "stopped"
                            and runtime.observed_state == "stopped"
                        ):
                            raise ProfileRunningError(
                                profile_id, "copying browser state"
                            )
                    config = ProfileConfig(
                        **{
                            **source.config.model_dump(),
                            "name": clone_name,
                        }
                    )
                    clone = await self._repo.create_profile(
                        config=config,
                        tags=source.tags,
                        profile_id=clone_id,
                        user_data_dir=str(clone_dir),
                        operation_id=operation_id,
                        req_payload={
                            "source_profile_id": profile_id,
                            "include_browser_state": include_browser_state,
                            "name": clone_name,
                        },
                        audit_source=(
                            f"duplicate:{profile_id}:"
                            f"{int(include_browser_state)}:"
                            f"{clone_name}"
                        ),
                    )
                    if clone.id != clone_id:
                        await asyncio.to_thread(
                            _cleanup_copy, clone_dir.parent, profile_id
                        )
                    return clone
                except BaseException:
                    await asyncio.to_thread(
                        _cleanup_copy, clone_dir.parent, profile_id
                    )
                    raise
        except DBAPIError as e:
            self._handle_db_error(e)

    @staticmethod
    def _validated_clone_name(source: Profile, name: str | None) -> str:
        candidate = (name or f"{source.config.name} (copy)").strip()
        if not candidate:
            raise InvalidProfileNameError("Profile name cannot be blank")
        if len(candidate) > 255:
            candidate = candidate[:255].rstrip()
        if not candidate:
            raise InvalidProfileNameError("Profile name cannot be blank")
        return candidate

    async def reset_profile(
        self,
        profile_id: str,
        *,
        operation_id: str | None = None,
    ) -> Profile:
        try:
            async with self._locks.lock(profile_id):
                source = await self.get_profile(profile_id)
                replayed = await self._replay_if_committed(
                    operation_id,
                    expected_action="reset_profile",
                    expected_entity_id=profile_id,
                    details_match=lambda _details: True,
                    conflict_message="Operation ID was used for a different action",
                )
                if replayed is not None:
                    return replayed
                runtime = await self.get_runtime(profile_id)
                if not (
                    runtime.desired_state == "stopped"
                    and runtime.observed_state == "stopped"
                ):
                    raise ProfileRunningError(profile_id, "resetting")

                source_dir = Path(source.user_data_dir)
                backup = source_dir.with_name(f".reset-backup-{uuid.uuid4().hex}")
                moved = False
                if source_dir.exists():
                    await asyncio.to_thread(os.replace, source_dir, backup)
                    moved = True
                try:
                    await asyncio.to_thread(
                        source_dir.mkdir, parents=True, exist_ok=True
                    )
                    await asyncio.to_thread(
                        _apply_copy_ownership,
                        source_dir,
                        self.runtime_uid,
                        self.runtime_gid,
                    )
                    runtime = await self.get_runtime(profile_id)
                    if not (
                        runtime.desired_state == "stopped"
                        and runtime.observed_state == "stopped"
                    ):
                        raise ProfileRunningError(profile_id, "resetting")
                    seed = (
                        self._seed_for_operation(operation_id)
                        if operation_id
                        else generate_fingerprint_seed()
                    )
                    updated = await self._repo.update_profile(
                        profile_id=profile_id,
                        patch_data={"fingerprint_seed": seed},
                        operation_id=operation_id,
                        audit_action="reset_profile",
                    )
                    if updated is None:
                        raise ProfileNotFoundError(profile_id)
                except BaseException:
                    await asyncio.to_thread(_cleanup_copy, source_dir, profile_id)
                    if moved and backup.exists():
                        await asyncio.to_thread(os.replace, backup, source_dir)
                    raise
                if moved and backup.exists():
                    try:
                        await asyncio.to_thread(shutil.rmtree, backup)
                    except OSError as exc:
                        logger.warning(
                            "Reset backup cleanup failed: profile=%s error_type=%s",
                            profile_id,
                            type(exc).__name__,
                        )
                        raise ProfileServiceError(
                            "Reset completed but backup cleanup failed"
                        ) from None
                return updated
        except DBAPIError as e:
            self._handle_db_error(e)

    @staticmethod
    def _seed_for_operation(operation_id: str) -> int:
        digest = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()
        return 10000 + int(digest, 16) % 90000
