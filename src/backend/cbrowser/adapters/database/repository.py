"""Repository implementation for Profile and Runtime operations in SQLite."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from cbrowser.adapters.database.models import (
    AuditEventModel,
    ProfileConfigVersionModel,
    ProfileGroupModel,
    ProfileModel,
    ProfileRuntimeModel,
    ProxyEgressObservationModel,
    ProxyModel,
    RuntimeEventModel,
    SettingModel,
)
from cbrowser.adapters.database.session import write_transaction
from cbrowser.domain.egress_observation import (
    EgressObservation,
    observation_is_current,
)
from cbrowser.domain.models import (
    ConfigVersionSnapshot,
    GroupResponse,
    Profile,
    ProfileConfig,
    ProfileRuntime,
    ProxyResponse,
    RuntimeEvent,
    utc_now_iso,
)
from cbrowser.domain.proxy_endpoint import ProxyEndpoint
from cbrowser.domain.runtime_policy import (
    AUTO_RETRY_DELAYS,
    BLOCK_AFTER_RUNTIME_FAILURES,
)
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class IdempotencyConflictError(Exception):
    def __init__(
        self, message: str = "Operation ID reused with different request payload"
    ):
        super().__init__(message)


class InvalidConfigVersionError(Exception):
    def __init__(self, message: str = "Config version does not exist"):
        super().__init__(message)


class InstanceConflictError(Exception):
    def __init__(self, message: str = "Active instance conflict on runtime"):
        super().__init__(message)


def _hash_request(action: str, target: str, payload: Any) -> str:
    signature = {"action": action, "target": target, "payload": payload}
    serialized = json.dumps(signature, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# t035 AC-006: only a value change in one of these fields creates a new
# config version.  Metadata and the instant preview policy are written
# directly to the profile row without producing a "pending apply" state.
METADATA_FIELDS = frozenset({"name", "notes", "sort_order", "group_id"})
INSTANT_FIELDS = frozenset({"capture_preview"})
CONFIG_VERSION_FIELDS = frozenset(
    set(ProfileConfig.model_fields) - METADATA_FIELDS - INSTANT_FIELDS
)
# Connection fields of a proxy: changing one of these regenerates a config
# version for every profile referencing the proxy (AC-006).  Name, region
# and notes are presentation metadata and do not.
PROXY_CONNECTION_FIELDS = frozenset(
    {"scheme", "host", "port", "username", "password"}
)


class ProfileRepository:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self._session_maker = session_maker

    @staticmethod
    async def _match_operation_audit(
        session: AsyncSession,
        operation_id: str | None,
        sig_hash: str,
    ) -> AuditEventModel | None:
        """Return the recorded audit row for *operation_id*.

        A reused operation id whose stored request signature differs is an
        idempotency conflict, never a replay. This is the single place that
        interprets audit signatures for create/update/desired-state.
        """
        if not operation_id:
            return None
        audit = await session.get(AuditEventModel, operation_id)
        if audit is None:
            return None
        audit_details = json.loads(audit.details)
        if audit_details.get("sig_hash") != sig_hash:
            raise IdempotencyConflictError(
                f"Operation ID {operation_id} reused with different request payload"
            )
        return audit

    async def find_recorded_operation(
        self, operation_id: str | None, action: str, target: str, payload: Any
    ) -> str | None:
        """Return the entity id recorded for a past operation, or None.

        t056 A23: the service-side replay pre-check for the proxy methods
        (which must skip their probe side effects on replay).  The
        signature is interpreted here — the single place — never in the
        service; a mismatched payload raises IdempotencyConflictError.
        """
        if not operation_id:
            return None
        sig_hash = _hash_request(action, target, payload)
        async with self._session_maker() as session:
            audit = await self._match_operation_audit(session, operation_id, sig_hash)
        return audit.entity_id if audit is not None else None

    @staticmethod
    def _record_operation_audit(
        session: AsyncSession,
        *,
        operation_id: str,
        entity_type: str,
        entity_id: str,
        action: str,
        sig_hash: str,
        now: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Stage the audit row that makes a write replayable (t056 A23)."""
        details: dict[str, Any] = {"sig_hash": sig_hash}
        if extra:
            details.update(extra)
        session.add(
            AuditEventModel(
                id=operation_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor="system",
                details=json.dumps(details),
                created_at=now,
            )
        )

    @staticmethod
    async def _load_profile_model(
        session: AsyncSession, profile_id: str
    ) -> ProfileModel | None:
        """Load one profile row.

        Immutable config versions and artifact history are never loaded by
        ordinary profile reads; dedicated repository methods query them.
        """
        stmt = select(ProfileModel).where(ProfileModel.id == profile_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_profile(
        self,
        config: ProfileConfig,
        *,
        profile_id: str | None = None,
        user_data_dir: str | None = None,
        operation_id: str | None = None,
        req_payload: dict[str, Any] | None = None,
        audit_source: str | None = None,
    ) -> Profile:
        pid = profile_id or str(uuid.uuid4())
        udd = user_data_dir or f"/data/profiles/{pid}/profile"
        now = utc_now_iso()
        fallback_payload = {"config": config.model_dump()}
        sig_hash = _hash_request(
            "create_profile",
            "",
            req_payload if req_payload is not None else fallback_payload,
        )

        audit_recorded = False
        try:
            async with self._session_maker() as session, write_transaction(session):
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                if audit is not None:
                    audit_recorded = True
                    existing = await self._load_profile_model(
                        session, audit.entity_id
                    )
                    if existing is not None:
                        return self._to_domain_profile(existing)
                    # The recorded create's target was deleted afterwards.
                    # Replaying the create deterministically restores the
                    # same profile identity instead of leaking a PK conflict
                    # for the already-recorded operation id.
                    pid = audit.entity_id
                    udd = user_data_dir or f"/data/profiles/{pid}/profile"

                await session.execute(
                    text(
                        "INSERT OR IGNORE INTO profile_display_sequence "
                        "(id, value) VALUES (1, 0)"
                    )
                )
                next_number = int(
                    (
                        await session.execute(
                            text(
                                "UPDATE profile_display_sequence "
                                "SET value = value + 1 WHERE id = 1 "
                                "RETURNING value"
                            )
                        )
                    ).scalar_one()
                )
                p_model = ProfileModel(
                    id=pid,
                    display_number=next_number,
                    name=config.name,
                    fingerprint_seed=config.fingerprint_seed,
                    group_id=config.group_id,
                    proxy_id=config.proxy_id,
                    timezone=config.timezone,
                    locale=config.locale,
                    screen_width=config.screen_width,
                    screen_height=config.screen_height,
                    gpu_family=config.gpu_family,
                    humanize=config.humanize,
                    human_preset=config.human_preset,
                    geoip=config.geoip,
                    clipboard_sync=config.clipboard_sync,
                    auto_launch=config.auto_launch,
                    color_scheme=config.color_scheme,
                    fingerprint_platform=config.fingerprint_platform,
                    font_set_id=config.font_set_id,
                    launch_args=json.dumps(config.launch_args),
                    extension_paths=json.dumps(config.extension_paths),
                    allow_3p_cookies=config.allow_3p_cookies,
                    set_google_default=config.set_google_default,
                    capture_preview=config.capture_preview,
                    restore_session=config.restore_session,
                    transparent_proxy=config.transparent_proxy,
                    portable_cookies=config.portable_cookies,
                    notes=config.notes,
                    user_data_dir=udd,
                    sort_order=config.sort_order,
                    current_config_version=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(p_model)

                proxy_credential_revision: int | None = None
                if config.proxy_id:
                    proxy_model = await session.get(ProxyModel, config.proxy_id)
                    if proxy_model is not None:
                        proxy_credential_revision = proxy_model.credential_revision
                snapshot_data = {
                    "config": config.model_dump(),
                    "proxy_credential_revision": proxy_credential_revision,
                }
                v_model = ProfileConfigVersionModel(
                    id=str(uuid.uuid4()),
                    profile_id=pid,
                    version=1,
                    snapshot=json.dumps(snapshot_data),
                    created_at=now,
                )
                session.add(v_model)

                rt_model = ProfileRuntimeModel(
                    profile_id=pid,
                    desired_state="stopped",
                    observed_state="stopped",
                    runtime_instance_id=None,
                    config_version=1,
                    failure_count=0,
                    restart_blocked=False,
                    last_exit_event_id=None,
                    last_started_at=None,
                    last_stopped_at=None,
                    browser_product=None,
                    browser_user_agent=None,
                    updated_at=now,
                )
                session.add(rt_model)

                if operation_id and not audit_recorded:
                    audit = AuditEventModel(
                        id=operation_id,
                        entity_type="profile",
                        entity_id=pid,
                        action="create_profile",
                        actor="system",
                        details=json.dumps(
                            {
                                "sig_hash": sig_hash,
                                "name": config.name,
                                "source": audit_source,
                            }
                        ),
                        created_at=now,
                    )
                    session.add(audit)

            return await self.get_profile(pid)
        except IntegrityError:
            # A concurrent submission of the same operation won the commit
            # race: resolve through the same audit contract as the pre-check.
            async with self._session_maker() as session:
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                existing = (
                    await self._load_profile_model(session, audit.entity_id)
                    if audit is not None
                    else None
                )
            if audit is not None:
                if existing is not None:
                    return self._to_domain_profile(existing)
                return await self.create_profile(
                    config,
                    profile_id=audit.entity_id,
                    user_data_dir=user_data_dir,
                    operation_id=None,
                    req_payload=req_payload,
                    audit_source=audit_source,
                )
            raise

    async def get_audit_event(self, operation_id: str) -> dict | None:
        async with self._session_maker() as session:
            audit = await session.get(AuditEventModel, operation_id)
            if audit is None:
                return None
            return {
                "action": audit.action,
                "entity_id": audit.entity_id,
                "entity_type": audit.entity_type,
                "details": audit.details,
            }

    async def get_profile(self, profile_id: str) -> Profile | None:
        async with self._session_maker() as session:
            model = await self._load_profile_model(session, profile_id)
            if not model:
                return None
            return self._to_domain_profile(model)

    async def list_profiles(self) -> list[Profile]:
        async with self._session_maker() as session:
            stmt = select(ProfileModel).order_by(
                ProfileModel.sort_order.asc(), ProfileModel.created_at.desc()
            )
            result = await session.execute(stmt)
            models = result.scalars().all()
            return [self._to_domain_profile(m) for m in models]

    async def font_set_usage_counts(self) -> dict[tuple[str, str], int]:
        """Count profiles bound to each non-empty font set id (t041 AC-002).

        Keyed by (fingerprint_platform, font_set_id) (t053 A20): the same
        content-addressed id can exist under both platforms, and their
        reference counts are independent.
        """
        async with self._session_maker() as session:
            stmt = (
                select(
                    ProfileModel.fingerprint_platform,
                    ProfileModel.font_set_id,
                    func.count(),
                )
                .where(
                    ProfileModel.font_set_id.is_not(None),
                    ProfileModel.font_set_id != "",
                )
                .group_by(
                    ProfileModel.fingerprint_platform, ProfileModel.font_set_id
                )
            )
            result = await session.execute(stmt)
            return {
                (row[0], row[1]): row[2] for row in result.all() if row[1]
            }

    async def update_profile(
        self,
        profile_id: str,
        patch_data: dict[str, Any] | ProfileConfig,
        *,
        operation_id: str | None = None,
        audit_action: str = "update_profile",
    ) -> Profile | None:
        """Atomically merge supplied patch fields into latest profile state.

        Only a change to an actual runtime-config field creates a new config
        version (t035 AC-006): metadata (name/notes/sort_order/group_id) and
        the instant policy (capture_preview) are written directly.
        Performs update under write_transaction.
        """
        if isinstance(patch_data, ProfileConfig):
            patch_dict = patch_data.model_dump()
        else:
            patch_dict = dict(patch_data)

        sig_hash = _hash_request(
            audit_action,
            profile_id,
            {"patch": patch_dict},
        )
        now = utc_now_iso()

        try:
            async with self._session_maker() as session, write_transaction(session):
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                if audit is not None:
                    existing = await self._load_profile_model(session, profile_id)
                    if existing is not None:
                        return self._to_domain_profile(existing)
                    # Replay against a since-deleted target: the predictable
                    # result is the same "not found" as a fresh update.
                    return None

                p_model = await self._load_profile_model(session, profile_id)
                if not p_model:
                    return None

                # Read fresh current config from database row
                current_dict = {
                    "name": p_model.name,
                    "fingerprint_seed": p_model.fingerprint_seed,
                    "group_id": p_model.group_id,
                    "proxy_id": p_model.proxy_id,
                    "timezone": p_model.timezone,
                    "locale": p_model.locale,
                    "screen_width": p_model.screen_width,
                    "screen_height": p_model.screen_height,
                    "gpu_family": p_model.gpu_family,
                    "humanize": p_model.humanize,
                    "human_preset": p_model.human_preset,
                    "geoip": p_model.geoip,
                    "clipboard_sync": p_model.clipboard_sync,
                    "auto_launch": p_model.auto_launch,
                    "color_scheme": p_model.color_scheme,
                    "fingerprint_platform": p_model.fingerprint_platform,
                    "font_set_id": p_model.font_set_id,
                    "launch_args": json.loads(p_model.launch_args)
                    if p_model.launch_args
                    else [],
                    "extension_paths": json.loads(p_model.extension_paths)
                    if p_model.extension_paths
                    else [],
                    "allow_3p_cookies": p_model.allow_3p_cookies,
                    "set_google_default": p_model.set_google_default,
                    "capture_preview": p_model.capture_preview,
                    "restore_session": p_model.restore_session,
                    "transparent_proxy": p_model.transparent_proxy,
                    "portable_cookies": p_model.portable_cookies,
                    "notes": p_model.notes,
                    "sort_order": p_model.sort_order,
                }

                # Merge ONLY the supplied patch fields
                old_cfg = ProfileConfig(**current_dict)
                current_dict.update(patch_dict)
                merged_cfg = ProfileConfig(**current_dict)

                runtime_changed = any(
                    getattr(old_cfg, key) != getattr(merged_cfg, key)
                    for key in CONFIG_VERSION_FIELDS
                )
                new_version = p_model.current_config_version
                if runtime_changed:
                    max_v_stmt = select(
                        func.max(ProfileConfigVersionModel.version)
                    ).where(ProfileConfigVersionModel.profile_id == profile_id)
                    max_v = (await session.execute(max_v_stmt)).scalar() or 0
                    new_version = max_v + 1

                # Update model fields
                p_model.name = merged_cfg.name
                p_model.fingerprint_seed = merged_cfg.fingerprint_seed
                p_model.group_id = merged_cfg.group_id
                p_model.proxy_id = merged_cfg.proxy_id
                p_model.timezone = merged_cfg.timezone
                p_model.locale = merged_cfg.locale
                p_model.screen_width = merged_cfg.screen_width
                p_model.screen_height = merged_cfg.screen_height
                p_model.gpu_family = merged_cfg.gpu_family
                p_model.humanize = merged_cfg.humanize
                p_model.human_preset = merged_cfg.human_preset
                p_model.geoip = merged_cfg.geoip
                p_model.clipboard_sync = merged_cfg.clipboard_sync
                p_model.auto_launch = merged_cfg.auto_launch
                p_model.color_scheme = merged_cfg.color_scheme
                p_model.fingerprint_platform = merged_cfg.fingerprint_platform
                p_model.font_set_id = merged_cfg.font_set_id
                p_model.launch_args = json.dumps(merged_cfg.launch_args)
                p_model.extension_paths = json.dumps(merged_cfg.extension_paths)
                p_model.allow_3p_cookies = merged_cfg.allow_3p_cookies
                p_model.set_google_default = merged_cfg.set_google_default
                if old_cfg.capture_preview != merged_cfg.capture_preview:
                    p_model.capture_preview_epoch = (
                        p_model.capture_preview_epoch or 0
                    ) + 1
                p_model.capture_preview = merged_cfg.capture_preview
                p_model.restore_session = merged_cfg.restore_session
                p_model.transparent_proxy = merged_cfg.transparent_proxy
                p_model.portable_cookies = merged_cfg.portable_cookies
                p_model.notes = merged_cfg.notes
                p_model.sort_order = merged_cfg.sort_order
                p_model.current_config_version = new_version
                p_model.updated_at = now

                if runtime_changed:
                    # Snapshot holds only the proxy id and credential
                    # revision; the password itself lives solely in proxies.
                    proxy_credential_revision: int | None = None
                    if merged_cfg.proxy_id:
                        proxy_model = await session.get(
                            ProxyModel, merged_cfg.proxy_id
                        )
                        if proxy_model is not None:
                            proxy_credential_revision = (
                                proxy_model.credential_revision
                            )
                    snapshot_data = {
                        "config": merged_cfg.model_dump(),
                        "proxy_credential_revision": proxy_credential_revision,
                    }
                    session.add(
                        ProfileConfigVersionModel(
                            id=str(uuid.uuid4()),
                            profile_id=profile_id,
                            version=new_version,
                            snapshot=json.dumps(snapshot_data),
                            created_at=now,
                        )
                    )

                if operation_id:
                    session.add(
                        AuditEventModel(
                            id=operation_id,
                            entity_type="profile",
                            entity_id=profile_id,
                            action=audit_action,
                            actor="system",
                            details=json.dumps(
                                {"sig_hash": sig_hash, "version": new_version}
                            ),
                            created_at=now,
                        )
                    )

            return await self.get_profile(profile_id)
        except IntegrityError:
            async with self._session_maker() as session:
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                if audit is not None:
                    existing = await self._load_profile_model(session, profile_id)
                    if existing is not None:
                        return self._to_domain_profile(existing)
                    return None
            raise

    async def delete_profile(self, profile_id: str) -> bool:
        async with self._session_maker() as session, write_transaction(session):
            p_model = await session.get(ProfileModel, profile_id)
            if not p_model:
                return False
            await session.delete(p_model)
            return True

    async def list_config_versions(
        self, profile_id: str
    ) -> list[ConfigVersionSnapshot]:
        async with self._session_maker() as session:
            stmt = (
                select(ProfileConfigVersionModel)
                .where(ProfileConfigVersionModel.profile_id == profile_id)
                .order_by(ProfileConfigVersionModel.version.asc())
            )
            result = await session.execute(stmt)
            models = result.scalars().all()
            return [self._to_domain_snapshot(m) for m in models]

    async def get_config_version(
        self, profile_id: str, version: int
    ) -> ConfigVersionSnapshot | None:
        async with self._session_maker() as session:
            stmt = select(ProfileConfigVersionModel).where(
                ProfileConfigVersionModel.profile_id == profile_id,
                ProfileConfigVersionModel.version == version,
            )
            result = await session.execute(stmt)
            m = result.scalar_one_or_none()
            if not m:
                return None
            return self._to_domain_snapshot(m)

    async def get_runtime(self, profile_id: str) -> ProfileRuntime | None:
        async with self._session_maker() as session:
            m = await session.get(ProfileRuntimeModel, profile_id)
            if not m:
                return None
            profile = await session.get(ProfileModel, profile_id)
            if profile is None or profile.display_number is None:
                raise RuntimeError("Profile is missing its display number")
            return self._to_domain_runtime(
                m, display_number=profile.display_number
            )

    async def bind_runtime_instance(
        self,
        profile_id: str,
        runtime_instance_id: str,
        config_version: int = 1,
        expected_current_instance: str | None = None,
    ) -> ProfileRuntime | None:
        """Supervisor binds container instance with applied config version.

        Marks observed starting under write_transaction.
        """
        now = utc_now_iso()
        async with self._session_maker() as session, write_transaction(session):
            m = await session.get(ProfileRuntimeModel, profile_id)
            if not m:
                return None

            # Validate config_version exists for this profile
            v_exists = (
                await session.execute(
                    select(1).where(
                        ProfileConfigVersionModel.profile_id == profile_id,
                        ProfileConfigVersionModel.version == config_version,
                    )
                )
            ).scalar()
            if not v_exists:
                raise InvalidConfigVersionError(
                    f"Config version {config_version} does not exist "
                    f"for profile {profile_id}"
                )

            # Idempotent re-bind of same instance
            if m.runtime_instance_id == runtime_instance_id:
                if m.config_version != config_version:
                    raise InvalidConfigVersionError(
                        f"Cannot change bound config_version for existing "
                        f"instance {runtime_instance_id} from {m.config_version} "
                        f"to {config_version}"
                    )
                # MUST NOT regress observed_state from running back to starting!
                return await self._runtime_with_number(session, m)

            # Check if runtime_instance_id was previously bound or exited
            prev_seen = (
                await session.execute(
                    select(1).where(
                        RuntimeEventModel.profile_id == profile_id,
                        RuntimeEventModel.runtime_instance_id == runtime_instance_id,
                    )
                )
            ).scalar()
            if prev_seen:
                raise InstanceConflictError(
                    f"Cannot bind stale instance {runtime_instance_id}: "
                    "instance was already superseded"
                )

            # Active instance guard: cannot overwrite an already active instance
            # unless expected_current_instance matches!
            if (
                m.runtime_instance_id is not None
                and m.observed_state in ("starting", "running")
                and (
                    expected_current_instance is None
                    or expected_current_instance != m.runtime_instance_id
                )
            ):
                raise InstanceConflictError(
                    f"Cannot bind instance {runtime_instance_id}: profile "
                    f"currently has active instance {m.runtime_instance_id}"
                )

            m.runtime_instance_id = runtime_instance_id
            m.config_version = config_version
            m.observed_state = "starting"
            m.backoff_started_at = None
            m.next_retry_at = None
            m.updated_at = now

            # Record bind lifecycle event
            session.add(
                RuntimeEventModel(
                    event_id=f"bind_{uuid.uuid4().hex}",
                    profile_id=profile_id,
                    runtime_instance_id=runtime_instance_id,
                    event_type="lifecycle",
                    exit_code=None,
                    exit_reason=None,
                    config_version=config_version,
                    payload=json.dumps({"action": "bind"}),
                    created_at=now,
                )
            )

        return await self.get_runtime(profile_id)

    async def get_preview_policy(self, profile_id: str) -> tuple[bool, int] | None:
        """Return (enabled, epoch) for the API-authoritative preview policy."""
        async with self._session_maker() as session:
            profile = await session.get(ProfileModel, profile_id)
            if profile is None:
                return None
            return profile.capture_preview, profile.capture_preview_epoch

    async def record_preview_capture(
        self,
        profile_id: str,
        captured_at: str,
        runtime_instance_id: str,
        policy_epoch: int,
    ) -> bool:
        """Persist preview_captured_at only for a live policy epoch and instance.

        Revocations, epoch bumps and stale instance callbacks are dropped, so a
        late write can never resurrect a deleted preview (t040 AC-004).
        """
        async with self._session_maker() as session, write_transaction(session):
            profile = await session.get(ProfileModel, profile_id)
            runtime = await session.get(ProfileRuntimeModel, profile_id)
            if (
                profile is None
                or runtime is None
                or not profile.capture_preview
                or profile.capture_preview_epoch != policy_epoch
                or runtime.runtime_instance_id != runtime_instance_id
            ):
                return False
            runtime.preview_captured_at = captured_at
            return True

    async def clear_preview_capture(self, profile_id: str) -> None:
        async with self._session_maker() as session, write_transaction(session):
            runtime = await session.get(ProfileRuntimeModel, profile_id)
            if runtime is not None:
                runtime.preview_captured_at = None

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
    ) -> ProfileRuntime | None:
        """Supervisor reports authoritative observed state for an instance.

        Observation is the only lifecycle authority: a terminal error keeps the
        user's running intent, counts one failure and releases the instance so
        the recovery coordinator can start a fresh generation. A clean browser
        close (``reason="normal_exit"``) clears running intent like a user stop.
        """
        now = utc_now_iso()
        async with self._session_maker() as session, write_transaction(session):
            m = await session.get(ProfileRuntimeModel, profile_id)
            if not m or m.runtime_instance_id != runtime_instance_id:
                return None
            if config_version is not None and config_version != m.config_version:
                raise InvalidConfigVersionError(
                    f"Reported config_version {config_version} does not "
                    f"match instance's bound version {m.config_version}"
                )
            previous = m.observed_state
            m.observed_state = observed_state
            if observed_state == "running":
                m.last_started_at = now
                m.backoff_started_at = None
                m.next_retry_at = None
                if browser_product is not None:
                    m.browser_product = browser_product
                if browser_user_agent is not None:
                    m.browser_user_agent = browser_user_agent
            elif observed_state in ("stopped", "error"):
                m.last_stopped_at = now
                m.browser_product = None
                m.browser_user_agent = None
            observation_id = f"observed_error:{runtime_instance_id}"
            already_counted = (
                previous == "error" or m.last_exit_event_id == observation_id
            )
            if observed_state == "error" and not already_counted:
                m.failure_count += 1
                m.last_exit_event_id = f"observed_error:{runtime_instance_id}"
                if m.failure_count >= BLOCK_AFTER_RUNTIME_FAILURES:
                    m.restart_blocked = True
                m.runtime_instance_id = None
                m.backoff_started_at = now
                if m.failure_count <= len(AUTO_RETRY_DELAYS):
                    m.next_retry_at = (
                        datetime.fromisoformat(now)
                        + timedelta(seconds=AUTO_RETRY_DELAYS[m.failure_count - 1])
                    ).isoformat()
                else:
                    m.next_retry_at = None
                session.add(
                    RuntimeEventModel(
                        event_id=f"observed_error:{runtime_instance_id}",
                        profile_id=profile_id,
                        runtime_instance_id=runtime_instance_id,
                        event_type="lifecycle",
                        exit_code=None,
                        exit_reason=reason,
                        config_version=m.config_version,
                        payload=json.dumps(
                            {"source": "supervisor_observation", "reason": reason}
                        ),
                        created_at=now,
                    )
                )
            elif observed_state == "stopped":
                m.runtime_instance_id = None
                if reason == "normal_exit" and m.desired_state == "running":
                    m.desired_state = "stopped"
                    m.failure_count = 0
            m.updated_at = now
            return await self._runtime_with_number(session, m)

    async def set_desired_state(
        self, profile_id: str, desired_state: str, *, operation_id: str | None = None
    ) -> ProfileRuntime | None:
        """User sets intent.

        Replay of same operation_id returns state without resetting failures.
        """
        now = utc_now_iso()
        sig_hash = _hash_request(
            "set_desired_state", profile_id, {"desired_state": desired_state}
        )

        async with self._session_maker() as session, write_transaction(session):
            m = await session.get(ProfileRuntimeModel, profile_id)
            if not m:
                return None

            if operation_id:
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                if audit is not None:
                    # Idempotent replay: return current state without resetting failures
                    return await self._runtime_with_number(session, m)

                session.add(
                    AuditEventModel(
                        id=operation_id,
                        entity_type="profile_runtime",
                        entity_id=profile_id,
                        action="set_desired_state",
                        actor="system",
                        details=json.dumps(
                            {"sig_hash": sig_hash, "desired_state": desired_state}
                        ),
                        created_at=now,
                    )
                )

            # Fresh manual user intent: an errored profile with no bound
            # instance converges to stopped when the user asks it to stop
            # (t035 AC-011).
            m.desired_state = desired_state
            if desired_state == "running":
                m.failure_count = 0
                m.restart_blocked = False
                m.backoff_started_at = None
                m.next_retry_at = None
            elif (
                desired_state == "stopped"
                and m.observed_state == "error"
                and m.runtime_instance_id is None
            ):
                m.observed_state = "stopped"
                m.last_stopped_at = now
            m.updated_at = now
        return await self.get_runtime(profile_id)

    async def consume_runtime_event(self, event: RuntimeEvent) -> str:
        """Process runtime event atomically.

        Matches bound config version and handles parallel duplicates.
        """
        now = utc_now_iso()

        if event.event_type == "exit" and event.exit_code is None:
            raise ValueError("exit_code cannot be None for exit event")

        try:
            async with self._session_maker() as session, write_transaction(session):
                # 1. Deduplication check by event_id
                existing_event = await session.get(RuntimeEventModel, event.event_id)
                if existing_event:
                    return "duplicate"

                # 2. Find profile runtime
                rt = await session.get(ProfileRuntimeModel, event.profile_id)
                if not rt:
                    return "profile_not_found"

                # 3. Instance guard: reject events from older instances
                if rt.runtime_instance_id != event.runtime_instance_id:
                    session.add(
                        RuntimeEventModel(
                            event_id=event.event_id,
                            profile_id=event.profile_id,
                            runtime_instance_id=event.runtime_instance_id,
                            event_type=event.event_type,
                            exit_code=event.exit_code,
                            exit_reason=event.exit_reason,
                            config_version=event.config_version,
                            payload=json.dumps(event.payload),
                            created_at=now,
                        )
                    )
                    return "stale_instance"

                # 4. Bound config version match: event must match bound version!
                if event.config_version != rt.config_version:
                    session.add(
                        RuntimeEventModel(
                            event_id=event.event_id,
                            profile_id=event.profile_id,
                            runtime_instance_id=event.runtime_instance_id,
                            event_type=event.event_type,
                            exit_code=event.exit_code,
                            exit_reason=event.exit_reason,
                            config_version=event.config_version,
                            payload=json.dumps(event.payload),
                            created_at=now,
                        )
                    )
                    return "invalid_config_version"

                # 5. Events are diagnostics only. Lifecycle authority comes from
                # the Supervisor's Docker/Agent observations, never from files
                # writable by the sandboxed Profile.
                session.add(
                    RuntimeEventModel(
                        event_id=event.event_id,
                        profile_id=event.profile_id,
                        runtime_instance_id=event.runtime_instance_id,
                        event_type=event.event_type,
                        exit_code=event.exit_code,
                        exit_reason=event.exit_reason,
                        config_version=event.config_version,
                        payload=json.dumps(event.payload),
                        created_at=now,
                    )
                )
                return "applied"
        except IntegrityError:
            # Concurrent race on duplicate event_id PK: check if already committed
            async with self._session_maker() as read_session:
                existing = await read_session.get(RuntimeEventModel, event.event_id)
                if existing:
                    return "duplicate"
            raise

    async def _runtime_with_number(self, session, m):
        profile = await session.get(ProfileModel, m.profile_id)
        if profile is None or profile.display_number is None:
            raise RuntimeError("Profile is missing its display number")
        return self._to_domain_runtime(m, display_number=profile.display_number)

    @staticmethod
    def _to_domain_runtime(
        m: ProfileRuntimeModel, *, display_number: int
    ) -> ProfileRuntime:
        return ProfileRuntime(
            profile_id=m.profile_id,
            display_number=display_number,
            desired_state=m.desired_state,  # type: ignore
            observed_state=m.observed_state,  # type: ignore
            runtime_instance_id=m.runtime_instance_id,
            config_version=m.config_version,
            failure_count=m.failure_count,
            restart_blocked=m.restart_blocked,
            last_exit_event_id=m.last_exit_event_id,
            last_started_at=m.last_started_at,
            last_stopped_at=m.last_stopped_at,
            browser_product=m.browser_product,
            browser_user_agent=m.browser_user_agent,
            backoff_started_at=m.backoff_started_at,
            next_retry_at=m.next_retry_at,
            preview_captured_at=m.preview_captured_at,
            updated_at=m.updated_at,
        )

    @staticmethod
    def _to_domain_snapshot(m: ProfileConfigVersionModel) -> ConfigVersionSnapshot:
        parsed = json.loads(m.snapshot)
        cfg = parsed["config"] if isinstance(parsed, dict) and "config" in parsed else parsed
        proxy_credential_revision = (
            parsed.get("proxy_credential_revision")
            if isinstance(parsed, dict)
            else None
        )
        return ConfigVersionSnapshot(
            id=m.id,
            profile_id=m.profile_id,
            version=m.version,
            config=cfg,
            proxy_credential_revision=proxy_credential_revision,
            created_at=m.created_at,
        )

    @staticmethod
    def _to_domain_profile(m: ProfileModel) -> Profile:
        cfg = ProfileConfig(
            name=m.name,
            fingerprint_seed=m.fingerprint_seed,
            group_id=m.group_id,
            proxy_id=m.proxy_id,
            timezone=m.timezone,
            locale=m.locale,
            screen_width=m.screen_width,
            screen_height=m.screen_height,
            gpu_family=m.gpu_family,  # type: ignore
            humanize=m.humanize,
            human_preset=m.human_preset,  # type: ignore
            geoip=m.geoip,
            clipboard_sync=m.clipboard_sync,
            auto_launch=m.auto_launch,
            color_scheme=m.color_scheme,  # type: ignore
            fingerprint_platform=m.fingerprint_platform,  # type: ignore
            font_set_id=m.font_set_id,  # type: ignore
            launch_args=json.loads(m.launch_args) if m.launch_args else [],
            extension_paths=json.loads(m.extension_paths) if m.extension_paths else [],
            allow_3p_cookies=m.allow_3p_cookies,
            set_google_default=m.set_google_default,
            capture_preview=m.capture_preview,
            restore_session=m.restore_session,
            transparent_proxy=m.transparent_proxy,
            portable_cookies=m.portable_cookies,
            notes=m.notes,
            sort_order=m.sort_order,
        )
        if m.display_number is None:
            # t056 A21: display_number is NOT NULL since 0009; a NULL row
            # is a corrupt database, never a defaultable 1.
            raise RuntimeError(
                f"Profile {m.id} is missing its display number"
            )
        return Profile(
            id=m.id,
            display_number=m.display_number,
            config=cfg,
            user_data_dir=m.user_data_dir,
            sort_order=m.sort_order,
            current_config_version=m.current_config_version,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    # ---- Groups (t035 AC-003) -------------------------------------------

    @staticmethod
    def _to_domain_group(m: ProfileGroupModel) -> GroupResponse:
        return GroupResponse(
            id=m.id,
            name=m.name,
            color=m.color,  # type: ignore
            sort_order=m.sort_order,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    async def list_groups(self) -> list[GroupResponse]:
        async with self._session_maker() as session:
            stmt = select(ProfileGroupModel).order_by(
                ProfileGroupModel.sort_order.asc(), ProfileGroupModel.created_at.asc()
            )
            result = await session.execute(stmt)
            return [self._to_domain_group(m) for m in result.scalars().all()]

    async def get_group(self, group_id: str) -> GroupResponse | None:
        """One group by id (t056 A28: reference validation)."""
        async with self._session_maker() as session:
            model = await session.get(ProfileGroupModel, group_id)
            if model is None:
                return None
            return self._to_domain_group(model)

    async def create_group(
        self, name: str, color: str, sort_order: int, *, operation_id: str | None = None,
        _allow_rebuild: bool = True,
    ) -> GroupResponse:
        """Create a group (t056 A23: replayable via Idempotency-Key, like
        create_profile).  A replay returns the first group; a replay after
        deletion restores the same id."""
        now = utc_now_iso()
        payload = {"name": name, "color": color, "sort_order": sort_order}
        sig_hash = _hash_request("create_group", "", payload)
        gid = str(uuid.uuid4())
        audit_recorded = False
        try:
            async with self._session_maker() as session, write_transaction(session):
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                if audit is not None:
                    audit_recorded = True
                    existing = await session.get(ProfileGroupModel, audit.entity_id)
                    if existing is not None:
                        return self._to_domain_group(existing)
                    gid = audit.entity_id
                model = ProfileGroupModel(
                    id=gid,
                    name=name,
                    color=color,
                    sort_order=sort_order,
                    created_at=now,
                    updated_at=now,
                )
                session.add(model)
                if operation_id and not audit_recorded:
                    self._record_operation_audit(
                        session,
                        operation_id=operation_id,
                        entity_type="group",
                        entity_id=gid,
                        action="create_group",
                        sig_hash=sig_hash,
                        now=now,
                        extra={"name": name},
                    )
            return self._to_domain_group(model)
        except IntegrityError as exc:
            # A concurrent submission of the same operation won the commit
            # race: resolve through the same audit contract.
            async with self._session_maker() as session:
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                if audit is not None:
                    existing = await session.get(ProfileGroupModel, audit.entity_id)
                    if existing is not None:
                        return self._to_domain_group(existing)
                    # The recorded entity was deleted: rebuild it under
                    # the same id — unless the name is now taken by
                    # another entity (t056_code_f002). Re-inserting
                    # would hit the same unique-name constraint again,
                    # so an unconditional retry recurses until
                    # RecursionError and surfaces as 500 instead of a
                    # clean 409 group_name_in_use. A rebuild is
                    # attempted at most once.
                    name_taken = (
                        await session.execute(
                            select(ProfileGroupModel.id)
                            .where(ProfileGroupModel.name == name)
                            .limit(1)
                        )
                    ).scalars().first() is not None
                    if name_taken or not _allow_rebuild:
                        raise ValueError("group name already exists") from exc
                    return await self.create_group(
                        name,
                        color,
                        sort_order,
                        operation_id=operation_id,
                        _allow_rebuild=False,
                    )
            raise ValueError("group name already exists") from exc

    async def update_group(
        self, group_id: str, patch: dict[str, Any], *, operation_id: str | None = None
    ) -> GroupResponse | None:
        """Update a group (t056 A23: replayable via Idempotency-Key)."""
        now = utc_now_iso()
        sig_hash = _hash_request("update_group", group_id, {"patch": patch})
        try:
            async with self._session_maker() as session, write_transaction(session):
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                if audit is not None:
                    model = await session.get(ProfileGroupModel, group_id)
                    if model is None:
                        return None
                    return self._to_domain_group(model)
                model = await session.get(ProfileGroupModel, group_id)
                if model is None:
                    return None
                for key, value in patch.items():
                    setattr(model, key, value)
                model.updated_at = now
                if operation_id:
                    self._record_operation_audit(
                        session,
                        operation_id=operation_id,
                        entity_type="group",
                        entity_id=group_id,
                        action="update_group",
                        sig_hash=sig_hash,
                        now=now,
                    )
                return self._to_domain_group(model)
        except IntegrityError as exc:
            async with self._session_maker() as session:
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                if audit is not None:
                    model = await session.get(ProfileGroupModel, group_id)
                    if model is not None:
                        return self._to_domain_group(model)
                    return None
            raise ValueError("group name already exists") from exc

    async def delete_group(
        self, group_id: str, *, operation_id: str | None = None
    ) -> bool:
        """Delete a group (t056 A23: replayable via Idempotency-Key — a
        replay returns the recorded success, not 404)."""
        now = utc_now_iso()
        sig_hash = _hash_request("delete_group", group_id, {})
        try:
            async with self._session_maker() as session, write_transaction(session):
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                if audit is not None:
                    return True
                model = await session.get(ProfileGroupModel, group_id)
                if model is None:
                    return False
                await session.delete(model)
                if operation_id:
                    self._record_operation_audit(
                        session,
                        operation_id=operation_id,
                        entity_type="group",
                        entity_id=group_id,
                        action="delete_group",
                        sig_hash=sig_hash,
                        now=now,
                    )
                return True
        except IntegrityError:
            async with self._session_maker() as session:
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                if audit is not None:
                    return True
            raise

    async def reorder_groups(self, ordered_ids: list[str]) -> list[GroupResponse]:
        now = utc_now_iso()
        async with self._session_maker() as session, write_transaction(session):
            for index, group_id in enumerate(ordered_ids):
                model = await session.get(ProfileGroupModel, group_id)
                if model is None:
                    raise ValueError(f"unknown group {group_id}")
                model.sort_order = index
                model.updated_at = now
        return await self.list_groups()

    # ---- Proxies (t035 AC-004 / AC-005 / AC-006) -----------------------

    @staticmethod
    def _to_domain_proxy(
        m: ProxyModel,
        used_by_count: int,
        observation: EgressObservation | None = None,
    ) -> ProxyResponse:
        endpoint = ProxyEndpoint(
            scheme=m.scheme,  # type: ignore[arg-type]
            host=m.host,
            port=m.port,
            username=m.username,
            password=None,
        )
        return ProxyResponse(
            id=m.id,
            name=m.name,
            scheme=m.scheme,  # type: ignore
            host=m.host,
            port=m.port,
            username=m.username,
            has_password=bool(m.password),
            credential_revision=m.credential_revision,
            proxy_url=endpoint.redacted_link(),
            country_code=observation.country_code if observation else None,
            egress_ip=observation.egress_ip if observation else None,
            observation_status=observation.status if observation else "unknown",  # type: ignore[arg-type]
            observed_at=observation.observed_at.isoformat()
            if observation and observation.observed_at
            else None,
            region_label=m.region_label,
            notes=m.notes,
            used_by_count=used_by_count,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    @staticmethod
    def _observation_to_domain(m: ProxyEgressObservationModel) -> EgressObservation:
        def _parse(value: str | None) -> datetime.datetime | None:
            return datetime.fromisoformat(value) if value else None

        return EgressObservation(
            proxy_id=m.proxy_id,
            endpoint_fingerprint=m.endpoint_fingerprint,
            credential_revision=m.credential_revision,
            perspective=m.perspective,
            egress_ip=m.egress_ip,
            country_code=m.country_code,
            source=m.source,
            status=m.status,  # type: ignore[arg-type]
            error_code=m.error_code,
            observed_at=_parse(m.observed_at),
            expires_at=_parse(m.expires_at),
        )

    @staticmethod
    def _visible_observation(
        obs: EgressObservation, proxy: ProxyModel, now: datetime.datetime
    ) -> EgressObservation | None:
        """Apply the currency rule to one row: a pending/failed row is
        still surfaced (its status drives the UI "detecting"/"unknown"
        states); only a stale *ok* row is hidden (AC-007)."""
        if obs.status != "ok":
            return obs
        endpoint = ProxyEndpoint(
            scheme=proxy.scheme,  # type: ignore[arg-type]
            host=proxy.host,
            port=proxy.port,
            username=proxy.username,
        )
        if observation_is_current(
            obs, endpoint.fingerprint, proxy.credential_revision, now
        ):
            return obs
        return None

    async def _current_observation(
        self, session: AsyncSession, proxy: ProxyModel
    ) -> EgressObservation | None:
        """Latest observation row, but only when it is still current for
        the proxy's present endpoint fingerprint and credential revision
        (AC-007: endpoint/credential change or expiry invalidates it)."""
        stmt = (
            select(ProxyEgressObservationModel)
            .where(ProxyEgressObservationModel.proxy_id == proxy.id)
            .order_by(
                ProxyEgressObservationModel.observed_at.desc(),
                ProxyEgressObservationModel.created_at.desc(),
            )
            .limit(1)
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        obs = self._observation_to_domain(row)
        return self._visible_observation(obs, proxy, datetime.now(timezone.utc))

    async def _current_observations(
        self, session: AsyncSession, models: list[ProxyModel]
    ) -> dict[str, EgressObservation | None]:
        """Current observation per proxy in a single bounded query
        (code f005/f007).

        The per-row ``_current_observation`` inside ``list_proxies`` was
        one SELECT per proxy; this fetches every proxy's latest row with
        one ``WHERE proxy_id IN (...)``.  The first batch version fetched
        *all* history rows and picked the latest in Python, so the
        transfer grew with history (code f007).  The query below ranks
        rows per proxy with ``ROW_NUMBER()`` and only returns the latest
        row per proxy — one row per proxy, in a single SELECT — with the
        same ordering as the single-row path (``observed_at`` desc,
        ``created_at`` desc; ``id`` desc only breaks exact ties
        deterministically).
        """
        result: dict[str, EgressObservation | None] = {m.id: None for m in models}
        if not models:
            return result
        ranked = (
            select(
                ProxyEgressObservationModel.id,
                func.row_number()
                .over(
                    partition_by=ProxyEgressObservationModel.proxy_id,
                    order_by=[
                        ProxyEgressObservationModel.observed_at.desc(),
                        ProxyEgressObservationModel.created_at.desc(),
                        ProxyEgressObservationModel.id.desc(),
                    ],
                )
                .label("rn"),
            )
            .where(ProxyEgressObservationModel.proxy_id.in_([m.id for m in models]))
            .subquery()
        )
        stmt = select(ProxyEgressObservationModel).where(
            ProxyEgressObservationModel.id.in_(
                select(ranked.c.id).where(ranked.c.rn == 1)
            )
        )
        rows = (await session.execute(stmt)).scalars().all()
        now = datetime.now(timezone.utc)
        by_id = {m.id: m for m in models}
        for row in rows:
            obs = self._observation_to_domain(row)
            result[row.proxy_id] = self._visible_observation(
                obs, by_id[row.proxy_id], now
            )
        return result

    async def _proxy_used_by_current(
        self, session: AsyncSession, proxy_id: str
    ) -> set[str]:
        """Profiles whose CURRENT config references the proxy."""
        current = (
            await session.execute(
                select(ProfileModel.id).where(ProfileModel.proxy_id == proxy_id)
            )
        ).scalars().all()
        return set(current)

    async def _proxy_used_by_bound(
        self, session: AsyncSession, proxy_id: str
    ) -> set[str]:
        """Profiles whose RUNNING bound version snapshot references the proxy."""
        result: set[str] = set()
        runtimes = (
            await session.execute(select(ProfileRuntimeModel))
        ).scalars().all()
        for rt in runtimes:
            version = (
                await session.execute(
                    select(ProfileConfigVersionModel).where(
                        ProfileConfigVersionModel.profile_id == rt.profile_id,
                        ProfileConfigVersionModel.version == rt.config_version,
                    )
                )
            ).scalar_one_or_none()
            if version is None:
                continue
            parsed = json.loads(version.snapshot)
            cfg = parsed.get("config", parsed) if isinstance(parsed, dict) else parsed
            if isinstance(cfg, dict) and cfg.get("proxy_id") == proxy_id:
                result.add(rt.profile_id)
        return result

    async def _proxy_used_by(
        self, session: AsyncSession, proxy_id: str
    ) -> list[str]:
        """Profiles whose current config OR runtime-bound version reference it.

        Union semantics are kept for delete-refusal and the used_by count:
        a bound-only reference still blocks deletion (t056 A17).
        """
        result = await self._proxy_used_by_current(session, proxy_id)
        result |= await self._proxy_used_by_bound(session, proxy_id)
        return sorted(result)

    async def _proxy_used_by_bound_only(
        self, session: AsyncSession, proxy_id: str
    ) -> list[str]:
        """Profiles whose ONLY reference is in a running bound version.

        t056 A17: a password change on this proxy sends these profiles a
        runtime event only — no new config version.
        """
        bound = await self._proxy_used_by_bound(session, proxy_id)
        current = await self._proxy_used_by_current(session, proxy_id)
        return sorted(bound - current)

    async def list_proxies(self) -> list[ProxyResponse]:
        async with self._session_maker() as session:
            models = (
                await session.execute(select(ProxyModel))
            ).scalars().all()
            observations = await self._current_observations(session, models)
            return [
                self._to_domain_proxy(
                    m,
                    len(await self._proxy_used_by(session, m.id)),
                    observations[m.id],
                )
                for m in models
            ]

    async def get_proxy(self, proxy_id: str) -> ProxyResponse | None:
        async with self._session_maker() as session:
            m = await session.get(ProxyModel, proxy_id)
            if m is None:
                return None
            return self._to_domain_proxy(
                m,
                len(await self._proxy_used_by(session, proxy_id)),
                await self._current_observation(session, m),
            )

    async def get_proxy_credentials(self, proxy_id: str) -> dict[str, Any] | None:
        """Raw connection + credentials for the Supervisor's Browser sandbox.

        Internal service-plane only: the password lives solely in the proxy
        library and is never returned by the public proxy API or written into
        a config-version snapshot.
        """
        async with self._session_maker() as session:
            m = await session.get(ProxyModel, proxy_id)
            if m is None:
                return None
            return {
                "scheme": m.scheme,
                "host": m.host,
                "port": m.port,
                "username": m.username,
                "password": m.password,
                "credential_revision": m.credential_revision,
            }

    async def get_proxy_endpoint(self, proxy_id: str) -> dict[str, Any] | None:
        """Endpoint + fingerprint for the egress probe runner (t052).

        Service-plane only: includes the password (the probe must present
        it to the upstream proxy).  Never returned by the public API.
        """
        async with self._session_maker() as session:
            m = await session.get(ProxyModel, proxy_id)
            if m is None:
                return None
            endpoint = ProxyEndpoint(
                scheme=m.scheme,  # type: ignore[arg-type]
                host=m.host,
                port=m.port,
                username=m.username,
                password=m.password,
            )
            return {
                "scheme": endpoint.scheme,
                "host": endpoint.host,
                "port": endpoint.port,
                "username": endpoint.username,
                "password": endpoint.password,
                "credential_revision": m.credential_revision,
                "endpoint_fingerprint": endpoint.fingerprint,
                "is_loopback": endpoint.is_loopback,
            }

    async def record_egress_observation(
        self, proxy_id: str, observation: EgressObservation
    ) -> EgressObservation:
        """Append one observation row (history is kept; currency is
        computed on read).  Returns the recorded observation."""
        now = utc_now_iso()
        model = ProxyEgressObservationModel(
            id=str(uuid.uuid4()),
            proxy_id=proxy_id,
            endpoint_fingerprint=observation.endpoint_fingerprint,
            credential_revision=observation.credential_revision,
            perspective=observation.perspective,
            egress_ip=observation.egress_ip,
            country_code=observation.country_code,
            source=observation.source,
            status=observation.status,
            error_code=observation.error_code,
            observed_at=(
                observation.observed_at.isoformat()
                if observation.observed_at
                else now
            ),
            expires_at=(
                observation.expires_at.isoformat()
                if observation.expires_at
                else None
            ),
            created_at=now,
        )
        async with self._session_maker() as session, write_transaction(session):
            session.add(model)
        return observation

    async def get_egress_observations(
        self, proxy_id: str
    ) -> list[EgressObservation]:
        """Observation history, latest first (diagnostics / review)."""
        async with self._session_maker() as session:
            stmt = (
                select(ProxyEgressObservationModel)
                .where(ProxyEgressObservationModel.proxy_id == proxy_id)
                .order_by(
                    ProxyEgressObservationModel.observed_at.desc(),
                    ProxyEgressObservationModel.created_at.desc(),
                )
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._observation_to_domain(r) for r in rows]

    async def proxy_impact(self, proxy_id: str) -> tuple[list[str], list[str]]:
        """Current-config refs and bound-only refs for a proxy (t056 A17).

        Read-only impact lists, used by the service when replaying a
        proxy update: the replay returns these lists without creating a
        new version for anyone.
        """
        async with self._session_maker() as session:
            current = sorted(await self._proxy_used_by_current(session, proxy_id))
            bound_only = await self._proxy_used_by_bound_only(session, proxy_id)
        return current, bound_only

    async def create_proxy(
        self, payload: dict[str, Any], *, operation_id: str | None = None,
        _allow_rebuild: bool = True,
    ) -> ProxyResponse:
        """Create a proxy (t056 A23: replayable via Idempotency-Key, like
        create_profile)."""
        now = utc_now_iso()
        sig_hash = _hash_request("create_proxy", "", payload)
        pid = str(uuid.uuid4())
        audit_recorded = False
        try:
            async with self._session_maker() as session, write_transaction(session):
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                if audit is not None:
                    audit_recorded = True
                    existing = await session.get(ProxyModel, audit.entity_id)
                    if existing is not None:
                        return self._to_domain_proxy(
                            existing,
                            len(await self._proxy_used_by(session, existing.id)),
                            await self._current_observation(session, existing),
                        )
                    pid = audit.entity_id
                model = ProxyModel(
                    id=pid,
                    created_at=now,
                    updated_at=now,
                    **payload,
                )
                session.add(model)
                if operation_id and not audit_recorded:
                    self._record_operation_audit(
                        session,
                        operation_id=operation_id,
                        entity_type="proxy",
                        entity_id=pid,
                        action="create_proxy",
                        sig_hash=sig_hash,
                        now=now,
                        extra={"name": payload.get("name")},
                    )
            return self._to_domain_proxy(model, 0)
        except IntegrityError as exc:
            async with self._session_maker() as session:
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                if audit is not None:
                    existing = await session.get(ProxyModel, audit.entity_id)
                    if existing is not None:
                        return self._to_domain_proxy(
                            existing,
                            len(await self._proxy_used_by(session, existing.id)),
                            await self._current_observation(session, existing),
                        )
                    # The recorded entity was deleted: rebuild it under
                    # the same id — unless the name is now taken by
                    # another entity (t056_code_f002). Re-inserting
                    # would hit the same unique-name constraint again,
                    # so an unconditional retry recurses until
                    # RecursionError and surfaces as 500 instead of a
                    # clean 409 proxy_name_in_use. A rebuild is
                    # attempted at most once.
                    name_taken = (
                        await session.execute(
                            select(ProxyModel.id)
                            .where(ProxyModel.name == payload.get("name"))
                            .limit(1)
                        )
                    ).scalars().first() is not None
                    if name_taken or not _allow_rebuild:
                        raise ValueError("proxy name already exists") from exc
                    return await self.create_proxy(
                        payload, operation_id=operation_id, _allow_rebuild=False
                    )
            raise ValueError("proxy name already exists") from exc

    async def update_proxy(
        self,
        proxy_id: str,
        patch: dict[str, Any],
        password_supplied: bool,
        *,
        operation_id: str | None = None,
    ) -> tuple[ProxyResponse | None, list[str], list[str]]:
        """Update a proxy; when a connection field changes, regenerate a
        config version only for profiles whose CURRENT config references
        it (t056 A17).  Profiles whose only reference is in a running
        bound version get no new version — they are returned separately
        so the caller can notify them with a runtime event instead.

        Returns (proxy, versioned_profile_ids, runtime_only_profile_ids).
        The caller broadcasts SSE for both lists after the commit.

        t056 A23: replayable via Idempotency-Key.  A replay returns the
        current proxy with recomputed impact lists and creates no new
        version for anyone.
        """
        now = utc_now_iso()
        sig_hash = _hash_request(
            "update_proxy",
            proxy_id,
            {"patch": patch, "password_supplied": password_supplied},
        )
        try:
            async with self._session_maker() as session, write_transaction(session):
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                if audit is not None:
                    model = await session.get(ProxyModel, proxy_id)
                    if model is None:
                        return None, [], []
                    return (
                        self._to_domain_proxy(
                            model,
                            len(await self._proxy_used_by(session, proxy_id)),
                            await self._current_observation(session, model),
                        ),
                        sorted(await self._proxy_used_by_current(session, proxy_id)),
                        await self._proxy_used_by_bound_only(session, proxy_id),
                    )
                model = await session.get(ProxyModel, proxy_id)
                if model is None:
                    return None, [], []
                connection_changed = False
                old_password = model.password
                for key, value in patch.items():
                    if key in PROXY_CONNECTION_FIELDS and getattr(model, key) != value:
                        connection_changed = True
                    setattr(model, key, value)
                if password_supplied and patch.get("password") != old_password:
                    model.credential_revision += 1
                    connection_changed = True
                model.updated_at = now

                versioned: list[str] = []
                runtime_only: list[str] = []
                if connection_changed:
                    versioned = sorted(
                        await self._proxy_used_by_current(session, proxy_id)
                    )
                    runtime_only = await self._proxy_used_by_bound_only(
                        session, proxy_id
                    )
                    for pid in versioned:
                        p_model = await session.get(ProfileModel, pid)
                        if p_model is None:
                            continue
                        max_v = (
                            await session.execute(
                                select(func.max(ProfileConfigVersionModel.version)).where(
                                    ProfileConfigVersionModel.profile_id == pid
                                )
                            )
                        ).scalar() or 0
                        new_version = max_v + 1
                        cfg = self._profile_config_from_model(p_model)
                        # The frozen revision is the revision of the proxy
                        # this snapshot's config actually references (t056
                        # A17) — never the proxy being updated, which may
                        # be a different proxy for a bound-only profile.
                        proxy_credential_revision: int | None = None
                        if cfg.proxy_id:
                            proxy_model = await session.get(ProxyModel, cfg.proxy_id)
                            if proxy_model is not None:
                                proxy_credential_revision = (
                                    proxy_model.credential_revision
                                )
                        snapshot = {
                            "config": cfg.model_dump(),
                            "proxy_credential_revision": proxy_credential_revision,
                        }
                        session.add(
                            ProfileConfigVersionModel(
                                id=str(uuid.uuid4()),
                                profile_id=pid,
                                version=new_version,
                                snapshot=json.dumps(snapshot),
                                created_at=now,
                            )
                        )
                        p_model.current_config_version = new_version
                        p_model.updated_at = now
                if operation_id:
                    self._record_operation_audit(
                        session,
                        operation_id=operation_id,
                        entity_type="proxy",
                        entity_id=proxy_id,
                        action="update_proxy",
                        sig_hash=sig_hash,
                        now=now,
                    )
                return (
                    self._to_domain_proxy(
                        model,
                        len(versioned) + len(runtime_only),
                        await self._current_observation(session, model),
                    ),
                    versioned,
                    runtime_only,
                )
        except IntegrityError as exc:
            async with self._session_maker() as session:
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                if audit is not None:
                    model = await session.get(ProxyModel, proxy_id)
                    if model is not None:
                        return (
                            self._to_domain_proxy(
                                model,
                                len(await self._proxy_used_by(session, proxy_id)),
                                await self._current_observation(session, model),
                            ),
                            sorted(
                                await self._proxy_used_by_current(session, proxy_id)
                            ),
                            await self._proxy_used_by_bound_only(session, proxy_id),
                        )
                    return None, [], []
            raise ValueError("proxy name already exists") from exc

    async def delete_proxy(
        self, proxy_id: str, *, operation_id: str | None = None
    ) -> tuple[bool, int]:
        """Return (deleted, used_by_count).  A referenced proxy is refused.

        t056 A23: replayable via Idempotency-Key — a replay returns the
        recorded success, not 404.  The audit row is recorded only when
        the delete actually succeeds.
        """
        now = utc_now_iso()
        sig_hash = _hash_request("delete_proxy", proxy_id, {})
        try:
            async with self._session_maker() as session, write_transaction(session):
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                if audit is not None:
                    return True, 0
                model = await session.get(ProxyModel, proxy_id)
                if model is None:
                    return False, 0
                used_by = await self._proxy_used_by(session, proxy_id)
                if used_by:
                    return False, len(used_by)
                await session.delete(model)
                if operation_id:
                    self._record_operation_audit(
                        session,
                        operation_id=operation_id,
                        entity_type="proxy",
                        entity_id=proxy_id,
                        action="delete_proxy",
                        sig_hash=sig_hash,
                        now=now,
                    )
                return True, 0
        except IntegrityError:
            async with self._session_maker() as session:
                audit = await self._match_operation_audit(
                    session, operation_id, sig_hash
                )
                if audit is not None:
                    return True, 0
            raise

    @staticmethod
    def _profile_config_from_model(m: ProfileModel) -> ProfileConfig:
        return ProfileConfig(
            name=m.name,
            fingerprint_seed=m.fingerprint_seed,
            group_id=m.group_id,
            proxy_id=m.proxy_id,
            timezone=m.timezone,
            locale=m.locale,
            screen_width=m.screen_width,
            screen_height=m.screen_height,
            gpu_family=m.gpu_family,  # type: ignore
            humanize=m.humanize,
            human_preset=m.human_preset,  # type: ignore
            geoip=m.geoip,
            clipboard_sync=m.clipboard_sync,
            auto_launch=m.auto_launch,
            color_scheme=m.color_scheme,  # type: ignore
            fingerprint_platform=m.fingerprint_platform,  # type: ignore
            font_set_id=m.font_set_id,  # type: ignore
            launch_args=json.loads(m.launch_args) if m.launch_args else [],
            extension_paths=json.loads(m.extension_paths) if m.extension_paths else [],
            allow_3p_cookies=m.allow_3p_cookies,
            set_google_default=m.set_google_default,
            capture_preview=m.capture_preview,
            restore_session=m.restore_session,
            transparent_proxy=m.transparent_proxy,
            portable_cookies=m.portable_cookies,
            notes=m.notes,
            sort_order=m.sort_order,
        )
