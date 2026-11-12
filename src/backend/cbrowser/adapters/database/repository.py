"""Repository implementation for Profile and Runtime operations in SQLite."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from cbrowser.adapters.database.models import (
    AuditEventModel,
    ProfileConfigVersionModel,
    ProfileGroupModel,
    ProfileModel,
    ProfileRuntimeModel,
    ProxyModel,
    RuntimeEventModel,
    SettingModel,
)
from cbrowser.adapters.database.session import write_transaction
from cbrowser.domain.models import (
    ConfigVersionSnapshot,
    GroupResponse,
    Profile,
    ProfileConfig,
    ProfileRuntime,
    ProxyResponse,
    RuntimeEvent,
    AppliedNetworkAccessVersion,
    NetworkAccessConfig,
    NetworkAccessSettingsResponse,
    NetworkApplyOperation,
    NetworkApplyPhase,
    utc_now_iso,
)
from cbrowser.domain.runtime_policy import (
    AUTO_RETRY_DELAYS,
    BLOCK_AFTER_RUNTIME_FAILURES,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class NetworkTransaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(min_length=1, max_length=128)
    target_version: int = Field(ge=1)
    phase: NetworkApplyPhase = NetworkApplyPhase.PENDING
    error_reason: str | None = None
    new_entry_url: str | None = None
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    transaction_phase: str = "pending"
    decision: str = "pending"
    execution_generation: int = 0
    old_applied: dict[str, Any] = Field(default_factory=dict)
    target_applied: dict[str, Any] = Field(default_factory=dict)
    candidate_hash: str = ""
    component_hash: str = ""
    gateway_acked: bool = False
    gateway_generation: int | None = None
    gateway_hash: str = ""
    recovery_complete: bool = True

    def to_operation(self) -> NetworkApplyOperation:
        return NetworkApplyOperation(
            operation_id=self.operation_id,
            target_version=self.target_version,
            phase=self.phase,
            error_reason=self.error_reason,
            new_entry_url=self.new_entry_url,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


def _load_transaction(raw: str) -> NetworkTransaction:
    data = json.loads(raw)
    allowed = set(NetworkTransaction.model_fields)
    return NetworkTransaction.model_validate(
        {key: value for key, value in data.items() if key in allowed}
    )


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
        self._network_transaction_lock = asyncio.Lock()

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

    async def font_set_usage_counts(self) -> dict[str, int]:
        """Count profiles bound to each non-empty font set id (t041 AC-002)."""
        async with self._session_maker() as session:
            stmt = (
                select(ProfileModel.font_set_id, func.count())
                .where(
                    ProfileModel.font_set_id.is_not(None),
                    ProfileModel.font_set_id != "",
                )
                .group_by(ProfileModel.font_set_id)
            )
            result = await session.execute(stmt)
            return {row[0]: row[1] for row in result.all() if row[0]}

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

    async def create_group(
        self, name: str, color: str, sort_order: int
    ) -> GroupResponse:
        now = utc_now_iso()
        model = ProfileGroupModel(
            id=str(uuid.uuid4()),
            name=name,
            color=color,
            sort_order=sort_order,
            created_at=now,
            updated_at=now,
        )
        try:
            async with self._session_maker() as session, write_transaction(session):
                session.add(model)
        except IntegrityError as exc:
            raise ValueError("group name already exists") from exc
        return self._to_domain_group(model)

    async def update_group(
        self, group_id: str, patch: dict[str, Any]
    ) -> GroupResponse | None:
        now = utc_now_iso()
        try:
            async with self._session_maker() as session, write_transaction(session):
                model = await session.get(ProfileGroupModel, group_id)
                if model is None:
                    return None
                for key, value in patch.items():
                    setattr(model, key, value)
                model.updated_at = now
                return self._to_domain_group(model)
        except IntegrityError as exc:
            raise ValueError("group name already exists") from exc

    async def delete_group(self, group_id: str) -> bool:
        async with self._session_maker() as session, write_transaction(session):
            model = await session.get(ProfileGroupModel, group_id)
            if model is None:
                return False
            await session.delete(model)
            return True

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
    def _to_domain_proxy(m: ProxyModel, used_by_count: int) -> ProxyResponse:
        return ProxyResponse(
            id=m.id,
            name=m.name,
            scheme=m.scheme,  # type: ignore
            host=m.host,
            port=m.port,
            username=m.username,
            has_password=bool(m.password),
            credential_revision=m.credential_revision,
            country_code=m.country_code,
            region_label=m.region_label,
            notes=m.notes,
            used_by_count=used_by_count,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    async def _proxy_used_by(
        self, session: AsyncSession, proxy_id: str
    ) -> list[str]:
        """Profiles whose current config OR runtime-bound version reference it."""
        current = (
            await session.execute(
                select(ProfileModel.id).where(ProfileModel.proxy_id == proxy_id)
            )
        ).scalars().all()
        result = set(current)
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
        return sorted(result)

    async def list_proxies(self) -> list[ProxyResponse]:
        async with self._session_maker() as session:
            models = (
                await session.execute(select(ProxyModel))
            ).scalars().all()
            return [
                self._to_domain_proxy(
                    m, len(await self._proxy_used_by(session, m.id))
                )
                for m in models
            ]

    async def get_proxy(self, proxy_id: str) -> ProxyResponse | None:
        async with self._session_maker() as session:
            m = await session.get(ProxyModel, proxy_id)
            if m is None:
                return None
            return self._to_domain_proxy(
                m, len(await self._proxy_used_by(session, proxy_id))
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

    async def create_proxy(self, payload: dict[str, Any]) -> ProxyResponse:
        now = utc_now_iso()
        model = ProxyModel(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            **payload,
        )
        try:
            async with self._session_maker() as session, write_transaction(session):
                session.add(model)
        except IntegrityError as exc:
            raise ValueError("proxy name already exists") from exc
        return self._to_domain_proxy(model, 0)

    async def update_proxy(
        self, proxy_id: str, patch: dict[str, Any], password_supplied: bool
    ) -> tuple[ProxyResponse | None, list[str]]:
        """Update a proxy; when a connection field changes, regenerate a
        config version for every referencing profile in the same transaction.

        Returns (proxy, affected_profile_ids).  The caller broadcasts SSE
        for the affected ids after the commit (AC-006).
        """
        now = utc_now_iso()
        try:
            async with self._session_maker() as session, write_transaction(session):
                model = await session.get(ProxyModel, proxy_id)
                if model is None:
                    return None, []
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

                affected: list[str] = []
                if connection_changed:
                    affected = await self._proxy_used_by(session, proxy_id)
                    for pid in affected:
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
                        snapshot = {
                            "config": cfg.model_dump(),
                            "proxy_credential_revision": model.credential_revision,
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
                return (
                    self._to_domain_proxy(model, len(affected)),
                    affected,
                )
        except IntegrityError as exc:
            raise ValueError("proxy name already exists") from exc

    async def delete_proxy(self, proxy_id: str) -> tuple[bool, int]:
        """Return (deleted, used_by_count).  A referenced proxy is refused."""
        async with self._session_maker() as session, write_transaction(session):
            model = await session.get(ProxyModel, proxy_id)
            if model is None:
                return False, 0
            used_by = await self._proxy_used_by(session, proxy_id)
            if used_by:
                return False, len(used_by)
            await session.delete(model)
            return True, 0

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

    # -------------------------------------------------------------------------
    # Network Access Settings & Apply Operations (t042)
    # -------------------------------------------------------------------------

    KEY_NETWORK_PENDING = "network.pending_config"
    KEY_NETWORK_APPLIED = "network.applied_version"
    KEY_NETWORK_ACTIVE_OP = "network.active_operation"
    KEY_NETWORK_OP_PREFIX = "network.operation."
    KEY_NETWORK_GENERATION = "network.execution_generation"
    KEY_NETWORK_CURRENT_TXN = "network.transaction.current"

    async def get_network_access_settings(
        self, export_dir: Path | None = None
    ) -> NetworkAccessSettingsResponse:
        async with self._session_maker() as session:
            # Pending config
            pending_row = await session.get(SettingModel, self.KEY_NETWORK_PENDING)
            if pending_row:
                pending_config = NetworkAccessConfig.model_validate_json(pending_row.value)
            else:
                pending_config = NetworkAccessConfig(lan_access_enabled=False)

            # Applied version: DB takes precedence; on clean boot fallback to disk exported baseline
            applied_row = await session.get(SettingModel, self.KEY_NETWORK_APPLIED)
            if applied_row:
                applied_version = AppliedNetworkAccessVersion.model_validate_json(applied_row.value)
            else:
                from cbrowser.network_config import (
                    build_applied_network_version,
                    read_applied_network_state,
                )
                file_state = (
                    read_applied_network_state(export_dir) if export_dir else None
                )
                if file_state is not None:
                    applied_version = file_state[0]
                else:
                    applied_version, _ = build_applied_network_version(
                        NetworkAccessConfig(lan_access_enabled=False),
                        version=1,
                    )

            # Active operation
            active_op_row = await session.get(SettingModel, self.KEY_NETWORK_ACTIVE_OP)
            active_op = None
            if active_op_row:
                active_op = _load_transaction(active_op_row.value).to_operation()

            return NetworkAccessSettingsResponse(
                pending_config=pending_config,
                applied_version=applied_version,
                active_operation=active_op,
            )

    async def save_pending_network_config(self, config: NetworkAccessConfig) -> None:
        async with self._session_maker() as session, write_transaction(session):
            row = await session.get(SettingModel, self.KEY_NETWORK_PENDING)
            raw = config.model_dump_json()
            if row:
                row.value = raw
                row.updated_at = utc_now_iso()
            else:
                session.add(
                    SettingModel(
                        key=self.KEY_NETWORK_PENDING,
                        value=raw,
                        updated_at=utc_now_iso(),
                    )
                )

    async def record_applied_network_version(
        self, version: AppliedNetworkAccessVersion
    ) -> None:
        async with self._session_maker() as session, write_transaction(session):
            # 1. Update latest applied version
            row = await session.get(SettingModel, self.KEY_NETWORK_APPLIED)
            raw = version.model_dump_json()
            if row:
                row.value = raw
                row.updated_at = utc_now_iso()
            else:
                session.add(
                    SettingModel(
                        key=self.KEY_NETWORK_APPLIED,
                        value=raw,
                        updated_at=utc_now_iso(),
                    )
                )
            # 2. Store immutable historical record
            hist_key = f"network.version.{version.version}"
            hist_row = await session.get(SettingModel, hist_key)
            if not hist_row:
                session.add(
                    SettingModel(
                        key=hist_key,
                        value=raw,
                        updated_at=utc_now_iso(),
                    )
                )

    async def _read_transaction(
        self, session: AsyncSession, operation_id: str
    ) -> NetworkTransaction | None:
        op_key = f"{self.KEY_NETWORK_OP_PREFIX}{operation_id}"
        row = await session.get(SettingModel, op_key)
        if row is None:
            return None
        return _load_transaction(row.value)

    async def _write_transaction(
        self, session: AsyncSession, txn: NetworkTransaction
    ) -> None:
        raw = txn.model_dump_json()
        op_key = f"{self.KEY_NETWORK_OP_PREFIX}{txn.operation_id}"
        row = await session.get(SettingModel, op_key)
        if row:
            row.value = raw
            row.updated_at = utc_now_iso()
        else:
            session.add(
                SettingModel(key=op_key, value=raw, updated_at=utc_now_iso())
            )

        current = await session.get(SettingModel, self.KEY_NETWORK_CURRENT_TXN)
        if current:
            current.value = txn.operation_id
            current.updated_at = utc_now_iso()
        else:
            session.add(
                SettingModel(
                    key=self.KEY_NETWORK_CURRENT_TXN,
                    value=txn.operation_id,
                    updated_at=utc_now_iso(),
                )
            )

        active = await session.get(SettingModel, self.KEY_NETWORK_ACTIVE_OP)
        keep_active = txn.decision == "pending" or not txn.recovery_complete
        if keep_active:
            if active:
                active.value = raw
                active.updated_at = utc_now_iso()
            else:
                session.add(
                    SettingModel(
                        key=self.KEY_NETWORK_ACTIVE_OP,
                        value=raw,
                        updated_at=utc_now_iso(),
                    )
                )
        elif active:
            await session.delete(active)

    async def _bump_generation(self, session: AsyncSession) -> int:
        row = await session.get(SettingModel, self.KEY_NETWORK_GENERATION)
        try:
            current = int(row.value) if row else 0
        except (TypeError, ValueError):
            current = 0
        generation = current + 1
        if row:
            row.value = str(generation)
            row.updated_at = utc_now_iso()
        else:
            session.add(
                SettingModel(
                    key=self.KEY_NETWORK_GENERATION,
                    value=str(generation),
                    updated_at=utc_now_iso(),
                )
            )
        return generation

    async def _write_applied(
        self, session: AsyncSession, version: AppliedNetworkAccessVersion
    ) -> None:
        raw = version.model_dump_json()
        row = await session.get(SettingModel, self.KEY_NETWORK_APPLIED)
        if row:
            row.value = raw
            row.updated_at = utc_now_iso()
        else:
            session.add(
                SettingModel(
                    key=self.KEY_NETWORK_APPLIED,
                    value=raw,
                    updated_at=utc_now_iso(),
                )
            )
        hist_key = f"network.version.{version.version}"
        hist_row = await session.get(SettingModel, hist_key)
        if not hist_row:
            session.add(
                SettingModel(
                    key=hist_key, value=raw, updated_at=utc_now_iso()
                )
            )

    async def get_execution_generation(self) -> int:
        async with self._session_maker() as session:
            row = await session.get(SettingModel, self.KEY_NETWORK_GENERATION)
            if row is None:
                return 0
            try:
                return int(row.value)
            except (TypeError, ValueError):
                return 0

    async def initialize_network_from_disk(self, export_dir: Path) -> bool:
        from cbrowser.network_config import read_applied_network_state

        async with self._session_maker() as session, write_transaction(session):
            row = await session.get(SettingModel, self.KEY_NETWORK_APPLIED)
            if row is not None:
                # Pre-A35 databases upgraded in place keep their applied
                # version row while the execution generation stays missing or
                # zero. The Gateway baseline generation is applied.version - 1
                # and would reject the next apply as stale, so correct the
                # seed here instead of only seeding on a fresh rebuild. The
                # applied version itself is never touched: the seed only moves
                # up to applied.version, never down.
                try:
                    applied_version = (
                        AppliedNetworkAccessVersion.model_validate_json(row.value)
                    )
                except ValueError:
                    return False
                seed = applied_version.version
                gen_row = await session.get(SettingModel, self.KEY_NETWORK_GENERATION)
                try:
                    current = int(gen_row.value) if gen_row is not None else -1
                except (TypeError, ValueError):
                    current = -1
                if gen_row is not None and current >= seed:
                    return False
                if gen_row is not None:
                    gen_row.value = str(seed)
                    gen_row.updated_at = utc_now_iso()
                else:
                    session.add(
                        SettingModel(
                            key=self.KEY_NETWORK_GENERATION,
                            value=str(seed),
                            updated_at=utc_now_iso(),
                        )
                    )
                return True
            state = read_applied_network_state(export_dir)
            if state is None:
                return False
            await self._write_applied(session, state[0])
            # Seed the execution generation from the rebuilt applied version
            # so the next transaction is not dialed from 0: the Gateway
            # baseline generation is applied.version - 1 and would reject a
            # lower generation as stale.
            gen_row = await session.get(SettingModel, self.KEY_NETWORK_GENERATION)
            seed = str(state[0].version)
            if gen_row:
                gen_row.value = seed
                gen_row.updated_at = utc_now_iso()
            else:
                session.add(
                    SettingModel(
                        key=self.KEY_NETWORK_GENERATION,
                        value=seed,
                        updated_at=utc_now_iso(),
                    )
                )
            return True

    async def begin_network_transaction(
        self,
        *,
        operation: NetworkApplyOperation,
        old_applied: AppliedNetworkAccessVersion,
        target_applied: AppliedNetworkAccessVersion,
        candidate_hash: str,
    ) -> NetworkTransaction:
        async with (
            self._network_transaction_lock,
            self._session_maker() as session,
            write_transaction(session),
        ):
            applied_row = await session.get(SettingModel, self.KEY_NETWORK_APPLIED)
            if applied_row is not None:
                try:
                    current_applied = (
                        AppliedNetworkAccessVersion.model_validate_json(
                            applied_row.value
                        )
                    )
                except ValueError:
                    raise RuntimeError(
                        "Applied network version is unreadable"
                    ) from None
                # TOCTOU: version alone is not enough — two concurrent readers
                # can mint the same target version with different configs.
                # Fence on version + config + bind_host + content hash.
                if (
                    current_applied.version != old_applied.version
                    or current_applied.config != old_applied.config
                    or current_applied.bind_host != old_applied.bind_host
                    or current_applied.caddyfile_sha256
                    != old_applied.caddyfile_sha256
                ):
                    raise RuntimeError(
                        "Stale applied network version: expected version "
                        f"{old_applied.version}, found version "
                        f"{current_applied.version}"
                    )
            active_row = await session.get(SettingModel, self.KEY_NETWORK_ACTIVE_OP)
            if active_row is not None:
                existing = _load_transaction(active_row.value)
                if existing.decision == "pending" or not existing.recovery_complete:
                    raise RuntimeError("Apply operation already in progress")
            current_row = await session.get(
                SettingModel, self.KEY_NETWORK_CURRENT_TXN
            )
            if current_row is not None:
                previous = await self._read_transaction(
                    session, current_row.value
                )
                if previous is not None and not previous.recovery_complete:
                    raise RuntimeError(
                        "Apply operation already in progress: recovery incomplete"
                    )
            generation = await self._bump_generation(session)
            txn = NetworkTransaction(
                operation_id=operation.operation_id,
                target_version=operation.target_version,
                phase=operation.phase,
                new_entry_url=operation.new_entry_url,
                created_at=operation.created_at,
                updated_at=operation.updated_at,
                transaction_phase="prepared",
                decision="pending",
                execution_generation=generation,
                old_applied=old_applied.model_dump(),
                target_applied=target_applied.model_dump(),
                candidate_hash=candidate_hash,
            )
            await self._write_transaction(session, txn)
            return txn

    async def get_network_transaction(
        self, operation_id: str
    ) -> NetworkTransaction | None:
        async with self._session_maker() as session:
            return await self._read_transaction(session, operation_id)

    async def get_current_network_transaction(self) -> NetworkTransaction | None:
        async with self._session_maker() as session:
            row = await session.get(SettingModel, self.KEY_NETWORK_CURRENT_TXN)
            if row is None:
                return None
            return await self._read_transaction(session, row.value)

    async def advance_network_transaction(
        self, operation_id: str, **updates: Any
    ) -> NetworkTransaction:
        protected = {
            "decision",
            "operation_id",
            "execution_generation",
            "old_applied",
            "target_applied",
            "created_at",
        }
        async with self._session_maker() as session, write_transaction(session):
            txn = await self._read_transaction(session, operation_id)
            if txn is None:
                raise ValueError(f"Network transaction {operation_id} not found")
            if txn.decision != "pending":
                raise RuntimeError("Network transaction already has a final decision")
            for key, value in updates.items():
                if key not in NetworkTransaction.model_fields or key in protected:
                    raise ValueError(f"Invalid transaction update: {key}")
                setattr(txn, key, value)
            txn.updated_at = utc_now_iso()
            await self._write_transaction(session, txn)
            return txn

    async def commit_network_transaction(
        self,
        *,
        operation_id: str,
        execution_generation: int,
        gateway_generation: int,
        gateway_hash: str,
    ) -> NetworkTransaction:
        async with self._session_maker() as session, write_transaction(session):
            txn = await self._read_transaction(session, operation_id)
            if txn is None:
                raise ValueError(f"Network transaction {operation_id} not found")
            if txn.decision == "commit":
                if (
                    txn.execution_generation == execution_generation
                    and txn.gateway_hash == gateway_hash
                ):
                    return txn
                raise RuntimeError("Commit replay with different generation")
            if txn.decision != "pending":
                raise RuntimeError("Aborted network transaction cannot be committed")
            if txn.execution_generation != execution_generation:
                raise RuntimeError("Stale execution generation")
            if (
                not txn.gateway_acked
                or txn.gateway_generation != gateway_generation
                or txn.gateway_hash != gateway_hash
                or gateway_hash != txn.candidate_hash
            ):
                raise RuntimeError("Gateway ACK not verifiable")
            await self._write_applied(
                session, AppliedNetworkAccessVersion.model_validate(txn.target_applied)
            )
            txn.decision = "commit"
            txn.transaction_phase = "committed"
            txn.phase = NetworkApplyPhase.COMPLETED
            txn.updated_at = utc_now_iso()
            await self._write_transaction(session, txn)
            return txn

    async def abort_network_transaction(
        self,
        *,
        operation_id: str,
        execution_generation: int,
        reason: str,
        recovery_complete: bool,
    ) -> NetworkTransaction:
        async with self._session_maker() as session, write_transaction(session):
            txn = await self._read_transaction(session, operation_id)
            if txn is None:
                raise ValueError(f"Network transaction {operation_id} not found")
            if txn.decision == "commit":
                raise RuntimeError("Committed network transaction cannot be aborted")
            if txn.decision == "abort":
                if txn.recovery_complete != recovery_complete:
                    txn.recovery_complete = recovery_complete
                    txn.transaction_phase = (
                        "aborted" if recovery_complete else "aborting"
                    )
                    txn.updated_at = utc_now_iso()
                    await self._write_transaction(session, txn)
                return txn
            if txn.execution_generation != execution_generation:
                raise RuntimeError("Stale execution generation")
            txn.execution_generation = await self._bump_generation(session)
            txn.decision = "abort"
            txn.transaction_phase = "aborted" if recovery_complete else "aborting"
            txn.recovery_complete = recovery_complete
            txn.error_reason = reason
            txn.phase = NetworkApplyPhase.FAILED
            txn.updated_at = utc_now_iso()
            if txn.old_applied:
                await self._write_applied(
                    session,
                    AppliedNetworkAccessVersion.model_validate(txn.old_applied),
                )
            await self._write_transaction(session, txn)
            return txn

    async def save_network_operation(self, op: NetworkApplyOperation) -> None:
        async with self._session_maker() as session, write_transaction(session):
            txn = await self._read_transaction(session, op.operation_id)
            if txn is None:
                txn = NetworkTransaction(
                    operation_id=op.operation_id,
                    target_version=op.target_version,
                    created_at=op.created_at,
                    updated_at=op.updated_at,
                )
            txn.phase = op.phase
            txn.error_reason = op.error_reason
            txn.new_entry_url = op.new_entry_url
            txn.updated_at = op.updated_at
            if op.phase in (
                NetworkApplyPhase.COMPLETED,
                NetworkApplyPhase.FAILED,
            ) and txn.decision == "pending":
                txn.decision = (
                    "commit" if op.phase == NetworkApplyPhase.COMPLETED else "abort"
                )
                txn.transaction_phase = (
                    "committed" if op.phase == NetworkApplyPhase.COMPLETED else "aborted"
                )
            await self._write_transaction(session, txn)

    async def get_active_network_operation(self) -> NetworkApplyOperation | None:
        async with self._session_maker() as session:
            row = await session.get(SettingModel, self.KEY_NETWORK_ACTIVE_OP)
            if not row:
                return None
            return _load_transaction(row.value).to_operation()

    async def get_network_operation(
        self, operation_id: str
    ) -> NetworkApplyOperation | None:
        async with self._session_maker() as session:
            txn = await self._read_transaction(session, operation_id)
            if txn is None:
                return None
            return txn.to_operation()
