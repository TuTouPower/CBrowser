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
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

from cbrowser.adapters.database.db_errors import classify_dbapi_error
from cbrowser.adapters.database.font_repository import FontSetRepository
from cbrowser.adapters.database.repository import (
    ProfileRepository,
)
from cbrowser.domain.egress_observation import (
    OBSERVATION_TTL_SECONDS,
    EgressObservation,
)
from cbrowser.domain.models import (
    CandidateEntry,
    CollectionPage,
    ConfigVersionSnapshot,
    Profile,
    ProfileConfig,
    ProfileDeletionOperation,
    ProfileResponse,
    ProfileRuntime,
    ProxyCandidateEntry,
    ProxyCountryRange,
    ProxyProbeJob,
    ProxyProbeJobAccepted,
    ProxyProbeJobMember,
    ProxyResponse,
    ProxyUsedByEntry,
    RuntimeEvent,
    UserSettingsResponse,
    UserSettingsUpdateRequest,
    derive_fingerprint_seed,
    generate_fingerprint_seed,
)
from cbrowser.domain.proxy_endpoint import ProxyEndpoint
from cbrowser.services.egress_probe import EgressProbeRunner
from cbrowser.services.font_set_catalog import FontSetCatalogService
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

#: 服务端并发上限（t095 AC-003）：一次作业内最多同时探测的成员数。
#: 超限成员在 asyncio.Semaphore 上排队，不丢弃、不拒绝。
DEFAULT_PROBE_JOB_CONCURRENCY = 8


def _probe_job_concurrency() -> int:
    """从环境读取并发上限；非法/小于 1 的配置拒绝并回退默认值。"""
    raw = os.environ.get("CBROWSER_PROBE_JOB_CONCURRENCY")
    if raw is None:
        return DEFAULT_PROBE_JOB_CONCURRENCY
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "Invalid CBROWSER_PROBE_JOB_CONCURRENCY=%r; using %s",
            raw, DEFAULT_PROBE_JOB_CONCURRENCY,
        )
        return DEFAULT_PROBE_JOB_CONCURRENCY
    if value < 1:
        logger.warning(
            "CBROWSER_PROBE_JOB_CONCURRENCY must be >= 1; using %s",
            DEFAULT_PROBE_JOB_CONCURRENCY,
        )
        return DEFAULT_PROBE_JOB_CONCURRENCY
    return value


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


class ProfileDeletionFailedError(ProfileServiceError):
    """A deletion intent reached ``failed``; carries the final
    operation so the API can report the exact stage (t078)."""

    def __init__(self, operation: ProfileDeletionOperation):
        super().__init__(
            f"Deletion of profile {operation.profile_id} failed at "
            f"stage {operation.failed_stage}: {operation.error}"
        )
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
        probe_concurrency: int | None = None,
    ):
        self._repo = repo
        self.runtime_uid = runtime_uid
        self.runtime_gid = runtime_gid
        self._data_root = data_root
        self._locks = ProfileLockRegistry()
        self._egress_probe_runner = egress_probe_runner
        self._probe_tasks: set[asyncio.Task] = set()
        # t094: server-owned probe jobs. `_probe_jobs` holds live driver
        # tasks keyed by job id so a single job is driven exactly once.
        self._probe_job_tasks: dict[str, asyncio.Task] = {}
        # Optional callback (job_id, state) used to publish SSE progress;
        # wired by the app once the coordinator exists.
        self._probe_job_progress: Callable[[str], Awaitable[None]] | None = None
        # t095 AC-003: 全局并发配额。所有作业的所有成员共享同一信号量，
        # 超限成员排队等待配额；每位成员超时独立，互不阻塞。
        self._probe_concurrency = (
            _probe_job_concurrency() if probe_concurrency is None
            else max(1, probe_concurrency)
        )
        self._probe_semaphore = asyncio.Semaphore(self._probe_concurrency)
        # Long-operation timeout budget is centralized in the runner's
        # ``timeout`` (wired into the HTTP client in shared.egress), not
        # re-declared here.
        # t078 deletion lifecycle: background drivers per operation id,
        # an optional artifact cleaner wired by the app, and a per-op
        # lock so the async driver and the synchronous DELETE path can
        # never run the same intent twice.
        self._deletion_tasks: dict[str, asyncio.Task[None]] = {}
        self._deletion_locks: dict[str, asyncio.Lock] = {}
        self._artifact_cleaner: Callable[[str], Awaitable[None]] | None = None
        self.deletion_stop_timeout_seconds = 120.0
        self.deletion_poll_interval_seconds = 0.5
        self._font_catalog: FontSetCatalogService | None = None

    def set_font_catalog(self, catalog: FontSetCatalogService | None) -> None:
        """Wire the font catalog after construction (app lifespan)."""
        self._font_catalog = catalog

    def font_catalog(self) -> FontSetCatalogService:
        """The shared font asset catalog bound to this service's DB."""
        if self._font_catalog is None:
            self._font_catalog = FontSetCatalogService(
                FontSetRepository(self._repo._session_maker)
            )
        return self._font_catalog

    async def _validate_font_set_binding(
        self, platform: str, font_set_id: str | None
    ) -> None:
        """t081: reject a binding the catalog does not record as a
        verified published set for the platform.  Reads catalog metadata
        only — font bytes are verified by import/adoption/audit, never
        on the binding path.

        t075: a missing binding is itself invalid — every profile must
        be bound to a verified platform set."""
        if font_set_id is None:
            raise InvalidFontSetBindingError(
                f"profile is not bound to a {platform} font set"
            )
        record = await self.font_catalog().get_asset(platform, font_set_id)
        if record is None:
            raise InvalidFontSetBindingError(
                f"font_set_id {font_set_id!r} does not reference an available "
                f"{platform} font set"
            )
        if not record.verified:
            raise InvalidFontSetBindingError(
                f"font set {font_set_id!r} failed its integrity check"
            )

    async def get_settings(self) -> UserSettingsResponse:
        return await self._repo.get_settings()

    async def update_settings(
        self, payload: UserSettingsUpdateRequest
    ) -> UserSettingsResponse:
        return await self._repo.update_settings(payload)

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
    ) -> Profile:
        # t075: the font binding is backend-managed, never user-chosen.
        # A config that already carries a binding (clone/duplicate keeps
        # the source identity) is validated as-is; otherwise the
        # platform's catalog default is bound.  When a font root is
        # configured (every real deployment) a platform with no verified
        # set fails creation outright — a profile never starts life
        # unbound on Linux base fonts (AC-005).  A process with no font
        # root configured has the font subsystem out of scope (test
        # harnesses run that way deliberately): creation proceeds
        # unbound, and the Supervisor/Runner fail-closed checks still
        # refuse to start such a profile.
        if config.font_set_id is None:
            if self.font_catalog().root_configured():
                default = await self.font_catalog().default_set_id(
                    config.fingerprint_platform
                )
                if default is None:
                    raise InvalidFontSetBindingError(
                        f"no available {config.fingerprint_platform} font set; "
                        "import and verify a font set for the platform first"
                    )
                config = config.model_copy(update={"font_set_id": default})
        if config.font_set_id is not None:
            await self._validate_font_set_binding(
                config.fingerprint_platform, config.font_set_id
            )
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

    async def list_profiles_page(
        self,
        *,
        search: str | None = None,
        group_id: str | None = None,
        proxy_id: str | None = None,
        status: str | None = None,
        platform: str | None = None,
        sort: str = "default",
        page: int = 1,
        page_size: int = 50,
    ) -> CollectionPage[ProfileResponse]:
        """t076 AC-001: bounded server-side profile page."""
        try:
            result = await self._repo.list_profiles_page(
                search=search,
                group_id=group_id,
                proxy_id=proxy_id,
                status=status,
                platform=platform,
                sort=sort,
                page=page,
                page_size=page_size,
            )
        except DBAPIError as e:
            self._handle_db_error(e)
        return CollectionPage(
            items=[ProfileResponse.from_domain(p) for p in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    async def list_profile_candidates(
        self, search: str = "", limit: int = 20
    ) -> list[CandidateEntry]:
        return await self._repo.list_profile_candidates(search, limit)

    async def list_runtimes(self) -> list[ProfileRuntime]:
        """t076 AC-002: every runtime row in one batched read."""
        try:
            return await self._repo.list_runtimes()
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
        if "fingerprint_platform" in patch_dict or "font_set_id" in patch_dict:
            current = await self._repo.get_profile(profile_id)
            if current is not None:
                platform = patch_dict.get(
                    "fingerprint_platform", current.config.fingerprint_platform
                )
                if platform != current.config.fingerprint_platform:
                    # t075: switching platform rebinds the profile to
                    # the new platform's catalog default set.  With a
                    # font root configured, the switch fails before
                    # anything is written when the target platform has
                    # no verified set, so a profile can never land on a
                    # platform whose fonts it cannot use.  With no font
                    # root configured (font subsystem out of scope for
                    # the process), the stale cross-platform binding is
                    # dropped instead.
                    if self.font_catalog().root_configured():
                        default = await self.font_catalog().default_set_id(
                            platform
                        )
                        if default is None:
                            raise InvalidFontSetBindingError(
                                f"no available {platform} font set; import and "
                                "verify a font set for the platform first"
                            )
                    else:
                        default = None
                    patch_dict["font_set_id"] = default
                    if isinstance(patch_data, ProfileConfig):
                        patch_data = patch_data.model_copy(
                            update={"font_set_id": default}
                        )
                    if default is not None:
                        await self._validate_font_set_binding(platform, default)
                elif patch_dict.get(
                    "font_set_id", current.config.font_set_id
                ) != current.config.font_set_id:
                    await self._validate_font_set_binding(
                        platform, patch_dict.get("font_set_id")
                    )
        # t056 A28: only keys present in the patch are validated; an
        # explicit null clears the reference and needs no lookup.
        if "group_id" in patch_dict or "proxy_id" in patch_dict:
            await self._validate_references(
                patch_dict.get("group_id"), patch_dict.get("proxy_id")
            )
        if not isinstance(patch_data, ProfileConfig):
            # The font-binding branch above may have rewritten
            # patch_dict (platform-switch rebind); a dict patch must
            # reach the repository in that enriched form, not as the
            # caller's original dict.
            patch_data = patch_dict
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

    # --- Profile deletion lifecycle (t078) ---
    #
    # Deletion is one durable state machine, not a refuse-if-running
    # check: an intent row is persisted first, then the machine walks
    # stopping (desired=stopped until no writer remains) and cleaning
    # (artifacts -> directories -> preview -> database row), recording
    # every step outcome. A failure lands in ``failed`` with its stage
    # and leaves the profile data untouched unless the failing step is
    # the database row itself; a retry resumes the same intent. The
    # instance bound when the stop stage began fences cleaning: a
    # *different* instance bound later means the profile was started
    # again, and the deletion fails instead of deleting a live new
    # instance (AC-004).

    def set_artifact_cleaner(
        self, cleaner: Callable[[str], Awaitable[None]] | None
    ) -> None:
        """Wire artifact cleanup after construction (the artifact
        service is built after this service in the app lifespan)."""
        self._artifact_cleaner = cleaner

    async def request_deletions(
        self, profile_ids: list[str]
    ) -> tuple[str, list[ProfileDeletionOperation]]:
        """Accept an explicit target set and return one durable intent
        per target. A target with an intent joins it (never a duplicate);
        a late request whose Profile was already deleted concurrently
        joins the finished intent (p136). Only a genuinely missing target
        with no prior intent gets a ``profile_not_found`` failure receipt.

        t085 (p139): the resolve-or-create decision for one target is
        serialized per profile (``ProfileLockRegistry``): the
        check-for-existing / create sequence is no longer interleavable,
        so a second request can no longer slip a duplicate intent in
        after the first intent completed and the partial unique index
        stopped covering it.
        """
        batch_id = uuid.uuid4().hex
        operations: list[ProfileDeletionOperation] = []
        seen: set[str] = set()
        for profile_id in profile_ids:
            if profile_id in seen:
                continue
            seen.add(profile_id)
            async with self._locks.lock(profile_id):
                operations.append(
                    await self._resolve_or_create_deletion(
                        profile_id, batch_id
                    )
                )
        return batch_id, operations

    async def _resolve_or_create_deletion(
        self, profile_id: str, batch_id: str
    ) -> ProfileDeletionOperation:
        """Resolve one target to its single intent.

        Caller must hold the per-profile lock (``self._locks``): every
        read below and the ``create_deletion`` insert run atomically
        against concurrent ``request_deletions`` calls for the same
        profile in this process. The partial unique index plus the
        ``IntegrityError`` retry remain the backstop for other processes.
        """
        existing = await self._repo.find_open_deletion(profile_id)
        if existing is not None:
            return await self._join_deletion(existing, batch_id)
        profile = await self._repo.get_profile(profile_id)
        if profile is None:
            # p136: a concurrent request may have already completed
            # the deletion. Re-join that finished intent instead of
            # creating a second, spurious ``profile_not_found`` one.
            finished = await self._repo.find_deletion_for_profile(profile_id)
            if finished is not None:
                return await self._join_deletion(finished, batch_id)
        try:
            operation = await self._repo.create_deletion(
                batch_id=batch_id,
                profile_id=profile_id,
                profile_name=(
                    profile.config.name if profile else profile_id
                ),
            )
        except IntegrityError:
            # A concurrent submission created the open intent
            # first (the partial unique index rejected ours);
            # join the winner once its transaction commits.
            existing = None
            for _ in range(50):
                existing = await self._repo.find_open_deletion(profile_id)
                if existing is not None:
                    break
                await asyncio.sleep(0.01)
            if existing is None:
                # t085: the winner may have completed while we waited,
                # so no open intent remains — but the finished one is
                # still joinable; only raise when no intent exists at
                # all.
                existing = await self._repo.find_deletion_for_profile(
                    profile_id
                )
            if existing is None:
                raise
            return await self._join_deletion(existing, batch_id)
        if profile is None:
            return await self._fail_deletion(
                operation, "accepted", "profile_not_found"
            )
        self._kick_deletion(operation.id)
        return operation

    async def _join_deletion(
        self,
        existing: ProfileDeletionOperation,
        batch_id: str,
    ) -> ProfileDeletionOperation:
        """Present an existing intent under the batch that just confirmed
        it, so the returned receipt and the batch query agree. Membership
        is tracked separately (p130): the intent's own batch_id is never
        moved, so every confirming client keeps observing the intent.
        A failed intent confirmed again is a retry: resume it from its
        failed stage with the failure cleared. An already-done intent is
        returned as-is (p136): a late request must not create a second,
        spurious ``profile_not_found`` intent."""
        if existing.stage == "failed":
            resumed = await self._repo.update_deletion(
                existing.id,
                stage=existing.failed_stage or "accepted",
                failed_stage=None,
                error=None,
                detail=dict(existing.detail),
            )
            assert resumed is not None
            existing = resumed
        await self._repo.add_batch_member(batch_id, existing.id)
        self._kick_deletion(existing.id)
        return existing

    async def get_deletion(
        self, operation_id: str
    ) -> ProfileDeletionOperation | None:
        return await self._repo.get_deletion(operation_id)

    async def list_deletion_batch(
        self, batch_id: str
    ) -> list[ProfileDeletionOperation]:
        return await self._repo.list_deletions_for_batch(batch_id)

    async def retry_deletion(
        self, operation_id: str
    ) -> ProfileDeletionOperation:
        operation = await self._repo.get_deletion(operation_id)
        if operation is None:
            raise ProfileNotFoundError(operation_id)
        if operation.stage == "done":
            return operation
        if operation.stage != "failed":
            self._kick_deletion(operation.id)
            return operation
        resumed = await self._repo.update_deletion(
            operation.id,
            stage=operation.failed_stage or "accepted",
            failed_stage=None,
            error=None,
            detail=dict(operation.detail),
        )
        assert resumed is not None
        self._kick_deletion(resumed.id)
        return resumed

    async def resume_pending_deletions(self) -> int:
        """Re-drive in-flight intents after a restart; failed intents
        keep waiting for an explicit retry."""
        pending = await self._repo.list_unfinished_deletions()
        for operation in pending:
            self._kick_deletion(operation.id)
        return len(pending)

    async def await_pending_deletions(self) -> None:
        """Wait for deletion background tasks (tests; production never
        blocks on deletions)."""
        tasks = [t for t in self._deletion_tasks.values() if not t.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _kick_deletion(self, operation_id: str) -> None:
        task = self._deletion_tasks.get(operation_id)
        if task is not None and not task.done():
            return
        task = asyncio.get_running_loop().create_task(
            self._drive_deletion_guarded(operation_id)
        )
        self._deletion_tasks[operation_id] = task

    async def _drive_deletion_guarded(self, operation_id: str) -> None:
        lock = self._deletion_locks.setdefault(operation_id, asyncio.Lock())
        async with lock:
            try:
                await self._drive_deletion(operation_id)
            except Exception:  # noqa: BLE001 - a driver crash must not
                # kill the intent silently; record it as a failure.
                logger.exception(
                    "Deletion driver crashed: operation=%s", operation_id
                )
                operation = await self._repo.get_deletion(operation_id)
                if operation is not None and operation.stage not in (
                    "done",
                    "failed",
                ):
                    await self._fail_deletion(
                        operation,
                        operation.stage,
                        "driver_error",
                    )

    async def _fail_deletion(
        self,
        operation: ProfileDeletionOperation,
        failed_stage: str,
        error: str,
    ) -> ProfileDeletionOperation:
        updated = await self._repo.update_deletion(
            operation.id,
            stage="failed",
            failed_stage=failed_stage,
            error=error,
            detail=dict(operation.detail),
        )
        assert updated is not None
        return updated

    async def _drive_deletion(self, operation_id: str) -> None:
        operation = await self._repo.get_deletion(operation_id)
        if operation is None or operation.stage == "done":
            return
        if operation.stage == "accepted":
            # An intent that never started against a profile that does
            # not exist is a failure, not a completed deletion — unless
            # a sibling intent proves the deletion already happened.
            # t085 (p139): a late duplicate intent's driver used to fail
            # here with ``profile_not_found`` because the first intent's
            # machine had already deleted the row; the deletion this
            # intent represents is complete, so it is done, mirroring
            # the clean stage's already-gone handling below. With no
            # sibling, the genuinely-missing receipt semantics stay:
            # a profile that never existed still fails.
            if await self._repo.get_profile(operation.profile_id) is None:
                sibling = await self._repo.find_sibling_deletion(
                    operation.profile_id,
                    exclude_operation_id=operation.id,
                )
                if sibling is not None:
                    detail = dict(operation.detail)
                    steps: dict[str, str] = dict(detail.get("steps") or {})
                    steps.setdefault("database", "ok")
                    detail["steps"] = steps
                    await self._repo.update_deletion(
                        operation.id,
                        stage="done",
                        failed_stage=None,
                        error=None,
                        detail=detail,
                    )
                    return
                await self._fail_deletion(
                    operation, "accepted", "profile_not_found"
                )
                return
        if operation.stage in ("accepted", "stopping"):
            operation = await self._deletion_stop_stage(operation)
            if operation.stage == "failed":
                return
        if operation.stage == "cleaning":
            await self._deletion_clean_stage(operation)

    async def _deletion_stop_stage(
        self, operation: ProfileDeletionOperation
    ) -> ProfileDeletionOperation:
        profile_id = operation.profile_id
        detail = dict(operation.detail)
        runtime = await self._repo.get_runtime(profile_id)
        detail["bound_instance_id"] = (
            runtime.runtime_instance_id if runtime is not None else None
        )
        operation = await self._repo.update_deletion(
            operation.id,
            stage="stopping",
            failed_stage=None,
            error=None,
            detail=detail,
        )
        assert operation is not None
        if runtime is None or not _runtime_has_writer(runtime):
            return await self._advance_deletion(operation, "cleaning")
        await self.set_desired_state(profile_id, "stopped")
        deadline = (
            datetime.datetime.now(datetime.timezone.utc).timestamp()
            + self.deletion_stop_timeout_seconds
        )
        while True:
            runtime = await self._repo.get_runtime(profile_id)
            if runtime is None or not _runtime_has_writer(runtime):
                return await self._advance_deletion(operation, "cleaning")
            if (
                datetime.datetime.now(datetime.timezone.utc).timestamp()
                >= deadline
            ):
                return await self._fail_deletion(
                    operation,
                    "stopping",
                    "stop_timeout: observed_state="
                    f"{runtime.observed_state}, desired_state="
                    f"{runtime.desired_state}, instance_bound="
                    f"{runtime.runtime_instance_id is not None}",
                )
            await asyncio.sleep(self.deletion_poll_interval_seconds)

    async def _advance_deletion(
        self, operation: ProfileDeletionOperation, stage: str
    ) -> ProfileDeletionOperation:
        updated = await self._repo.update_deletion(
            operation.id,
            stage=stage,
            failed_stage=None,
            error=None,
            detail=dict(operation.detail),
        )
        assert updated is not None
        return updated

    async def _deletion_clean_stage(
        self, operation: ProfileDeletionOperation
    ) -> None:
        profile_id = operation.profile_id
        detail = dict(operation.detail)
        steps: dict[str, str] = dict(detail.get("steps") or {})
        detail["steps"] = steps
        async with self._locks.lock(profile_id):
            profile = await self._repo.get_profile(profile_id)
            if profile is None:
                # The row is already gone (a previous pass deleted it
                # and crashed before recording ``done``): the intent is
                # complete, not failed.
                steps.setdefault("database", "ok")
                detail["steps"] = steps
                await self._repo.update_deletion(
                    operation.id,
                    stage="done",
                    failed_stage=None,
                    error=None,
                    detail=detail,
                )
                return
            runtime = await self._repo.get_runtime(profile_id)
            if runtime is not None and runtime.runtime_instance_id is not None:
                if runtime.runtime_instance_id != detail.get(
                    "bound_instance_id"
                ):
                    await self._fail_deletion(
                        operation,
                        "cleaning",
                        "instance_changed: a new runtime instance was "
                        "bound after the stop stage; refusing to delete "
                        "a live instance",
                    )
                    return
                await self._fail_deletion(
                    operation,
                    "cleaning",
                    "instance_still_bound: the stopped instance is "
                    "still bound; refusing to delete underneath it",
                )
                return
            if steps.get("artifacts") != "ok":
                if self._artifact_cleaner is not None:
                    try:
                        await self._artifact_cleaner(profile_id)
                        steps["artifacts"] = "ok"
                    except Exception as exc:  # noqa: BLE001 - recorded
                        steps["artifacts"] = (
                            f"error: {type(exc).__name__}: {exc}"
                        )
                        detail["steps"] = steps
                        operation = await self._repo.update_deletion(
                            operation.id,
                            stage="cleaning",
                            failed_stage=None,
                            error=None,
                            detail=detail,
                        )
                        assert operation is not None
                        await self._fail_deletion(
                            operation,
                            "cleaning",
                            f"artifact_cleanup_failed: {exc}",
                        )
                        return
                else:
                    steps["artifacts"] = "not_configured"
            if steps.get("directories") != "ok":
                dir_error = await self._remove_profile_directories_strict(
                    profile_id
                )
                if dir_error is not None:
                    steps["directories"] = f"error: {dir_error}"
                    detail["steps"] = steps
                    operation = await self._repo.update_deletion(
                        operation.id,
                        stage="cleaning",
                        failed_stage=None,
                        error=None,
                        detail=detail,
                    )
                    assert operation is not None
                    await self._fail_deletion(
                        operation, "cleaning", dir_error
                    )
                    return
                steps["directories"] = "ok"
            await self._clear_preview_state(profile_id)
            steps["preview"] = "ok"
            deleted = await self._repo.delete_profile(profile_id)
            if not deleted and await self._repo.get_profile(profile_id):
                await self._fail_deletion(
                    operation, "cleaning", "database_delete_failed"
                )
                return
            steps["database"] = "ok"
        await self._repo.update_deletion(
            operation.id,
            stage="done",
            failed_stage=None,
            error=None,
            detail=detail,
        )

    async def _remove_profile_directories_strict(
        self, profile_id: str
    ) -> str | None:
        """Remove the profile's private directories, returning the
        first failure instead of only logging it (t078 AC-006)."""
        if self._data_root is None:
            return None
        for sub in ("profiles", "runtime", "runtime-events"):
            target = self._data_root / sub / profile_id
            try:
                await asyncio.to_thread(shutil.rmtree, target)
            except FileNotFoundError:
                pass
            except OSError as exc:
                return f"directory_cleanup_failed: {sub}: {exc}"
        # t080: the per-Profile secret directory lives under
        # runtime/.secrets (runtime volume); it is private credential
        # material and is removed with the Profile.
        secrets = self._data_root / "runtime" / ".secrets" / profile_id
        try:
            await asyncio.to_thread(shutil.rmtree, secrets)
        except FileNotFoundError:
            pass
        except OSError as exc:
            return f"directory_cleanup_failed: runtime/.secrets: {exc}"
        return None

    async def delete_profile(self, profile_id: str) -> bool:
        """Delete through the durable lifecycle (t078).

        The old refuse-if-running semantics are gone: a running profile
        is stopped first, then cleaned. Synchronous callers (the DELETE
        route) drive the same intent the async batch path uses and get
        the final stage as an exception on failure.
        """
        try:
            profile = await self._repo.get_profile(profile_id)
            existing = await self._repo.find_open_deletion(profile_id)
            if profile is None and existing is None:
                raise ProfileNotFoundError(profile_id)
            if existing is not None:
                operation = existing
            else:
                _, operations = await self.request_deletions([profile_id])
                operation = operations[0]
            if operation.stage == "failed" and (
                operation.failed_stage == "accepted"
                and operation.error == "profile_not_found"
            ):
                raise ProfileNotFoundError(profile_id)
            lock = self._deletion_locks.setdefault(
                operation.id, asyncio.Lock()
            )
            async with lock:
                await self._drive_deletion(operation.id)
            final = await self._repo.get_deletion(operation.id)
            assert final is not None
            if final.stage == "done":
                return True
            raise ProfileDeletionFailedError(final)
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

    async def list_runtime_batch(
        self, *, after_profile_id: str | None, limit: int
    ) -> list[ProfileRuntime]:
        """One batch of the Supervisor state snapshot (t083)."""
        try:
            return await self._repo.list_runtimes_batch(
                after_profile_id=after_profile_id, limit=limit
            )
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

    async def get_group(self, group_id: str):
        """One group by id (t076 review f006: the list toolbar shows
        the selected filter value even when it falls outside the first
        bounded candidate page)."""
        return await self._repo.get_group(group_id)

    async def list_groups_page(
        self,
        *,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ):
        """t076 AC-001: bounded server-side group page."""
        return await self._repo.list_groups_page(
            search=search, page=page, page_size=page_size
        )

    async def list_group_candidates(
        self, search: str = "", limit: int = 20
    ) -> list[CandidateEntry]:
        return await self._repo.list_group_candidates(search, limit)

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

    async def list_proxies_page(
        self,
        *,
        search: str | None = None,
        country_code: str | None = None,
        city: str | None = None,
        scheme: str | None = None,
        sort: str = "default",
        page: int = 1,
        page_size: int = 50,
    ):
        """t076 AC-001/AC-006: bounded server-side proxy page."""
        return await self._repo.list_proxies_page(
            search=search,
            country_code=country_code,
            city=city,
            scheme=scheme,
            sort=sort,
            page=page,
            page_size=page_size,
        )

    async def list_proxy_ids_for_filters(
        self,
        *,
        search: str | None = None,
        country_code: str | None = None,
        city: str | None = None,
        scheme: str | None = None,
    ) -> list[str]:
        """Resolve the frozen target set for a filter-scoped probe job."""
        return await self._repo.list_proxy_ids_for_filters(
            search=search,
            country_code=country_code,
            city=city,
            scheme=scheme,
        )

    async def list_proxy_candidates(
        self, search: str = "", limit: int = 20
    ) -> list[ProxyCandidateEntry]:
        return await self._repo.list_proxy_candidates(search, limit)

    async def proxy_country_ranges(self) -> list[ProxyCountryRange]:
        return await self._repo.proxy_country_ranges()

    async def get_proxy_used_by(
        self, proxy_id: str
    ) -> list[ProxyUsedByEntry] | None:
        """t076 AC-004: used-by detail in the same union as the count."""
        proxy = await self._repo.get_proxy(proxy_id)
        if proxy is None:
            return None
        return await self._repo.get_proxy_used_by(proxy_id)

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
                "runner_unavailable",
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
                        country_name=result.country_name,
                        city=result.city,
                        latency_ms=result.latency_ms,
                        status="ok",
                        observed_at=completed_at,
                        expires_at=completed_at
                        + datetime.timedelta(seconds=OBSERVATION_TTL_SECONDS),
                    ),
                )
        return await self._repo.get_proxy(proxy_id)

    def set_probe_job_progress(
        self, callback: Callable[[str], Awaitable[None]] | None
    ) -> None:
        """Wire the SSE progress publisher (app lifespan, t094)."""
        self._probe_job_progress = callback

    async def _publish_probe_job_progress(self, job_id: str) -> None:
        if self._probe_job_progress is None:
            return
        try:
            await self._probe_job_progress(job_id)
        except Exception:  # pragma: no cover - progress is best-effort
            logger.warning("probe job progress publish failed: job=%s", job_id)

    async def request_probe_jobs(
        self, proxy_ids: list[str], *, filters: Any | None = None
    ) -> ProxyProbeJobAccepted:
        """Submit one probe job (t094 AC-003).

        The target set is frozen here; submission persists the job and
        schedules a background driver, returning immediately. ``filters`` is
        accepted for API compatibility but the resolved explicit id set is
        always the authoritative scope (frozen before any work runs).
        """
        job_id = uuid.uuid4().hex
        job = await self._repo.create_probe_job(job_id=job_id, proxy_ids=proxy_ids)
        task = asyncio.create_task(self._drive_probe_job(job_id))
        self._probe_job_tasks[job_id] = task
        task.add_done_callback(lambda t: self._probe_job_tasks.pop(job_id, None))
        return ProxyProbeJobAccepted(
            job_id=job.job_id,
            state=job.state,
            total=job.total,
            completed=job.completed,
            failed=job.failed,
        )

    async def get_probe_job(self, job_id: str) -> ProxyProbeJob | None:
        return await self._repo.get_probe_job(job_id)

    async def list_unfinished_probe_jobs(self) -> list[ProxyProbeJob]:
        jobs = []
        for job_id in await self._repo.list_unfinished_jobs():
            job = await self._repo.get_probe_job(job_id)
            if job is not None:
                jobs.append(job)
        return jobs

    async def resume_pending_probe_jobs(self) -> None:
        """Restart drivers for jobs left running by a process restart.

        Members already terminal are skipped by the repository fence, so a
        resumed job converges without re-running finished work. A job stuck
        with no driver and no terminal members is driven to completion here.
        """
        for job_id in await self._repo.list_unfinished_jobs():
            if job_id in self._probe_job_tasks:
                continue
            task = asyncio.create_task(self._drive_probe_job(job_id))
            self._probe_job_tasks[job_id] = task
            task.add_done_callback(lambda t: self._probe_job_tasks.pop(job_id, None))

    async def await_probe_jobs(self) -> None:
        """Test helper: wait until all live job drivers finish."""
        pending = [t for t in self._probe_job_tasks.values() if not t.done()]
        if pending:
            await asyncio.gather(*pending)

    async def _drive_members(
        self,
        job_id: str,
        job: ProxyProbeJob,
        run: Callable[[str], Awaitable[tuple[str, str | None]]],
    ) -> None:
        """受配额并发驱动所有 pending 成员，串行提交计数与状态（t095 AC-003）。

        探测通过全局 ``_probe_semaphore`` 限流：并发上限内的成员并行执行，
        超限成员排队；单成员异常被就地收敛为 failed，不影响其他成员。
        计数在 ``counter_lock`` 内串行推进，写库仍走 write_transaction 的
        BEGIN IMMEDIATE，因此 SQLite 不会 BUSY，也不会出现计数竞态。
        """
        completed = job.completed
        failed = job.failed
        counter_lock = asyncio.Lock()

        async def drive_one(member: ProxyProbeJobMember) -> None:
            nonlocal completed, failed
            async with self._probe_semaphore:
                try:
                    status, error_code = await run(member.proxy_id)
                except Exception as exc:  # noqa: BLE001 - 单成员故障就地收敛
                    logger.warning(
                        "Probe job member fault: job=%s proxy=%s type=%s",
                        job_id, member.proxy_id, type(exc).__name__,
                    )
                    status, error_code = "failed", "driver_member_fault"
            async with counter_lock:
                if status == "ok":
                    completed += 1
                else:
                    failed += 1
                done = (completed + failed) >= job.total
                await self._repo.update_probe_job_member(
                    job_id=job_id,
                    proxy_id=member.proxy_id,
                    state="ok" if status == "ok" else "failed",
                    error_code=error_code,
                    observation_at=datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    completed=completed,
                    failed=failed,
                    done=done,
                )
                await self._publish_probe_job_progress(job_id)

        tasks = [
            asyncio.create_task(drive_one(member))
            for member in job.members
            if member.state == "pending"
        ]
        try:
            await asyncio.gather(*tasks)
        except Exception as exc:  # noqa: BLE001 - 驱动故障不能悬挂 pending 成员
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.warning(
                "Probe job driver fault: job=%s type=%s",
                job_id, type(exc).__name__, exc_info=True,
            )
            failed += max(0, job.total - completed - failed)
            await self._repo.finalize_probe_job(job_id, completed, failed)
        await self._publish_probe_job_progress(job_id)

    async def _drive_probe_job(self, job_id: str) -> None:
        meta = await self._repo.get_job_meta(job_id)
        if meta is not None and meta[0] == "profile_batch":
            await self._drive_profile_batch_job(job_id, meta[1])
            return
        job = await self._repo.get_probe_job(job_id)
        if job is None:
            return

        async def run(proxy_id: str) -> tuple[str, str | None]:
            return await self._probe_one_member(job_id, proxy_id)

        await self._drive_members(job_id, job, run)

    async def request_profile_batch_job(
        self, action: str, profile_ids: list[str], group_id: str | None = None
    ) -> ProxyProbeJobAccepted:
        """Submit a server-driven environment batch (t094 AC-007).

        The action and options are persisted in the job ``detail`` so a
        process restart can resume the same frozen set with the same action.
        """
        job_id = uuid.uuid4().hex
        detail = json.dumps(
            {"action": action, "group_id": group_id}, separators=(",", ":")
        )
        job = await self._repo.create_probe_job(
            job_id=job_id,
            proxy_ids=profile_ids,
            kind="profile_batch",
            detail=detail,
        )
        task = asyncio.create_task(self._drive_probe_job(job_id))
        self._probe_job_tasks[job_id] = task
        task.add_done_callback(lambda t: self._probe_job_tasks.pop(job_id, None))
        return ProxyProbeJobAccepted(
            job_id=job.job_id, state=job.state, total=job.total
        )

    async def _drive_profile_batch_job(
        self, job_id: str, detail_json: str | None
    ) -> None:
        job = await self._repo.get_probe_job(job_id)
        if job is None:
            return
        try:
            detail = json.loads(detail_json or "{}")
        except ValueError:
            detail = {}
        action = detail.get("action", "start")
        group_id = detail.get("group_id")

        async def run(proxy_id: str) -> tuple[str, str | None]:
            ok = await self._apply_profile_batch_action(
                proxy_id, action, group_id
            )
            return ("ok", None) if ok else ("failed", "batch_action_failed")

        await self._drive_members(job_id, job, run)

    async def _apply_profile_batch_action(
        self, profile_id: str, action: str, group_id: str | None
    ) -> bool:
        """Apply one environment action to one frozen target; never raise.

        Missing profiles / conflicts are per-member failures, not job aborts.
        """
        try:
            if action == "start":
                await self.set_desired_state(profile_id, "running")
            elif action == "stop":
                await self.set_desired_state(profile_id, "stopped")
            elif action == "moveToGroup":
                await self.update_profile(profile_id, {"group_id": group_id})
            else:
                return False
            return True
        except Exception as exc:
            logger.warning(
                "Profile batch action failed: target=%s action=%s type=%s",
                profile_id, action, type(exc).__name__,
            )
            return False

    async def _probe_one_member(self, job_id: str, proxy_id: str) -> tuple[str, str | None]:
        """Probe one frozen member through the shared single-probe path.

        Returns ``(status, error_code)`` where status is ok/failed/gone. The
        observation row written here is the per-item result; the job member
        state and error code are the job-level view (t094 AC-004).
        """
        endpoint_data = await self._repo.get_proxy_endpoint(proxy_id)
        if endpoint_data is None:
            return "gone", "proxy_not_found"
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
                proxy_id, fingerprint, revision, "runner_unavailable",
                datetime.datetime.now(datetime.timezone.utc),
            )
            return "failed", "runner_unavailable"
        try:
            result = await runner.probe(proxy_id, endpoint, revision)
        except EgressProbeError as exc:
            await self._record_failed_observation(
                proxy_id, fingerprint, revision, exc.code,
                datetime.datetime.now(datetime.timezone.utc),
            )
            return "failed", exc.code
        except Exception as exc:
            logger.warning(
                "Probe job member failed: job=%s proxy=%s type=%s",
                job_id, proxy_id, type(exc).__name__,
            )
            await self._record_failed_observation(
                proxy_id, fingerprint, revision, "probe_failed",
                datetime.datetime.now(datetime.timezone.utc),
            )
            return "failed", "probe_failed"
        completed_at = datetime.datetime.now(datetime.timezone.utc)
        await self._repo.record_egress_observation(
            proxy_id,
            EgressObservation(
                proxy_id=proxy_id,
                endpoint_fingerprint=fingerprint,
                credential_revision=revision,
                egress_ip=result.egress_ip,
                country_code=result.country_code,
                country_name=result.country_name,
                city=result.city,
                latency_ms=result.latency_ms,
                source=getattr(result, "source", "local_geoip"),
                status="ok",
                observed_at=completed_at,
                expires_at=completed_at
                + datetime.timedelta(seconds=OBSERVATION_TTL_SECONDS),
            ),
        )
        return "ok", None

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
