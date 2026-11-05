"""SQLAlchemy 2.0 ORM models for CBrowser v2."""

from __future__ import annotations

from cbrowser.domain.models import utc_now_iso
from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ProfileGroupModel(Base):
    __tablename__ = "profile_groups"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    color: Mapped[str] = mapped_column(
        String(32), default="slate", nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, nullable=False
    )
    updated_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, onupdate=utc_now_iso, nullable=False
    )


class ProxyModel(Base):
    __tablename__ = "proxies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    scheme: Mapped[str] = mapped_column(String(16), nullable=False)
    host: Mapped[str] = mapped_column(String(512), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_revision: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    region_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, nullable=False
    )
    updated_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, onupdate=utc_now_iso, nullable=False
    )


class ProfileModel(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fingerprint_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    group_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("profile_groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    proxy_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("proxies.id", ondelete="RESTRICT"),
        nullable=True,
    )
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(64), nullable=True)
    screen_width: Mapped[int] = mapped_column(Integer, default=1920, nullable=False)
    screen_height: Mapped[int] = mapped_column(Integer, default=1080, nullable=False)
    gpu_family: Mapped[str] = mapped_column(String(32), default="auto", nullable=False)
    humanize: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    human_preset: Mapped[str] = mapped_column(
        String(32), default="default", nullable=False
    )
    geoip: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    clipboard_sync: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_launch: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    color_scheme: Mapped[str | None] = mapped_column(String(32), nullable=True)
    font_bundle: Mapped[str] = mapped_column(
        String(32), default="none", nullable=False
    )
    launch_args: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    extension_paths: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    allow_3p_cookies: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    set_google_default: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    capture_preview: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    restore_session: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    transparent_proxy: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    portable_cookies: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_data_dir: Mapped[str] = mapped_column(String(1024), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_config_version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    created_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, nullable=False
    )
    updated_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, onupdate=utc_now_iso, nullable=False
    )

    # Relationships are never loaded implicitly: ordinary profile reads load
    # only what their DTO needs; immutable version history and artifact
    # collections are fetched by their dedicated queries. Profile deletion
    # cascades at the database level (FK ON DELETE CASCADE + foreign_keys pragma).
    versions: Mapped[list[ProfileConfigVersionModel]] = relationship(
        "ProfileConfigVersionModel",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="noload",
        passive_deletes=True,
    )
    runtime: Mapped[ProfileRuntimeModel | None] = relationship(
        "ProfileRuntimeModel",
        back_populates="profile",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="noload",
        passive_deletes=True,
    )
    artifacts: Mapped[list[ArtifactModel]] = relationship(
        "ArtifactModel",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="noload",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("idx_profiles_group_id", "group_id"),
        Index("idx_profiles_proxy_id", "proxy_id"),
    )


class ProfileConfigVersionModel(Base):
    __tablename__ = "profile_config_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, nullable=False
    )

    profile: Mapped[ProfileModel] = relationship(
        "ProfileModel", back_populates="versions"
    )

    __table_args__ = (
        UniqueConstraint("profile_id", "version", name="uq_profile_version"),
    )


class ProfileRuntimeModel(Base):
    __tablename__ = "profile_runtimes"

    profile_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    desired_state: Mapped[str] = mapped_column(
        String(32), default="stopped", nullable=False
    )
    observed_state: Mapped[str] = mapped_column(
        String(32), default="stopped", nullable=False
    )
    runtime_instance_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    restart_blocked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    last_exit_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_started_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_stopped_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    browser_product: Mapped[str | None] = mapped_column(String(255), nullable=True)
    browser_user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, onupdate=utc_now_iso, nullable=False
    )

    profile: Mapped[ProfileModel] = relationship(
        "ProfileModel", back_populates="runtime"
    )


class ArtifactModel(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="upload", nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="ready", nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    picker_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    # Durable deletion intent: set before any file is touched so a failed
    # or interrupted delete can be resumed after a restart (A40).
    delete_requested_at: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, nullable=False
    )

    profile: Mapped[ProfileModel] = relationship(
        "ProfileModel", back_populates="artifacts"
    )

    __table_args__ = (
        Index("idx_artifacts_profile_id", "profile_id"),
        Index("idx_artifacts_profile_sha256", "profile_id", "sha256"),
    )


class SettingModel(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, onupdate=utc_now_iso, nullable=False
    )


class RuntimeEventModel(Base):
    __tablename__ = "runtime_events"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    runtime_instance_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), default="exit", nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    payload: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, nullable=False
    )

    __table_args__ = (
        Index("idx_runtime_events_profile", "profile_id"),
        Index("idx_runtime_events_instance", "runtime_instance_id"),
    )


class AuditEventModel(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    details: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, nullable=False
    )


class AdminModel(Base):
    __tablename__ = "admins"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, nullable=False
    )
    updated_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, onupdate=utc_now_iso, nullable=False
    )


class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, nullable=False
    )

    __table_args__ = (Index("idx_sessions_token_hash", "token_hash"),)


class AutomationTokenModel(Base):
    __tablename__ = "automation_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    profile_ids: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, nullable=False
    )
    revoked_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (Index("idx_automation_tokens_token_hash", "token_hash"),)


class ProfileControlModel(Base):
    """Durable human-priority control state, one row per profile (t031).

    Only the API-side control service writes this table (ADR 019: the
    API is the sole business-DB writer). ``generation`` fences stale
    tunnels and control responses; ``agent_reclaim_allowed`` blocks
    silent re-claim after a takeover until an explicit human restore.
    """

    __tablename__ = "profile_controls"

    profile_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    owner: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    agent_instance_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    agent_session_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    handoff_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    handoff_detail: Mapped[str | None] = mapped_column(String(256), nullable=True)
    agent_reclaim_allowed: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    pending_supervisor_close: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    updated_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, nullable=False
    )
