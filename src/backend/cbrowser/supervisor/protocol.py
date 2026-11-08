"""Data models and protocols for CBrowser Supervisor Internal Control Server."""

from __future__ import annotations

from typing import Literal, Union

from cbrowser.runtime_agent.protocol import SearchDefaultsStatus
from cbrowser.udp_mux import udp_mux_bounds
from pydantic import BaseModel, ConfigDict, Field

ObservedState = Literal["stopped", "starting", "running", "stopping", "error"]
DesiredState = Literal["stopped", "running"]

UDP_MUX_MIN, UDP_MUX_MAX = udp_mux_bounds()


class StartProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str = Field(min_length=1, max_length=128)
    config_version: int = Field(default=1, ge=1)
    force: bool = False
    operation_id: str | None = Field(default=None, min_length=1, max_length=128)


class StartProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    status: Literal["starting", "running"]
    runtime_instance_id: str
    udp_mux_port: int = Field(ge=UDP_MUX_MIN, le=UDP_MUX_MAX)
    browser_container: str
    stream_container: str


class StopProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str = Field(min_length=1, max_length=128)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    operation_id: str = Field(min_length=1, max_length=128)


class StopProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    runtime_instance_id: str | None = None
    # Command result, not an observation: "stopped" only when this command
    # actually stopped the target, "already_absent" when the target was
    # confirmed not to exist, and "superseded_noop" when a newer instance
    # has replaced the target (which is left untouched).
    status: Literal["stopped", "already_absent", "superseded_noop"]


class SearchDefaultsRetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str = Field(min_length=1, max_length=128)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)


class SearchDefaultsStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    runtime_instance_id: str | None = None
    search_defaults: SearchDefaultsStatus | None = None


class PreviewPolicySyncResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"] = "ok"


class ResetBlockedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str = Field(min_length=1, max_length=128)


class CloseTunnelsRequest(BaseModel):
    """t031: close every Supervisor-layer tunnel for a profile.

    ``generation`` is the post-takeover control generation: the fence
    advances to it monotonically, so later forwarded handshakes at or
    below it are stale and rejected.
    """

    model_config = ConfigDict(extra="forbid")
    generation: int = Field(ge=0)


class CloseTunnelsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    generation: int
    closed_tunnel_ids: list[str] = Field(default_factory=list)
    attendant_released: bool = False


class AttendantDialogsResponse(BaseModel):
    """t031: held dialogs peeked from the resident attendant."""

    model_config = ConfigDict(extra="forbid")
    profile_id: str
    dialogs: list[dict] = Field(default_factory=list)


class AnswerAttendantDialogRequest(BaseModel):
    """t031: answer a held dialog through the attendant's session."""

    model_config = ConfigDict(extra="forbid")
    target_id: str = Field(min_length=1)
    accept: bool = False
    prompt_text: str | None = None


class AnswerAttendantDialogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    dialog: dict
    action: str


class ResetBlockedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    status: str = "ok"
    message: str = "Restart block cleared"


class ProfileRuntimeStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    runtime_instance_id: str | None = None
    observed_state: ObservedState = "stopped"
    desired_state: DesiredState = "stopped"
    udp_mux_port: int | None = None
    browser_container_id: str | None = None
    stream_container_id: str | None = None
    restart_blocked: bool = False
    failure_count: int = 0


LayerState = Literal["running", "stopped", "missing", "error", "unknown"]
TransportState = Literal["ready", "recovering", "failed", "unknown"]


class TransportObservation(BaseModel):
    """Layered runtime observation for one Profile (t026 AC-010).

    Browser/Stream are process layers; transport is the media/signaling
    path between them and the viewer (Gateway attachment, policy and
    Agent registration). Held in memory by the Supervisor and the API;
    never persisted. ``unknown`` is the honest value before the first
    report of a generation.
    """

    model_config = ConfigDict(extra="forbid")
    profile_id: str
    runtime_instance_id: str | None = None
    browser_state: LayerState = "unknown"
    stream_state: LayerState = "unknown"
    transport_state: TransportState = "unknown"
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


class TransportObservationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    runtime_instance_id: str | None = None
    transport: TransportObservation | None = None


class ReconcileAllResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scanned: int = 0
    profiles: list[str] = Field(default_factory=list)


class ProfileReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    runtime_instance_id: str | None = None
    ready: bool = False
    # None means the check could not be evaluated (unknown), which
    # always makes the profile not ready.
    checks: dict[str, bool | None] = Field(default_factory=dict)
    diagnostics: list[str] = Field(default_factory=list)


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ready: bool = False
    reason: str | None = None
    profiles: list[ProfileReadiness] = Field(default_factory=list)


class RebuildEdgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_version: int = Field(ge=1)
    bind_host: str = Field(min_length=1, max_length=64)
    https_port: int = Field(ge=1, le=65535)
    caddyfile_path: str = Field(min_length=1)


class ConvergeStreamsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_version: int = Field(ge=1)
    bind_host: str = Field(min_length=1, max_length=64)
    advertised_ip: str = Field(min_length=1, max_length=64)


SupervisorMessage = Union[
    StartProfileRequest,
    StartProfileResponse,
    StopProfileRequest,
    StopProfileResponse,
    SearchDefaultsRetryRequest,
    SearchDefaultsStatusResponse,
    PreviewPolicySyncResponse,
    ResetBlockedRequest,
    CloseTunnelsRequest,
    CloseTunnelsResponse,
    AttendantDialogsResponse,
    AnswerAttendantDialogRequest,
    AnswerAttendantDialogResponse,
    ResetBlockedResponse,
    ProfileRuntimeStatus,
    TransportObservation,
    TransportObservationResponse,
    ReconcileAllResponse,
    ProfileReadiness,
    ReadinessResponse,
    RebuildEdgeRequest,
    ConvergeStreamsRequest,
]
