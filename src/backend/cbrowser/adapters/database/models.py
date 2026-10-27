"""SQLAlchemy 2.0 ORM models for CBrowser v2."""

from __future__ import annotations

import datetime

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


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


class Base(DeclarativeBase):
    pass


class ProfileModel(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fingerprint_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    proxy: Mapped[str | None] = mapped_column(String(512), nullable=True)
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
    runtime_mode: Mapped[str] = mapped_column(
        String(32), default="docker", nullable=False
    )
    viewer_mode: Mapped[str] = mapped_column(
        String(32), default="webrtc", nullable=False
    )
    current_config_version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    created_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, nullable=False
    )
    updated_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, onupdate=utc_now_iso, nullable=False
    )

    tags: Mapped[list[ProfileTagModel]] = relationship(
        "ProfileTagModel",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    versions: Mapped[list[ProfileConfigVersionModel]] = relationship(
        "ProfileConfigVersionModel",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    runtime: Mapped[ProfileRuntimeModel | None] = relationship(
        "ProfileRuntimeModel",
        back_populates="profile",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    artifacts: Mapped[list[ArtifactModel]] = relationship(
        "ArtifactModel",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
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


class ProfileTagModel(Base):
    __tablename__ = "profile_tags"

    profile_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String(64), primary_key=True)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)

    profile: Mapped[ProfileModel] = relationship("ProfileModel", back_populates="tags")


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
    created_at: Mapped[str] = mapped_column(
        String(64), default=utc_now_iso, nullable=False
    )

    profile: Mapped[ProfileModel] = relationship(
        "ProfileModel", back_populates="artifacts"
    )

    __table_args__ = (Index("idx_artifacts_profile_id", "profile_id"),)


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
