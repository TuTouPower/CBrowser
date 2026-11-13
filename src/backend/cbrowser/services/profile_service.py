"""Profile service coordinating domain operations, persistence, and diagnostics."""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import logging
import os
import shutil
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

from cbrowser import font_sets
from cbrowser.adapters.database.db_errors import classify_dbapi_error
from cbrowser.adapters.database.repository import (
    ProfileRepository,
)
from cbrowser.domain.egress_observation import (
    OBSERVATION_TTL_SECONDS,
    EgressObservation,
)
from cbrowser.domain.models import (
    ConfigVersionSnapshot,
    Profile,
    ProfileConfig,
    ProfileRuntime,
    RuntimeEvent,
    derive_fingerprint_seed,
    generate_fingerprint_seed,
)
from cbrowser.domain.proxy_endpoint import ProxyEndpoint
from cbrowser.services.egress_probe import EgressProbeRunner
from cbrowser.shared.egress import EgressProbeError
from cbrowser.shared.profile_locks import ProfileLockRegistry
from cbrowser.preview import (
    POLICY_FILE,
    PreviewPolicy,
    clear_preview,
    preview_dir,
    write_policy,
)
from cbrowser.runtime_event_log import emit_runtime_event_log
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


class DatabaseUnavailableError(ProfileServiceError):
    """SQLite I/O error (primary code 10): the database file is unreachable.

    Distinct from a lock: the caller cannot fix this by waiting a second,
    but the operation is still retryable, so the API answers 503 rather
    than 500.
    """

    def __init__(
        self, message: str = "Database temporarily unavailable, retryable operation"
    ):
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


class InvalidFontSetBindingError(ProfileServiceError):
    """A profile's font_set_id does not reference a usable font set."""


class ReferenceValidationError(ProfileServiceError):
    """A write references a group/proxy that does not exist, or a reorder
    does not carry the full set (t056 A28).

    Carries field-level ``details`` in the ValidationErrorDetail shape
    (``loc`` / ``msg`` / ``type``); the API maps it to 422.
    """

    def __init__(self, details: list[dict[str, Any]]):
        message = "; ".join(str(d.get("msg", "")) for d in details)
        super().__init__(message)
        self.details = details


def _validate_font_set_binding(platform: str, font_set_id: str | None) -> None:
    """Reject a non-null binding whose set is missing, cross-platform, or
    fails its integrity check."""
    if font_set_id is None:
        return
    found = font_sets.get_font_set(platform, font_set_id)
    if found is None:
        raise InvalidFontSetBindingError(
            f"font_set_id {font_set_id!r} does not reference an available "
            f"{platform} font set"
        )
    directory, manifest = found
    if manifest.get("platform") != platform:
        raise InvalidFontSetBindingError(
            f"font set {font_set_id!r} platform does not match "
            f"fingerprint_platform {platform!r}"
        )
    if not font_sets.check_font_set(directory)["ok"]:
        raise InvalidFontSetBindingError(
            f"font set {font_set_id!r} failed its integrity check"
        )


_SKIP_COPY_FILES = frozenset({"SingletonLock", "SingletonCookie", "SingletonSocket"})


def _runtime_has_writer(runtime: ProfileRuntime) -> bool:
    """Whether a browser process may still write the user data directory.

    A bound ``runtime_instance_id`` is the durable trace of an actual
    writer: desired/observed can both read ``stopped`` while an instance
    binding survives (Supervisor unreachable, observation lost), and the
    directory must not be rewritten underneath that process (t066 AC-005).
    """
    return (
        runtime.runtime_instance_id is not None
        or runtime.desired_state == "running"
        or runtime.observed_state in ("starting", "running", "stopping")
    )


def _require_fully_stopped(
    runtime: ProfileRuntime, profile_id: str, operation: str
) -> None:
    """Refuse a state-rewriting operation unless the profile is fully
    stopped with no bound runtime instance (t066 AC-005)."""
    if (
        runtime.desired_state != "stopped"
        or runtime.observed_state != "stopped"
        or runtime.runtime_instance_id is not None
    ):
        raise ProfileRunningError(profile_id, operation)


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
        data_root: Path | None = None,
        egress_probe_runner: EgressProbeRunner | None = None,
    ):
        self._repo = repo
        self.runtime_uid = runtime_uid
        self.runtime_gid = runtime_gid
        self._data_root = data_root
        self._locks = ProfileLockRegistry()
        self._egress_probe_runner = egress_probe_runner
        self._probe_tasks: set[asyncio.Task] = set()

    def set_egress_probe_runner(self, runner: EgressProbeRunner | None) -> None:
        """Wire the probe runner after construction (the Supervisor client
        is built after the service in the app lifespan)."""
        self._egress_probe_runner = runner

    async def await_pending_probes(self) -> None:
        """Wait for auto-probe background tasks (tests; production never
        blocks on probes)."""
        tasks = list(self._probe_tasks)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @property
    def locks_idle(self) -> bool:
        """Whether no per-profile lock is registered."""
        return self._locks.is_idle

    def profile_lock(self, profile_id: str) -> AbstractAsyncContextManager[None]:
        """Serialize an external critical section on one profile.

        The public coordination surface for callers (routes) that must
        exclude this service's own per-profile mutations without
        reaching into the registry.
        """
        return self._locks.lock(profile_id)

    def get_preview_dir(self, profile_id: str) -> Path | None:
        if self._data_root is None:
            return None
        return preview_dir(self._data_root, profile_id)

    async def get_preview_policy(
        self, profile_id: str
    ) -> tuple[bool, int] | None:
        return await self._repo.get_preview_policy(profile_id)

    async def clear_preview_capture(self, profile_id: str) -> None:
        await self._repo.clear_preview_capture(profile_id)

    async def record_preview_capture(
        self,
        profile_id: str,
        captured_at: str,
        runtime_instance_id: str,
        policy_epoch: int,
    ) -> bool:
        return await self._repo.record_preview_capture(
            profile_id, captured_at, runtime_instance_id, policy_epoch
        )

    async def _clear_preview_state(self, profile_id: str) -> None:
        directory = self.get_preview_dir(profile_id)
        if directory is not None:
            clear_preview(directory)
            try:
                (directory / POLICY_FILE).unlink(missing_ok=True)
            except OSError as exc:
                logger.warning(
                    "Preview policy cleanup failed: profile=%s error_type=%s",
                    profile_id,
                    type(exc).__name__,
                )
        await self.clear_preview_capture(profile_id)

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

        classification = classify_dbapi_error(exc)
        if classification.kind in ("busy", "locked"):
            raise DatabaseLockError(
                "Database is temporarily locked, please retry"
            ) from None
        if classification.kind == "io_error":
            raise DatabaseUnavailableError(
                "Database is temporarily unavailable, please retry"
            ) from None
        raise exc

    async def _validate_references(
        self, group_id: str | None, proxy_id: str | None
    ) -> None:
        """t056 A28: a non-null group/proxy reference must exist.  Both
        missing fields are reported together, field-level."""
        details: list[dict[str, Any]] = []
        if group_id is not None and await self._repo.get_group(group_id) is None:
            details.append(
                {
                    "loc": ["body", "group_id"],
                    "msg": f"Group {group_id} does not exist",
                    "type": "value_error",
                }
            )
        if proxy_id is not None and await self._repo.get_proxy(proxy_id) is None:
            details.append(
                {
                    "loc": ["body", "proxy_id"],
                    "msg": f"Proxy {proxy_id} does not exist",
                    "type": "value_error",
                }
            )
        if details:
            raise ReferenceValidationError(details)

    async def create_profile(
        self,
        config: ProfileConfig,
        *,
        profile_id: str | None = None,
        operation_id: str | None = None,
        req_payload: dict[str, Any] | None = None,
        font_set_id_supplied: bool = False,
    ) -> Profile:
        # A16: the backend default font set applies only when the caller
        # did not supply font_set_id at all. An explicit null ("no font
        # set") is honored and never silently replaced by the default.
        if config.font_set_id is None and not font_set_id_supplied:
            default = font_sets.default_font_set(config.fingerprint_platform)
            if default is not None:
                config = config.model_copy(update={"font_set_id": default})
        _validate_font_set_binding(config.fingerprint_platform, config.font_set_id)
        await self._validate_references(config.group_id, config.proxy_id)
        try:
            return await self._repo.create_profile(
                config=config,
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

    async def font_set_usage_counts(self) -> dict[tuple[str, str], int]:
        return await self._repo.font_set_usage_counts()

    async def update_profile(
        self,
        profile_id: str,
        patch_data: dict[str, Any] | ProfileConfig,
        *,
        operation_id: str | None = None,
    ) -> Profile:
        patch_dict = (
            patch_data.model_dump()
            if isinstance(patch_data, ProfileConfig)
            else dict(patch_data)
        )
        if "font_set_id" in patch_dict or "fingerprint_platform" in patch_dict:
            current = await self._repo.get_profile(profile_id)
            if current is not None:
                platform = patch_dict.get(
                    "fingerprint_platform", current.config.fingerprint_platform
                )
                font_set_id = patch_dict.get(
                    "font_set_id", current.config.font_set_id
                )
                _validate_font_set_binding(platform, font_set_id)
        # t056 A28: only keys present in the patch are validated; an
        # explicit null clears the reference and needs no lookup.
        if "group_id" in patch_dict or "proxy_id" in patch_dict:
            await self._validate_references(
                patch_dict.get("group_id"), patch_dict.get("proxy_id")
            )
        try:
            profile = await self._repo.update_profile(
                profile_id=profile_id,
                patch_data=patch_data,
                operation_id=operation_id,
            )
            if not profile:
                raise ProfileNotFoundError(profile_id)
            return profile
        except DBAPIError as e:
            self._handle_db_error(e)

    @staticmethod
    def _remove_profile_directory(target: Path, profile_id: str) -> None:
        """Best-effort cleanup that stays observable.

        A failed removal must not silently disappear: AC-011 promises the
        private directories are gone, so a permission/occupancy error is
        logged rather than swallowed by ``ignore_errors=True``.
        """
        try:
            shutil.rmtree(target)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning(
                "Profile directory cleanup failed: profile=%s path=%s "
                "error_type=%s",
                profile_id,
                target,
                type(exc).__name__,
            )

    async def delete_profile(self, profile_id: str) -> bool:
        """Delete a stopped profile and all of its private directories.

        A profile that is desired-running, still observed in a lifecycle
        transition, or bound to a runtime instance is refused (t035 AC-011).
        """
        try:
            async with self._locks.lock(profile_id):
                profile = await self._repo.get_profile(profile_id)
                if profile is None:
                    raise ProfileNotFoundError(profile_id)
                runtime = await self._repo.get_runtime(profile_id)
                if runtime is not None and _runtime_has_writer(runtime):
                    raise ProfileRunningError(profile_id, "delete")
                deleted = await self._repo.delete_profile(profile_id)
                if not deleted:
                    raise ProfileNotFoundError(profile_id)
                if self._data_root is not None:
                    for sub in ("profiles", "runtime", "runtime-events"):
                        target = self._data_root / sub / profile_id
                        await asyncio.to_thread(
                            self._remove_profile_directory, target, profile_id
                        )
                await self._clear_preview_state(profile_id)
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
                policy_row = await self.get_preview_policy(profile_id)
                directory = self.get_preview_dir(profile_id)
                if policy_row is not None and directory is not None:
                    write_policy(
                        directory,
                        PreviewPolicy(
                            enabled=policy_row[0],
                            epoch=policy_row[1],
                            runtime_instance_id=runtime_instance_id,
                        ),
                    )
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
        *,
        browser_product: str | None = None,
        browser_user_agent: str | None = None,
    ) -> ProfileRuntime:
        try:
            await self.get_profile(profile_id)
            rt = await self._repo.report_observed_state(
                profile_id,
                runtime_instance_id,
                observed_state,
                config_version,
                reason,
                browser_product=browser_product,
                browser_user_agent=browser_user_agent,
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
                    _require_fully_stopped(
                        runtime, profile_id, "copying browser state"
                    )

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
                        _require_fully_stopped(
                            runtime, profile_id, "copying browser state"
                        )
                    config = ProfileConfig(
                        **{
                            **source.config.model_dump(),
                            "name": clone_name,
                        }
                    )
                    clone = await self._repo.create_profile(
                        config=config,
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
                _require_fully_stopped(runtime, profile_id, "resetting")

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
                    _require_fully_stopped(runtime, profile_id, "resetting")
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
                await self._clear_preview_state(profile_id)
                return updated
        except DBAPIError as e:
            self._handle_db_error(e)

    @staticmethod
    def _seed_for_operation(operation_id: str) -> int:
        return derive_fingerprint_seed(operation_id)

    # ---- Group / Proxy (t035) -----------------------------------------

    async def list_groups(self):
        return await self._repo.list_groups()

    async def create_group(self, req, *, operation_id: str | None = None):
        return await self._repo.create_group(
            req.name, req.color, req.sort_order, operation_id=operation_id
        )

    async def update_group(
        self, group_id: str, req, *, operation_id: str | None = None
    ):
        patch = req.model_dump(exclude_unset=True)
        return await self._repo.update_group(
            group_id, patch, operation_id=operation_id
        )

    async def delete_group(
        self, group_id: str, *, operation_id: str | None = None
    ) -> bool:
        return await self._repo.delete_group(group_id, operation_id=operation_id)

    async def reorder_groups(self, req):
        # t056 A28: a reorder must carry the full set — same ids, no
        # duplicates, no unknowns — otherwise 422.
        ordered_ids: list[str] = list(req.ordered_ids)
        existing = {g.id for g in await self._repo.list_groups()}
        details: list[dict[str, Any]] = []
        if len(set(ordered_ids)) != len(ordered_ids):
            details.append(
                {
                    "loc": ["body", "ordered_ids"],
                    "msg": "ordered_ids must not contain duplicates",
                    "type": "value_error",
                }
            )
        missing = sorted(set(ordered_ids) - existing)
        if missing:
            details.append(
                {
                    "loc": ["body", "ordered_ids"],
                    "msg": f"Unknown group(s): {', '.join(missing)}",
                    "type": "value_error",
                }
            )
        omitted = sorted(existing - set(ordered_ids))
        if omitted:
            details.append(
                {
                    "loc": ["body", "ordered_ids"],
                    "msg": (
                        "ordered_ids must contain every group; "
                        f"missing: {', '.join(omitted)}"
                    ),
                    "type": "value_error",
                }
            )
        if details:
            raise ReferenceValidationError(details)
        return await self._repo.reorder_groups(ordered_ids)

    async def list_proxies(self):
        return await self._repo.list_proxies()

    async def get_proxy(self, proxy_id: str):
        return await self._repo.get_proxy(proxy_id)

    async def get_proxy_credentials(self, proxy_id: str):
        return await self._repo.get_proxy_credentials(proxy_id)

    async def create_proxy(self, req, *, operation_id: str | None = None):
        """Create from a proxy link (t052): the link is the only entry;
        the name defaults to ``host:port``; a pending observation is
        recorded and an egress probe is scheduled in the background.

        t056 A23: replayable via Idempotency-Key.  A replay returns the
        first proxy and schedules no second probe.
        """
        endpoint = req.parsed_endpoint()
        payload = {
            "name": req.resolved_name(),
            "scheme": endpoint.scheme,
            "host": endpoint.host,
            "port": endpoint.port,
            "username": endpoint.username,
            "password": endpoint.password,
            "region_label": req.region_label,
            "notes": req.notes,
        }
        if operation_id is not None:
            entity_id = await self._repo.find_recorded_operation(
                operation_id, "create_proxy", "", payload
            )
            if entity_id is not None:
                existing = await self._repo.get_proxy(entity_id)
                if existing is not None:
                    return existing
        created = await self._repo.create_proxy(payload, operation_id=operation_id)
        await self._record_pending_observation(created.id, endpoint)
        self._schedule_probe(created.id)
        refreshed = await self._repo.get_proxy(created.id)
        return refreshed if refreshed is not None else created

    async def update_proxy(
        self, proxy_id: str, req, *, operation_id: str | None = None
    ):
        """PATCH from a proxy link (t052): an omitted ``proxy_url`` leaves
        the endpoint (and password) untouched; a supplied one replaces it
        wholesale and re-triggers the egress probe.

        t056 A23: replayable via Idempotency-Key.  A replay returns the
        current proxy with recomputed impact lists and schedules no
        second probe.
        """
        patch: dict[str, Any] = {
            key: value
            for key, value in req.model_dump(exclude_unset=True).items()
            if key != "proxy_url"
        }
        endpoint: ProxyEndpoint | None = None
        password_supplied = False
        if req.endpoint_was_supplied():
            endpoint = req.parsed_endpoint()
            patch.update(
                {
                    "scheme": endpoint.scheme,
                    "host": endpoint.host,
                    "port": endpoint.port,
                    "username": endpoint.username,
                    "password": endpoint.password,
                }
            )
            password_supplied = True
        if operation_id is not None:
            entity_id = await self._repo.find_recorded_operation(
                operation_id,
                "update_proxy",
                proxy_id,
                {"patch": patch, "password_supplied": password_supplied},
            )
            if entity_id is not None:
                existing = await self._repo.get_proxy(proxy_id)
                if existing is not None:
                    versioned, runtime_only = await self._repo.proxy_impact(proxy_id)
                    return existing, versioned, runtime_only
        proxy, versioned, runtime_only = await self._repo.update_proxy(
            proxy_id, patch, password_supplied, operation_id=operation_id
        )
        if proxy is None:
            return None, [], []
        if endpoint is not None:
            await self._record_pending_observation(proxy.id, endpoint)
            self._schedule_probe(proxy.id)
            refreshed = await self._repo.get_proxy(proxy.id)
            if refreshed is not None:
                proxy = refreshed
        return proxy, versioned, runtime_only

    async def probe_proxy_egress(self, proxy_id: str):
        """Manual probe (t052): only the proxy id is accepted — the stored
        endpoint and credentials are loaded server-side, so a caller can
        never redirect the stored password to another host (AC-009)."""
        endpoint_data = await self._repo.get_proxy_endpoint(proxy_id)
        if endpoint_data is None:
            return None
        endpoint = ProxyEndpoint(
            scheme=endpoint_data["scheme"],
            host=endpoint_data["host"],
            port=endpoint_data["port"],
            username=endpoint_data["username"],
            password=endpoint_data["password"],
        )
        fingerprint = endpoint_data["endpoint_fingerprint"]
        revision = endpoint_data["credential_revision"]
        await self._record_pending_observation(proxy_id, endpoint)
        runner = self._egress_probe_runner
        if runner is None:
            await self._record_failed_observation(
                proxy_id,
                fingerprint,
                revision,
                "supervisor_unavailable",
                datetime.datetime.now(datetime.timezone.utc),
            )
        else:
            try:
                result = await runner.probe(proxy_id, endpoint, revision)
            except EgressProbeError as exc:
                await self._record_failed_observation(
                    proxy_id,
                    fingerprint,
                    revision,
                    exc.code,
                    datetime.datetime.now(datetime.timezone.utc),
                )
            except Exception as exc:
                # A runner bug (or any unexpected failure) must never
                # leave the pending observation hanging and must never
                # surface as a 500: record a controlled failed row so
                # the UI shows "unknown" and the probe can be retried.
                logger.warning(
                    "Egress probe failed unexpectedly: proxy=%s "
                    "error_type=%s error=%s",
                    proxy_id,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                await self._record_failed_observation(
                    proxy_id,
                    fingerprint,
                    revision,
                    "probe_failed",
                    datetime.datetime.now(datetime.timezone.utc),
                )
            else:
                # observed_at is the time the probe *completed*: it must
                # sort after the pending row recorded when the probe
                # started, or "latest wins" would resurrect the pending
                # state.
                completed_at = datetime.datetime.now(datetime.timezone.utc)
                await self._repo.record_egress_observation(
                    proxy_id,
                    EgressObservation(
                        proxy_id=proxy_id,
                        endpoint_fingerprint=fingerprint,
                        credential_revision=revision,
                        egress_ip=result.egress_ip,
                        country_code=result.country_code,
                        status="ok",
                        observed_at=completed_at,
                        expires_at=completed_at
                        + datetime.timedelta(seconds=OBSERVATION_TTL_SECONDS),
                    ),
                )
        return await self._repo.get_proxy(proxy_id)

    async def _record_pending_observation(
        self, proxy_id: str, endpoint: ProxyEndpoint
    ) -> None:
        data = await self._repo.get_proxy_endpoint(proxy_id)
        if data is None:
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        await self._repo.record_egress_observation(
            proxy_id,
            EgressObservation(
                proxy_id=proxy_id,
                endpoint_fingerprint=data["endpoint_fingerprint"],
                credential_revision=data["credential_revision"],
                status="pending",
                observed_at=now,
            ),
        )

    async def _record_failed_observation(
        self,
        proxy_id: str,
        fingerprint: str,
        revision: int,
        error_code: str,
        now: datetime.datetime,
    ) -> None:
        await self._repo.record_egress_observation(
            proxy_id,
            EgressObservation(
                proxy_id=proxy_id,
                endpoint_fingerprint=fingerprint,
                credential_revision=revision,
                status="failed",
                error_code=error_code,
                observed_at=now,
            ),
        )

    def _schedule_probe(self, proxy_id: str) -> None:
        """Fire-and-forget auto-probe after save / endpoint change (AC-006).
        The pending observation is already recorded; the task only upgrades
        it to ok/failed.  Failures are recorded, never raised to the API
        caller."""
        task = asyncio.create_task(self._probe_safely(proxy_id))
        self._probe_tasks.add(task)
        task.add_done_callback(self._probe_tasks.discard)

    async def _probe_safely(self, proxy_id: str) -> None:
        try:
            await self.probe_proxy_egress(proxy_id)
        except Exception as exc:  # noqa: BLE001 - probe must never break the API
            logger.warning(
                "Background egress probe failed: proxy=%s error_type=%s error=%s",
                proxy_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )

    async def delete_proxy(
        self, proxy_id: str, *, operation_id: str | None = None
    ):
        return await self._repo.delete_proxy(proxy_id, operation_id=operation_id)
