"""Repository implementation for Profile and Runtime operations in SQLite."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from cbrowser.adapters.database.models import (
    AuditEventModel,
    ProfileConfigVersionModel,
    ProfileModel,
    ProfileRuntimeModel,
    ProfileTagModel,
    RuntimeEventModel,
)
from cbrowser.adapters.database.session import write_transaction
from cbrowser.domain.models import (
    ConfigVersionSnapshot,
    Profile,
    ProfileConfig,
    ProfileRuntime,
    RuntimeEvent,
    Tag,
    utc_now_iso,
)
from cbrowser.domain.runtime_policy import BLOCK_AFTER_RUNTIME_FAILURES
from sqlalchemy import delete, func, select
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


class ProfileRepository:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self._session_maker = session_maker

    async def create_profile(
        self,
        config: ProfileConfig,
        tags: list[Tag] | None = None,
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
        tag_list = tags or []
        fallback_payload = {
            "config": config.model_dump(),
            "tags": [t.model_dump() for t in tag_list],
        }
        sig_hash = _hash_request(
            "create_profile",
            "",
            req_payload if req_payload is not None else fallback_payload,
        )

        try:
            async with self._session_maker() as session, write_transaction(session):
                if operation_id:
                    existing_audit = await session.get(AuditEventModel, operation_id)
                    if existing_audit:
                        audit_details = json.loads(existing_audit.details)
                        if audit_details.get("sig_hash") != sig_hash:
                            raise IdempotencyConflictError(
                                f"Operation ID {operation_id} reused with "
                                "different request payload"
                            )
                        existing = await session.get(
                            ProfileModel, existing_audit.entity_id
                        )
                        if existing:
                            return self._to_domain_profile(existing)

                p_model = ProfileModel(
                    id=pid,
                    name=config.name,
                    fingerprint_seed=config.fingerprint_seed,
                    proxy=config.proxy,
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
                    runtime_mode=config.runtime_mode,
                    viewer_mode=config.viewer_mode,
                    current_config_version=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(p_model)

                for t in tag_list:
                    session.add(
                        ProfileTagModel(
                            profile_id=pid,
                            tag=t.tag,
                            color=t.color,
                        )
                    )

                snapshot_data = {
                    "config": config.model_dump(),
                    "tags": [t.model_dump() for t in tag_list],
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
                    updated_at=now,
                )
                session.add(rt_model)

                if operation_id:
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
            if operation_id:
                async with self._session_maker() as session:
                    existing_audit = await session.get(AuditEventModel, operation_id)
                    if existing_audit:
                        audit_details = json.loads(existing_audit.details)
                        if audit_details.get("sig_hash") != sig_hash:
                            raise IdempotencyConflictError(
                                f"Operation ID {operation_id} reused with "
                                "different request payload"
                            )
                        existing = await session.get(
                            ProfileModel, existing_audit.entity_id
                        )
                        if existing:
                            return self._to_domain_profile(existing)
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
            stmt = select(ProfileModel).where(ProfileModel.id == profile_id)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
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

    async def update_profile(
        self,
        profile_id: str,
        patch_data: dict[str, Any] | ProfileConfig,
        tags: list[Tag] | None = None,
        *,
        operation_id: str | None = None,
        audit_action: str = "update_profile",
    ) -> Profile | None:
        """Atomically merge supplied patch fields into latest profile state.

        Performs update under write_transaction.
        """
        if isinstance(patch_data, ProfileConfig):
            patch_dict = patch_data.model_dump()
        else:
            patch_dict = dict(patch_data)

        tag_list = tags if tags is not None else None
        sig_hash = _hash_request(
            audit_action,
            profile_id,
            {
                "patch": patch_dict,
                "tags": [t.model_dump() for t in tag_list]
                if tag_list is not None
                else None,
            },
        )
        now = utc_now_iso()

        try:
            async with self._session_maker() as session, write_transaction(session):
                if operation_id:
                    existing_audit = await session.get(AuditEventModel, operation_id)
                    if existing_audit:
                        audit_details = json.loads(existing_audit.details)
                        if audit_details.get("sig_hash") != sig_hash:
                            raise IdempotencyConflictError(
                                f"Operation ID {operation_id} reused with "
                                "different request payload"
                            )
                        existing = await session.get(ProfileModel, profile_id)
                        if existing:
                            return self._to_domain_profile(existing)

                p_model = await session.get(ProfileModel, profile_id)
                if not p_model:
                    return None

                # Read fresh current config from database row
                current_dict = {
                    "name": p_model.name,
                    "fingerprint_seed": p_model.fingerprint_seed,
                    "proxy": p_model.proxy,
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
                    "runtime_mode": p_model.runtime_mode,
                    "viewer_mode": p_model.viewer_mode,
                }

                # Merge ONLY the supplied patch fields
                current_dict.update(patch_dict)
                merged_cfg = ProfileConfig(**current_dict)

                # Compute latest version atomically
                max_v_stmt = select(func.max(ProfileConfigVersionModel.version)).where(
                    ProfileConfigVersionModel.profile_id == profile_id
                )
                max_v = (await session.execute(max_v_stmt)).scalar() or 0
                new_version = max_v + 1

                # Update model fields
                p_model.name = merged_cfg.name
                p_model.fingerprint_seed = merged_cfg.fingerprint_seed
                p_model.proxy = merged_cfg.proxy
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
                p_model.launch_args = json.dumps(merged_cfg.launch_args)
                p_model.extension_paths = json.dumps(merged_cfg.extension_paths)
                p_model.allow_3p_cookies = merged_cfg.allow_3p_cookies
                p_model.set_google_default = merged_cfg.set_google_default
                p_model.capture_preview = merged_cfg.capture_preview
                p_model.restore_session = merged_cfg.restore_session
                p_model.transparent_proxy = merged_cfg.transparent_proxy
                p_model.portable_cookies = merged_cfg.portable_cookies
                p_model.notes = merged_cfg.notes
                p_model.sort_order = merged_cfg.sort_order
                p_model.current_config_version = new_version
                p_model.updated_at = now

                # Tags handling
                if tags is not None:
                    await session.execute(
                        delete(ProfileTagModel).where(
                            ProfileTagModel.profile_id == profile_id
                        )
                    )
                    for t in tags:
                        session.add(
                            ProfileTagModel(
                                profile_id=profile_id, tag=t.tag, color=t.color
                            )
                        )
                    active_tags = tags
                else:
                    active_tags = [Tag(tag=t.tag, color=t.color) for t in p_model.tags]

                # Snapshot includes tags
                snapshot_data = {
                    "config": merged_cfg.model_dump(),
                    "tags": [t.model_dump() for t in active_tags],
                }
                v_model = ProfileConfigVersionModel(
                    id=str(uuid.uuid4()),
                    profile_id=profile_id,
                    version=new_version,
                    snapshot=json.dumps(snapshot_data),
                    created_at=now,
                )
                session.add(v_model)

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
            if operation_id:
                async with self._session_maker() as session:
                    existing_audit = await session.get(AuditEventModel, operation_id)
                    if existing_audit:
                        audit_details = json.loads(existing_audit.details)
                        if audit_details.get("sig_hash") != sig_hash:
                            raise IdempotencyConflictError(
                                f"Operation ID {operation_id} reused with "
                                "different request payload"
                            )
                        existing = await session.get(ProfileModel, profile_id)
                        if existing:
                            return self._to_domain_profile(existing)
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
            return self._to_domain_runtime(m)

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
                return self._to_domain_runtime(m)

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

    async def report_observed_state(
        self,
        profile_id: str,
        runtime_instance_id: str,
        observed_state: str,
        config_version: int | None = None,
        reason: str | None = None,
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
            return self._to_domain_runtime(m)

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
                existing_audit = await session.get(AuditEventModel, operation_id)
                if existing_audit:
                    audit_details = json.loads(existing_audit.details)
                    if audit_details.get("sig_hash") != sig_hash:
                        raise IdempotencyConflictError(
                            "Operation ID reused with different request payload"
                        )
                    # Idempotent replay: return current state without resetting failures
                    return self._to_domain_runtime(m)

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

            # Fresh manual user intent
            m.desired_state = desired_state
            if desired_state == "running":
                m.failure_count = 0
                m.restart_blocked = False
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

    @staticmethod
    def _to_domain_runtime(m: ProfileRuntimeModel) -> ProfileRuntime:
        return ProfileRuntime(
            profile_id=m.profile_id,
            desired_state=m.desired_state,  # type: ignore
            observed_state=m.observed_state,  # type: ignore
            runtime_instance_id=m.runtime_instance_id,
            config_version=m.config_version,
            failure_count=m.failure_count,
            restart_blocked=m.restart_blocked,
            last_exit_event_id=m.last_exit_event_id,
            updated_at=m.updated_at,
        )

    @staticmethod
    def _to_domain_snapshot(m: ProfileConfigVersionModel) -> ConfigVersionSnapshot:
        parsed = json.loads(m.snapshot)
        if isinstance(parsed, dict) and "config" in parsed:
            cfg = parsed["config"]
            tags = [Tag(**t) for t in parsed.get("tags", [])]
        else:
            cfg = parsed
            tags = []
        return ConfigVersionSnapshot(
            id=m.id,
            profile_id=m.profile_id,
            version=m.version,
            config=cfg,
            tags=tags,
            created_at=m.created_at,
        )

    @staticmethod
    def _to_domain_profile(m: ProfileModel) -> Profile:
        cfg = ProfileConfig(
            name=m.name,
            fingerprint_seed=m.fingerprint_seed,
            proxy=m.proxy,
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
            runtime_mode="docker",
            viewer_mode="webrtc",
        )
        tags = [Tag(tag=t.tag, color=t.color) for t in m.tags]
        return Profile(
            id=m.id,
            config=cfg,
            tags=tags,
            user_data_dir=m.user_data_dir,
            sort_order=m.sort_order,
            current_config_version=m.current_config_version,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
