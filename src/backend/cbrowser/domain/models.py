"""Domain models and DTOs for CBrowser v2."""

from __future__ import annotations

import datetime
import random
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def generate_fingerprint_seed() -> int:
    return random.randint(100000, 999999)


DesiredState = Literal["stopped", "running"]
ObservedState = Literal["stopped", "starting", "running", "stopping", "error"]
RuntimeEventType = Literal["exit", "heartbeat", "lifecycle"]


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: str
    message: str
    retryable: bool = False


class ValidationErrorDetail(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ValidationErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: str = "validation_error"
    message: str | None = None
    detail: list[ValidationErrorDetail] = Field(default_factory=list)
    retryable: bool = False


class Tag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str = Field(min_length=1, max_length=64)
    color: str | None = Field(default=None, max_length=32)


class ProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="Default Profile", min_length=1, max_length=255)
    fingerprint_seed: int = Field(default_factory=generate_fingerprint_seed)
    proxy: str | None = Field(default=None, max_length=512)
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=64)
    screen_width: int = Field(default=1920, ge=100, le=10000)
    screen_height: int = Field(default=1080, ge=100, le=10000)
    gpu_family: Literal["auto", "nvidia", "intel"] = "auto"
    humanize: bool = False
    human_preset: Literal["default", "careful"] = "default"
    geoip: bool = True
    clipboard_sync: bool = True
    auto_launch: bool = False
    color_scheme: Literal["light", "dark", "no-preference"] | None = None
    launch_args: list[str] = Field(default_factory=list)
    extension_paths: list[str] = Field(default_factory=list)
    allow_3p_cookies: bool = True
    set_google_default: bool = True
    capture_preview: bool = True
    restore_session: bool = True
    transparent_proxy: bool = False
    portable_cookies: bool = False
    notes: str | None = None
    sort_order: int = 0
    runtime_mode: Literal["docker"] = "docker"
    viewer_mode: Literal["webrtc"] = "webrtc"

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Profile name cannot be blank")
        return v.strip()

    @field_validator("gpu_family", mode="before")
    @classmethod
    def validate_gpu_family(cls, v: Any) -> Any:
        if v is None:
            raise ValueError("gpu_family cannot be null")
        return v


class Profile(BaseModel):
    id: str
    config: ProfileConfig
    tags: list[Tag] = Field(default_factory=list)
    user_data_dir: str
    sort_order: int = 0
    current_config_version: int = 1
    created_at: str
    updated_at: str


class ConfigVersionSnapshot(BaseModel):
    id: str
    profile_id: str
    version: int
    config: dict[str, Any]
    tags: list[Tag] = Field(default_factory=list)
    created_at: str


class ProfileRuntime(BaseModel):
    profile_id: str
    desired_state: DesiredState = "stopped"
    observed_state: ObservedState = "stopped"
    runtime_instance_id: str | None = None
    config_version: int = 1
    failure_count: int = 0
    restart_blocked: bool = False
    last_exit_event_id: str | None = None
    updated_at: str


class RuntimeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$")
    profile_id: str = Field(pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$")
    runtime_instance_id: str = Field(pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$")
    event_type: RuntimeEventType = "exit"
    exit_code: int | None = None
    exit_reason: str | None = None
    config_version: int = Field(default=1, ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)


class Artifact(BaseModel):
    id: str
    profile_id: str
    name: str
    size: int = 0
    kind: str = "upload"
    state: str = "ready"
    content_type: str | None = None
    picker_name: str | None = None
    sha256: str | None = None
    storage_path: str | None = None
    created_at: str


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    profile_id: str
    name: str
    size: int
    kind: Literal["upload", "download"]
    state: Literal["pending", "ready", "failed"]
    content_type: str | None = None
    sha256: str | None = None
    container_path: str | None = None
    created_at: str

    @classmethod
    def from_domain(
        cls, artifact: "Artifact", container_path: str | None
    ) -> "ArtifactResponse":
        return cls(
            id=artifact.id,
            profile_id=artifact.profile_id,
            name=artifact.name,
            size=artifact.size,
            kind=artifact.kind,  # type: ignore[arg-type]
            state=artifact.state,  # type: ignore[arg-type]
            content_type=artifact.content_type,
            sha256=artifact.sha256,
            container_path=container_path,
            created_at=artifact.created_at,
        )


class ArtifactDownloadReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$"
    )
    profile_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$"
    )
    runtime_instance_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$"
    )
    path: str = Field(min_length=1, max_length=4096)
    name: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    content_type: str | None = Field(default=None, max_length=128)


class ArtifactDownloadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "ok"
    outcome: Literal["created", "duplicate", "ignored", "rejected"]
    artifact_id: str | None = None
    event_id: str


class AutomationEndpointResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    cdp_ws_path: str
    supervisor_configured: bool
    runtime_observed_state: str
    runtime_instance_id: str | None = None
    token_header: str = "Authorization: Bearer <cbat_...>"


class Setting(BaseModel):
    key: str
    value: dict[str, Any]
    updated_at: str


class AuditEvent(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    action: str
    actor: str = "system"
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)


# API DTOs
class ProfileCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    fingerprint_seed: int | None = None
    proxy: str | None = Field(default=None, max_length=512)
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=64)
    screen_width: int = Field(default=1920, ge=100, le=10000)
    screen_height: int = Field(default=1080, ge=100, le=10000)
    gpu_family: Literal["auto", "nvidia", "intel"] = "auto"
    humanize: bool = False
    human_preset: Literal["default", "careful"] = "default"
    geoip: bool = True
    clipboard_sync: bool = True
    auto_launch: bool = False
    color_scheme: Literal["light", "dark", "no-preference"] | None = None
    launch_args: list[str] = Field(default_factory=list)
    extension_paths: list[str] = Field(default_factory=list)
    allow_3p_cookies: bool = True
    set_google_default: bool = True
    capture_preview: bool = True
    restore_session: bool = True
    transparent_proxy: bool = False
    portable_cookies: bool = False
    notes: str | None = None
    sort_order: int = 0
    tags: list[Tag] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name cannot be blank")
        return v.strip()


class ProfileDuplicateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    include_browser_state: bool = False
    name: str | None = Field(default=None, min_length=1, max_length=255)


class ProfileResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: bool = False


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    fingerprint_seed: int | None = None
    proxy: str | None = Field(default=None, max_length=512)
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=64)
    screen_width: int | None = Field(default=None, ge=100, le=10000)
    screen_height: int | None = Field(default=None, ge=100, le=10000)
    gpu_family: Literal["auto", "nvidia", "intel"] | None = None
    humanize: bool | None = None
    human_preset: Literal["default", "careful"] | None = None
    geoip: bool | None = None
    clipboard_sync: bool | None = None
    auto_launch: bool | None = None
    color_scheme: Literal["light", "dark", "no-preference"] | None = None
    launch_args: list[str] | None = None
    extension_paths: list[str] | None = None
    allow_3p_cookies: bool | None = None
    set_google_default: bool | None = None
    capture_preview: bool | None = None
    restore_session: bool | None = None
    transparent_proxy: bool | None = None
    portable_cookies: bool | None = None
    notes: str | None = None
    sort_order: int | None = None
    tags: list[Tag] | None = None

    @field_validator("name", mode="before")
    @classmethod
    def reject_null_name(cls, value: object) -> object:
        if value is None:
            raise ValueError("name cannot be null")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None and (not v or not v.strip()):
            raise ValueError("name cannot be blank")
        return v.strip() if v is not None else None

    @field_validator("gpu_family", mode="before")
    @classmethod
    def reject_null_gpu_family(cls, value: object) -> object:
        if value is None:
            raise ValueError("gpu_family cannot be null")
        return value

    @field_validator("screen_width", "screen_height", mode="before")
    @classmethod
    def reject_null_dimensions(cls, value: object) -> object:
        if value is None:
            raise ValueError("dimensions cannot be null")
        return value


class ProfileResponse(BaseModel):
    id: str
    name: str
    fingerprint_seed: int
    proxy: str | None = None
    timezone: str | None = None
    locale: str | None = None
    screen_width: int = 1920
    screen_height: int = 1080
    gpu_family: str = "auto"
    humanize: bool = False
    human_preset: str = "default"
    geoip: bool = True
    clipboard_sync: bool = True
    auto_launch: bool = False
    color_scheme: str | None = None
    launch_args: list[str] = Field(default_factory=list)
    extension_paths: list[str] = Field(default_factory=list)
    allow_3p_cookies: bool = True
    set_google_default: bool = True
    capture_preview: bool = True
    restore_session: bool = True
    transparent_proxy: bool = False
    portable_cookies: bool = False
    notes: str | None = None
    user_data_dir: str
    sort_order: int = 0
    runtime_mode: str = "docker"
    viewer_mode: str = "webrtc"
    tags: list[Tag] = Field(default_factory=list)
    current_config_version: int = 1
    created_at: str
    updated_at: str

    @classmethod
    def from_domain(cls, p: Profile) -> ProfileResponse:
        cfg = p.config
        return cls(
            id=p.id,
            name=cfg.name,
            fingerprint_seed=cfg.fingerprint_seed,
            proxy=cfg.proxy,
            timezone=cfg.timezone,
            locale=cfg.locale,
            screen_width=cfg.screen_width,
            screen_height=cfg.screen_height,
            gpu_family=cfg.gpu_family,
            humanize=cfg.humanize,
            human_preset=cfg.human_preset,
            geoip=cfg.geoip,
            clipboard_sync=cfg.clipboard_sync,
            auto_launch=cfg.auto_launch,
            color_scheme=cfg.color_scheme,
            launch_args=cfg.launch_args,
            extension_paths=cfg.extension_paths,
            allow_3p_cookies=cfg.allow_3p_cookies,
            set_google_default=cfg.set_google_default,
            capture_preview=cfg.capture_preview,
            restore_session=cfg.restore_session,
            transparent_proxy=cfg.transparent_proxy,
            portable_cookies=cfg.portable_cookies,
            notes=cfg.notes,
            user_data_dir=p.user_data_dir,
            sort_order=p.sort_order,
            runtime_mode=cfg.runtime_mode,
            viewer_mode=cfg.viewer_mode,
            tags=p.tags,
            current_config_version=p.current_config_version,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )


class ConfigVersionResponse(BaseModel):
    id: str
    profile_id: str
    version: int
    config: dict[str, Any]
    tags: list[Tag] = Field(default_factory=list)
    created_at: str


class ProfileRuntimeResponse(BaseModel):
    profile_id: str
    desired_state: str
    observed_state: str
    runtime_instance_id: str | None
    config_version: int
    failure_count: int
    restart_blocked: bool
    last_exit_event_id: str | None
    last_coordinator_error: str | None = None
    updated_at: str


class ProfileRuntimeStatusEvent(BaseModel):
    profile_id: str
    desired_state: str
    observed_state: str
    runtime_instance_id: str | None = None
    failure_count: int = 0
    restart_blocked: bool = False
    last_coordinator_error: str | None = None
    updated_at: str


ProfileRuntimeEventData = ProfileRuntimeStatusEvent


class ProfileRuntimeEvent(BaseModel):
    id: str
    event: str = "runtime_state"
    data: ProfileRuntimeStatusEvent


class RuntimeInstanceBindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runtime_instance_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$"
    )
    config_version: int = Field(default=1, ge=1)
    expected_current_instance: str | None = Field(default=None, max_length=128)


class RuntimeObservedReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runtime_instance_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$"
    )
    observed_state: ObservedState
    config_version: int | None = None
    reason: str | None = Field(default=None, max_length=64)


class RuntimeDesiredStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    desired_state: DesiredState


class RuntimeEventReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$"
    )
    profile_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$"
    )
    runtime_instance_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$"
    )
    event_type: RuntimeEventType = "exit"
    exit_code: int | None = None
    exit_reason: str | None = Field(default=None, max_length=128)
    config_version: int = Field(default=1, ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class RuntimeEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = "ok"
    outcome: str
    event_id: str
    profile_id: str
