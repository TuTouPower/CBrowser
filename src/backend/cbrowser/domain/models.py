"""Domain models and DTOs for CBrowser."""

from __future__ import annotations

import datetime
from enum import Enum
import random
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cbrowser.domain.profile_locale import validate_locale, validate_timezone
from cbrowser.launch_args import filter_launch_args, validate_launch_args


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def generate_fingerprint_seed() -> int:
    return random.randint(100000, 999999)


DesiredState = Literal["stopped", "running"]
ObservedState = Literal["stopped", "starting", "running", "stopping", "error"]
RuntimeEventType = Literal["exit", "heartbeat", "lifecycle"]
FingerprintPlatform = Literal["windows", "macos"]
ProfileLocale = Literal["zh-CN", "en-US"]


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


GROUP_COLORS = Literal[
    "slate", "blue", "teal", "green", "amber", "orange", "red", "violet"
]
PROXY_SCHEMES = Literal["http", "https", "socks5"]


class GroupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    color: GROUP_COLORS
    sort_order: int = 0
    created_at: str
    updated_at: str


class GroupCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64)
    color: GROUP_COLORS = "slate"
    sort_order: int = 0


class GroupUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=64)
    color: GROUP_COLORS | None = None
    sort_order: int | None = None


class GroupReorderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordered_ids: list[str]


class ProxyResponse(BaseModel):
    """Public proxy view (t052).

    ``country_code`` / ``egress_ip`` / ``observation_status`` are read-only
    observations: they come from the current valid egress observation for
    the proxy's present endpoint fingerprint and credential revision, never
    from a stored writable field.  ``proxy_url`` is the redacted link (no
    password, ever); the password is never present in any response.
    """

    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    scheme: PROXY_SCHEMES
    host: str
    port: int
    username: str | None = None
    has_password: bool = False
    credential_revision: int = 1
    proxy_url: str
    country_code: str | None = None
    egress_ip: str | None = None
    observation_status: Literal["unknown", "pending", "ok", "failed"] = "unknown"
    observed_at: str | None = None
    region_label: str | None = None
    notes: str | None = None
    used_by_count: int = 0
    created_at: str
    updated_at: str


class ProxyCreateRequest(BaseModel):
    """Link-only entry (t052): the proxy link is the single source of
    truth for the endpoint; ``name`` defaults to ``host:port``."""

    model_config = ConfigDict(extra="forbid")
    proxy_url: str = Field(min_length=1, max_length=2048)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    region_label: str | None = Field(default=None, max_length=255)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_proxy_link(self) -> ProxyCreateRequest:
        from cbrowser.domain.proxy_endpoint import ProxyLinkError, parse_proxy_link

        try:
            parse_proxy_link(self.proxy_url)
        except ProxyLinkError as exc:
            raise ValueError(f"invalid proxy link: {exc.code}") from None
        return self

    def parsed_endpoint(self) -> ProxyEndpoint:
        from cbrowser.domain.proxy_endpoint import parse_proxy_link

        return parse_proxy_link(self.proxy_url)

    def resolved_name(self) -> str:
        if self.name is not None and self.name.strip():
            return self.name.strip()
        return self.parsed_endpoint().display_name()


class ProxyUpdateRequest(BaseModel):
    """PATCH semantics (t052): ``proxy_url`` omitted = endpoint unchanged;
    supplied = endpoint (including password) replaced wholesale.  All
    other fields are optional; ``name``/``region_label``/``notes`` may be
    set to null to clear."""

    model_config = ConfigDict(extra="forbid")
    proxy_url: str | None = Field(default=None, min_length=1, max_length=2048)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    region_label: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_proxy_link(self) -> ProxyUpdateRequest:
        if self.proxy_url is None:
            return self
        from cbrowser.domain.proxy_endpoint import ProxyLinkError, parse_proxy_link

        try:
            parse_proxy_link(self.proxy_url)
        except ProxyLinkError as exc:
            raise ValueError(f"invalid proxy link: {exc.code}") from None
        return self

    def endpoint_was_supplied(self) -> bool:
        return "proxy_url" in self.model_fields_set

    def parsed_endpoint(self) -> ProxyEndpoint:
        from cbrowser.domain.proxy_endpoint import parse_proxy_link

        if self.proxy_url is None:
            raise ValueError("proxy_url was not supplied")
        return parse_proxy_link(self.proxy_url)


class ProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="Default Profile", min_length=1, max_length=255)
    fingerprint_seed: int = Field(default_factory=generate_fingerprint_seed)
    group_id: str | None = None
    proxy_id: str | None = None
    timezone: str | None = Field(default=None, max_length=64)
    locale: ProfileLocale | None = Field(default=None, max_length=64)
    screen_width: int = Field(default=1920, ge=100, le=10000)
    screen_height: int = Field(default=1080, ge=100, le=10000)
    gpu_family: Literal["auto", "nvidia", "intel"] = "auto"
    humanize: bool = True
    human_preset: Literal["default", "careful"] = "default"
    geoip: bool = True
    clipboard_sync: bool = True
    auto_launch: bool = False
    color_scheme: Literal["light", "dark", "no-preference"] | None = None
    fingerprint_platform: FingerprintPlatform = "windows"
    font_set_id: str | None = None
    launch_args: list[str] = Field(default_factory=list)
    extension_paths: list[str] = Field(default_factory=list)
    allow_3p_cookies: bool = True
    set_google_default: bool = True
    capture_preview: bool = True
    restore_session: bool = True
    transparent_proxy: bool = False
    portable_cookies: bool = True
    notes: str | None = None
    sort_order: int = 0

    @field_validator("timezone")
    @classmethod
    def validate_timezone_value(cls, v: str | None) -> str | None:
        return validate_timezone(v)

    @field_validator("locale")
    @classmethod
    def validate_locale_value(cls, v: str | None) -> str | None:
        return validate_locale(v)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Profile name cannot be blank")
        return v.strip()

    @field_validator("launch_args", "extension_paths", mode="before")
    @classmethod
    def coerce_null_lists(cls, v: Any) -> Any:
        # PATCH tri-state: an explicit null list clears the stored value.
        return [] if v is None else v

    @field_validator("launch_args")
    @classmethod
    def normalize_launch_arguments(cls, v: list[str]) -> list[str]:
        return filter_launch_args(v)

    @field_validator("gpu_family", mode="before")
    @classmethod
    def validate_gpu_family(cls, v: Any) -> Any:
        if v is None:
            raise ValueError("gpu_family cannot be null")
        return v


class Profile(BaseModel):
    id: str
    display_number: int = 1
    config: ProfileConfig
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
    proxy_credential_revision: int | None = None
    created_at: str


class ProfileRuntime(BaseModel):
    profile_id: str
    display_number: int = 1
    desired_state: DesiredState = "stopped"
    observed_state: ObservedState = "stopped"
    runtime_instance_id: str | None = None
    config_version: int = 1
    failure_count: int = 0
    restart_blocked: bool = False
    last_exit_event_id: str | None = None
    last_started_at: str | None = None
    last_stopped_at: str | None = None
    browser_product: str | None = None
    browser_user_agent: str | None = None
    backoff_started_at: str | None = None
    next_retry_at: str | None = None
    preview_captured_at: str | None = None
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
    delete_requested_at: str | None = None
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

    @field_validator("launch_args")
    @classmethod
    def validate_new_launch_arguments(cls, v: list[str]) -> list[str]:
        return validate_launch_args(v)

    name: str = Field(min_length=1, max_length=255)
    fingerprint_seed: int | None = None
    group_id: str | None = None
    proxy_id: str | None = None
    timezone: str | None = Field(default=None, max_length=64)
    locale: ProfileLocale | None = Field(default="en-US", max_length=64)
    screen_width: int = Field(default=1920, ge=100, le=10000)
    screen_height: int = Field(default=1080, ge=100, le=10000)
    gpu_family: Literal["auto", "nvidia", "intel"] = "auto"
    humanize: bool = True
    human_preset: Literal["default", "careful"] = "default"
    geoip: bool = True
    clipboard_sync: bool = True
    auto_launch: bool = False
    color_scheme: Literal["light", "dark", "no-preference"] | None = None
    fingerprint_platform: FingerprintPlatform = "windows"
    font_set_id: str | None = None
    launch_args: list[str] = Field(default_factory=list)
    extension_paths: list[str] = Field(default_factory=list)
    allow_3p_cookies: bool = True
    set_google_default: bool = True
    capture_preview: bool = True
    restore_session: bool = True
    transparent_proxy: bool = False
    portable_cookies: bool = True
    notes: str | None = None
    sort_order: int = 0

    @field_validator("timezone")
    @classmethod
    def validate_timezone_value(cls, v: str | None) -> str | None:
        return validate_timezone(v)

    @field_validator("locale")
    @classmethod
    def validate_locale_value(cls, v: str | None) -> str | None:
        return validate_locale(v)

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

    @field_validator("launch_args")
    @classmethod
    def validate_updated_launch_arguments(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else validate_launch_args(v)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    fingerprint_seed: int | None = None
    group_id: str | None = None
    proxy_id: str | None = None
    timezone: str | None = Field(default=None, max_length=64)
    locale: ProfileLocale | None = Field(default=None, max_length=64)
    screen_width: int | None = Field(default=None, ge=100, le=10000)
    screen_height: int | None = Field(default=None, ge=100, le=10000)
    gpu_family: Literal["auto", "nvidia", "intel"] | None = None
    humanize: bool | None = None
    human_preset: Literal["default", "careful"] | None = None
    geoip: bool | None = None
    clipboard_sync: bool | None = None
    auto_launch: bool | None = None
    color_scheme: Literal["light", "dark", "no-preference"] | None = None
    fingerprint_platform: FingerprintPlatform | None = None
    font_set_id: str | None = None
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

    @field_validator("timezone")
    @classmethod
    def validate_timezone_value(cls, v: str | None) -> str | None:
        return validate_timezone(v)

    @field_validator("locale")
    @classmethod
    def validate_locale_value(cls, v: str | None) -> str | None:
        return validate_locale(v)


class ProfileResponse(BaseModel):
    id: str
    display_number: int
    name: str
    fingerprint_seed: int
    group_id: str | None = None
    proxy_id: str | None = None
    timezone: str | None = None
    locale: ProfileLocale | None = None
    screen_width: int = 1920
    screen_height: int = 1080
    gpu_family: str = "auto"
    humanize: bool = True
    human_preset: str = "default"
    geoip: bool = True
    clipboard_sync: bool = True
    auto_launch: bool = False
    color_scheme: str | None = None
    fingerprint_platform: str = "windows"
    font_set_id: str | None = None
    launch_args: list[str] = Field(default_factory=list)
    extension_paths: list[str] = Field(default_factory=list)
    allow_3p_cookies: bool = True
    set_google_default: bool = True
    capture_preview: bool = True
    restore_session: bool = True
    transparent_proxy: bool = False
    portable_cookies: bool = True
    notes: str | None = None
    user_data_dir: str
    sort_order: int = 0
    current_config_version: int = 1
    created_at: str
    updated_at: str

    @classmethod
    def from_domain(cls, p: Profile) -> ProfileResponse:
        cfg = p.config
        return cls(
            id=p.id,
            display_number=p.display_number,
            name=cfg.name,
            fingerprint_seed=cfg.fingerprint_seed,
            group_id=cfg.group_id,
            proxy_id=cfg.proxy_id,
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
            fingerprint_platform=cfg.fingerprint_platform,
            font_set_id=cfg.font_set_id,
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
            current_config_version=p.current_config_version,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )


class ConfigVersionResponse(BaseModel):
    id: str
    profile_id: str
    version: int
    config: dict[str, Any]
    created_at: str


class SearchDefaultsStatusData(BaseModel):
    """API view of the runtime agent's search-defaults outcome (t022 A55).

    Mirrors the runtime agent protocol model; kept independent of browser
    readiness: a failed initialization is reported here, never as a
    runtime failure.
    """

    model_config = ConfigDict(extra="forbid")

    state: Literal["applied", "failed", "disabled", "pending"]
    error_kind: str | None = Field(default=None, max_length=64)
    runtime_instance_id: str
    request_id: str | None = Field(default=None, max_length=128)
    updated_at: str


class TransportObservationData(BaseModel):
    """API view of the Supervisor's layered transport observation (t026).

    Mirrors the Supervisor control protocol model. Held in memory only:
    after an API restart the value is ``unknown`` until the Supervisor
    reports again, never a stale persisted copy.
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    runtime_instance_id: str | None = None
    browser_state: Literal["running", "stopped", "missing", "error", "unknown"] = (
        "unknown"
    )
    stream_state: Literal["running", "stopped", "missing", "error", "unknown"] = (
        "unknown"
    )
    transport_state: Literal["ready", "recovering", "failed", "unknown"] = "unknown"
    protocol_version: str | None = Field(default=None, max_length=16)
    selkies_version: str | None = Field(default=None, max_length=64)
    agent_build_id: str | None = Field(default=None, max_length=64)
    gateway_build_id: str | None = Field(default=None, max_length=64)
    config_version: int | None = None
    gateway_endpoint: str | None = Field(default=None, max_length=64)
    last_attached_at: str | None = None
    last_registered_at: str | None = None
    last_error: str | None = Field(default=None, max_length=256)
    last_error_at: str | None = None
    rejection_code: str | None = Field(default=None, max_length=64)


class ProfileControlStateData(BaseModel):
    """Human-priority control state for one profile (t031, ADR 019).

    ``owner`` is ``user`` by default and after every restart, crash,
    identity failure, or takeover; ``agent`` only while an explicitly
    claimed agent session holds control. ``generation`` increases on
    every ownership change and fences stale tunnel messages, control
    responses, and SSE snapshots. ``agent_reclaim_allowed`` is cleared
    by a takeover and only restored by an explicit human restore or a
    clean agent finish, so a taken-over agent cannot silently re-claim
    control through a fresh tunnel handshake.
    """

    profile_id: str
    owner: Literal["user", "agent"] = "user"
    generation: int = 0
    agent_instance_id: str | None = None
    agent_session_id: str | None = None
    handoff_reason: str | None = None
    handoff_detail: str | None = Field(default=None, max_length=256)
    agent_reclaim_allowed: bool = True
    pending_supervisor_close: bool = False
    updated_at: str


ControlHandoffReason = Literal[
    "human_input",
    "cli_handoff",
    "permission",
    "captcha",
    "two_fa",
    "agent_finish",
    "supervisor_restart",
    "profile_restart",
    "crash",
    "identity_invalid",
]


class ControlClaimRequest(BaseModel):
    """Claim request (t031_code_f005: read the field notes).

    ``agent_instance_id`` is accepted but IGNORED: the recorded
    instance identity always comes from the automation token id, so a
    caller-supplied instance never renames the claim. Only
    ``agent_session_id`` is honored (it scopes the claim to a session).
    """

    agent_instance_id: str | None = Field(default=None, max_length=128)
    agent_session_id: str | None = Field(default=None, max_length=128)


class ControlHandoffRequest(BaseModel):
    """Handoff request (t031_code_f005: read the field notes).

    Handoff is fail-open toward the user: the identity fields are
    accepted but IGNORED (any automation-token holder may move a
    profile back to the safe state; the server does not check that the
    caller is the controlling agent). Only ``reason``/``detail`` act.
    """

    reason: ControlHandoffReason
    detail: str | None = Field(default=None, max_length=256)
    agent_instance_id: str | None = Field(default=None, max_length=128)
    agent_session_id: str | None = Field(default=None, max_length=128)


class ControlTakeoverReport(BaseModel):
    """Gateway-reported human-input takeover (internal endpoint)."""

    source: str = Field(default="gateway", max_length=64)
    conn_id: str | None = Field(default=None, max_length=128)
    input_kind: str | None = Field(default=None, max_length=64)


class AutomationTunnelData(BaseModel):
    tunnel_id: str
    layer: Literal["api", "supervisor"]
    agent_instance_id: str | None = None
    agent_session_id: str | None = None
    generation: int
    opened_at: str


class ProfileRuntimeResponse(BaseModel):
    profile_id: str
    display_number: int
    desired_state: DesiredState
    observed_state: ObservedState
    runtime_instance_id: str | None
    config_version: int
    failure_count: int
    restart_blocked: bool
    last_exit_event_id: str | None
    last_started_at: str | None = None
    last_stopped_at: str | None = None
    browser_product: str | None = None
    browser_user_agent: str | None = None
    font_set_id: str | None = None
    missing_fonts: list[str] = Field(default_factory=list)
    last_coordinator_error: str | None = None
    search_defaults: SearchDefaultsStatusData | None = None
    transport: TransportObservationData | None = None
    control: ProfileControlStateData | None = None
    backoff_started_at: str | None = None
    next_retry_at: str | None = None
    preview_captured_at: str | None = None
    updated_at: str


class ProfileRuntimeStatusEvent(BaseModel):
    profile_id: str
    desired_state: DesiredState
    observed_state: ObservedState
    runtime_instance_id: str | None = None
    failure_count: int = 0
    restart_blocked: bool = False
    last_started_at: str | None = None
    last_stopped_at: str | None = None
    browser_product: str | None = None
    browser_user_agent: str | None = None
    font_set_id: str | None = None
    missing_fonts: list[str] = Field(default_factory=list)
    last_coordinator_error: str | None = None
    search_defaults: SearchDefaultsStatusData | None = None
    transport: TransportObservationData | None = None
    control: ProfileControlStateData | None = None
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
    browser_product: str | None = Field(default=None, max_length=255)
    browser_user_agent: str | None = None


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


class PreviewPolicySyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    epoch: int = Field(ge=0)
    runtime_instance_id: str | None = Field(default=None, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)


class PreviewObservedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    captured_at: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    policy_epoch: int = Field(ge=0)


class ProfilePreviewEvent(BaseModel):
    event: str = "profile_preview"
    profile_id: str
    captured_at: str


class NetworkApplyPhase(str, Enum):
    PENDING = "pending"
    REBUILDING_CADDY = "rebuilding_caddy"
    REBUILDING_STREAM = "rebuilding_stream"
    VERIFYING_READINESS = "verifying_readiness"
    COMPLETED = "completed"
    FAILED = "failed"


class NetworkAccessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lan_access_enabled: bool = False
    lan_advertised_ip: str | None = None
    https_port: int = Field(default=56661, ge=1, le=65535)

    @model_validator(mode="after")
    def validate_lan_config(self) -> NetworkAccessConfig:
        # LAN strip: whitespace around the advertised IP must never reach
        # persistence, Caddyfile generation, or origin comparison. Strip
        # unconditionally so a disabled-but-dirty value cannot resurface
        # with whitespace after a later enable.
        if isinstance(self.lan_advertised_ip, str):
            stripped = self.lan_advertised_ip.strip()
            self.lan_advertised_ip = stripped or None
        if self.lan_access_enabled:
            if not self.lan_advertised_ip:
                raise ValueError("lan_advertised_ip is required when lan_access_enabled is True")
            import ipaddress
            # Normalize once and store it so validated values are persisted
            # without surrounding whitespace.
            cleaned = self.lan_advertised_ip.strip()
            try:
                ip = ipaddress.IPv4Address(cleaned)
            except Exception as e:
                raise ValueError(f"Invalid IPv4 address: {cleaned}") from e
            if ip.is_loopback:
                raise ValueError(f"Loopback IP {cleaned} cannot be used as advertised LAN IP")
            if ip.is_unspecified:
                raise ValueError(f"Unspecified IP {cleaned} cannot be used as advertised LAN IP")
            if ip.is_multicast:
                raise ValueError(f"Multicast IP {cleaned} cannot be used as advertised LAN IP")
            self.lan_advertised_ip = cleaned
        return self


class AppliedNetworkAccessVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    config: NetworkAccessConfig
    bind_host: str = Field(default="127.0.0.1")
    applied_at: str = Field(min_length=1)
    caddyfile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    origin_whitelist: list[str] = Field(default_factory=list)


class NetworkApplyOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(min_length=1, max_length=128)
    target_version: int = Field(ge=1)
    phase: NetworkApplyPhase = NetworkApplyPhase.PENDING
    error_reason: str | None = None
    new_entry_url: str | None = None
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class NetworkAccessSettingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pending_config: NetworkAccessConfig
    applied_version: AppliedNetworkAccessVersion
    active_operation: NetworkApplyOperation | None = None


class NetworkApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    admin_password: str = Field(min_length=1)


class NetworkSettingsUpdateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "ok"


class NetworkDisconnectCheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    will_disconnect: bool
    new_entry_url: str
