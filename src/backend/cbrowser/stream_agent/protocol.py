"""
Pydantic models and serialization schemas for StreamAgent <->
Gateway/Supervisor communications.
"""

import math
import re
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

# Shared size budgets for the Gateway <-> StreamAgent tunnel (A15). Three
# layers, one authority, identical on both peers:
#   1. raw data payload:        MAX_TUNNEL_DATA_SIZE bytes (UTF-8);
#   2. serialized envelope JSON: MAX_TUNNEL_ENVELOPE_SIZE bytes — JSON string
#      escaping can expand the data layer, so the envelope layer is checked
#      on the actual serialized bytes, never estimated;
#   3. WebSocket frame ceiling:  MAX_STREAM_FRAME_SIZE, which must stay >=
#      the envelope budget so in-budget envelopes are never frame-dropped.
MAX_TUNNEL_DATA_SIZE = 1024 * 1024
MAX_TUNNEL_ENVELOPE_SIZE = 2 * 1024 * 1024 + 64 * 1024
MAX_STREAM_FRAME_SIZE = 1024 * 1024 * 6 + 64 * 1024
assert MAX_STREAM_FRAME_SIZE >= MAX_TUNNEL_ENVELOPE_SIZE


def serialize_tunnel_envelope(envelope: "GatewayTunnelEnvelope") -> str:
    """Serialize a tunnel envelope, enforcing the shared envelope budget."""
    text = envelope.model_dump_json()
    if len(text.encode("utf-8")) > MAX_TUNNEL_ENVELOPE_SIZE:
        raise ValueError("Serialized tunnel envelope exceeds the shared budget")
    return text


class AgentAction(str, Enum):
    REGISTER = "register"
    SUPERVISOR_QUOTA = "supervisor_quota"
    HEARTBEAT = "heartbeat"
    HUMAN_INPUT_TAKEOVER = "human_input_takeover"


# Shared identity validation for every envelope model (t022 A48): one
# definition per identity shape so gateways/agents cannot drift apart.
_PROFILE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_INSTANCE_ID_RE = re.compile(r"^[a-zA-Z0-9_\-\.:]{1,128}$")


def _check_profile_id(v: str) -> str:
    if not v or not _PROFILE_ID_RE.match(v):
        raise ValueError("Invalid profile_id")
    return v


def _check_runtime_instance_id(v: str) -> str:
    if not v or not _INSTANCE_ID_RE.match(v):
        raise ValueError("Invalid runtime_instance_id")
    return v


def _check_conn_id(v: str) -> str:
    if not v or not _INSTANCE_ID_RE.match(v):
        raise ValueError("Invalid conn_id")
    return v


def _check_optional_conn_id(v: str | None) -> str | None:
    if v is not None:
        _check_conn_id(v)
    return v


class GatewayTunnelEnvelope(BaseModel):
    """Wire envelope for tunnel stream packets between Gateway and StreamAgent."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["v2"]
    type: Literal["open", "msg", "close"]
    profile_id: str
    runtime_instance_id: str
    agent_session_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$"
    )
    conn_id: str
    data: str | None = None
    code: int | None = None
    reason: str | None = None

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, v: str) -> str:
        return _check_profile_id(v)

    @field_validator("runtime_instance_id")
    @classmethod
    def validate_runtime_instance_id(cls, v: str) -> str:
        return _check_runtime_instance_id(v)

    @field_validator("conn_id")
    @classmethod
    def validate_conn_id(cls, v: str) -> str:
        return _check_conn_id(v)

    @field_validator("data")
    @classmethod
    def validate_data(cls, v: str | None) -> str | None:
        if v is not None and len(v.encode("utf-8")) > MAX_TUNNEL_DATA_SIZE:
            raise ValueError("data exceeds the shared tunnel data budget")
        return v

    @model_validator(mode="after")
    def validate_type_fields(self) -> "GatewayTunnelEnvelope":
        if self.type == "msg" and self.data is None:
            raise ValueError("msg tunnel packet requires data field")
        return self


class SupervisorQuotaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_fps_cap: float | None = None
    reason: str | None = None

    @field_validator("max_fps_cap")
    @classmethod
    def validate_quota_cap(cls, v: float | None) -> float | None:
        if v is not None and (not math.isfinite(v) or v < 8.0 or v > 30.0):
            raise ValueError(
                "Supervisor quota must be finite and within [8.0, 30.0]"
            )
        return v


class GatewayControlEnvelope(BaseModel):
    """Wire envelope for control plane packets from Gateway to StreamAgent."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["v2"]
    action: Literal[AgentAction.SUPERVISOR_QUOTA]
    profile_id: str
    runtime_instance_id: str
    agent_session_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$"
    )
    conn_id: str | None = None
    payload: SupervisorQuotaPayload = Field(default_factory=SupervisorQuotaPayload)
    timestamp: str | None = None

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, v: str) -> str:
        return _check_profile_id(v)

    @field_validator("runtime_instance_id")
    @classmethod
    def validate_runtime_instance_id(cls, v: str) -> str:
        return _check_runtime_instance_id(v)

    @field_validator("conn_id")
    @classmethod
    def validate_conn_id(cls, v: str | None) -> str | None:
        return _check_optional_conn_id(v)


class RegistrationRejection(BaseModel):
    """Structured registration refusal (t026 AC-008).

    ``code`` is the machine-readable reason the Supervisor's replacement
    policy keys on; ``message`` is a bounded human diagnostic that never
    carries credentials. ``gateway_build_id`` identifies the refusing
    Gateway build; ``agent_build_id`` echoes what the Agent offered.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    message: str = Field(min_length=1, max_length=256)
    gateway_build_id: str | None = Field(default=None, max_length=64)
    agent_build_id: str | None = Field(default=None, max_length=64)


class GatewayRegisterResponse(BaseModel):
    """Registration ACK from Gateway to StreamAgent."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["v2"]
    status: Literal["ok", "error"]
    profile_id: str
    runtime_instance_id: str
    # Only a successful ACK carries a session; rejections have none.
    agent_session_id: str | None = Field(
        default=None, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$"
    )
    error: str | None = None
    gateway_build_id: str | None = Field(default=None, max_length=64)
    rejection: RegistrationRejection | None = None


class _AgentEnvelope(BaseModel):
    """Fields shared by every Agent-originated envelope."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["v2"] = "v2"
    profile_id: str
    runtime_instance_id: str
    agent_session_id: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$"
    )
    conn_id: str | None = None
    timestamp: str | None = None

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, v: str) -> str:
        return _check_profile_id(v)

    @field_validator("runtime_instance_id")
    @classmethod
    def validate_runtime_instance_id(cls, v: str) -> str:
        return _check_runtime_instance_id(v)


RuntimeState = Literal["starting", "ready"]


class AgentRegisterPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hostname: str
    profile_id: str
    runtime_instance_id: str
    udp_port: int
    selkies_version: str = Field(min_length=1, max_length=64)
    build_id: str | None = Field(
        default=None, max_length=64, pattern=r"^[a-zA-Z0-9_.:-]+$"
    )
    runtime_state: RuntimeState
    config_version: int = Field(ge=1)
    video_streaming_mode: bool = False
    width: int = 1920
    height: int = 1080

    @field_validator("udp_port")
    @classmethod
    def validate_udp_port(cls, v: int) -> int:
        if v < 30000 or v > 30991:
            raise ValueError("udp_port must be in allocated range [30000, 30991]")
        return v

    @field_validator("video_streaming_mode")
    @classmethod
    def validate_video_mode(cls, v: bool) -> bool:
        if v is not False:
            raise ValueError("video_streaming_mode must be False")
        return v


class AgentHeartbeatPayload(BaseModel):
    """Application-level health message sent every 10 seconds.

    The video fields come from Selkies peer state, not from page reports.
    """

    model_config = ConfigDict(extra="forbid")

    runtime_state: RuntimeState
    viewer_count: int = Field(ge=0)
    unpaused_video_consumers: int = Field(ge=0)
    capture_running: StrictBool


class AgentRegisterEnvelope(_AgentEnvelope):
    action: Literal[AgentAction.REGISTER] = AgentAction.REGISTER
    payload: AgentRegisterPayload


class AgentHeartbeatEnvelope(_AgentEnvelope):
    action: Literal[AgentAction.HEARTBEAT] = AgentAction.HEARTBEAT
    payload: AgentHeartbeatPayload


class HumanInputTakeoverPayload(BaseModel):
    """Classified foreground human input that must take over control.

    Sent by the Stream Agent when its policy classifier observes a
    takeover input (key press, mouse button, wheel, IME commit) from a
    foreground viewer. The Gateway forwards it to the API, which moves
    the profile to the user and closes agent tunnels (t031).
    """

    model_config = ConfigDict(extra="forbid")

    input_kind: str = Field(min_length=1, max_length=64)
    viewer_conn_id: str | None = Field(default=None, max_length=128)


class AgentHumanInputTakeoverEnvelope(_AgentEnvelope):
    action: Literal[AgentAction.HUMAN_INPUT_TAKEOVER] = (
        AgentAction.HUMAN_INPUT_TAKEOVER
    )
    payload: HumanInputTakeoverPayload


AgentEnvelope = Annotated[
    AgentRegisterEnvelope | AgentHeartbeatEnvelope | AgentHumanInputTakeoverEnvelope,
    Field(discriminator="action"),
]


def validate_agent_envelope(raw: dict[str, Any]) -> AgentEnvelope:
    """Validate any Agent-originated packet against the discriminated union."""
    from pydantic import TypeAdapter

    return TypeAdapter(AgentEnvelope).validate_python(raw)
