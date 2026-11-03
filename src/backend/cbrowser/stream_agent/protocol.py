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

# Shared transport frame ceiling for both Agent and Gateway WebSocket peers.
MAX_STREAM_FRAME_SIZE = 1024 * 1024 * 6 + 64 * 1024


class AgentAction(str, Enum):
    REGISTER = "register"
    SUPERVISOR_QUOTA = "supervisor_quota"
    HEARTBEAT = "heartbeat"


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
        if not v or not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid profile_id")
        return v

    @field_validator("runtime_instance_id")
    @classmethod
    def validate_runtime_instance_id(cls, v: str) -> str:
        if not v or not re.match(r"^[a-zA-Z0-9_\-\.:]{1,128}$", v):
            raise ValueError("Invalid runtime_instance_id")
        return v

    @field_validator("conn_id")
    @classmethod
    def validate_conn_id(cls, v: str) -> str:
        if not v or not re.match(r"^[a-zA-Z0-9_\-\.:]{1,128}$", v):
            raise ValueError("Invalid conn_id")
        return v

    @field_validator("data")
    @classmethod
    def validate_data(cls, v: str | None) -> str | None:
        if v is not None and len(v.encode("utf-8")) > 1024 * 1024:
            raise ValueError("data exceeds 1MB limit")
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
        if not v or not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid profile_id")
        return v

    @field_validator("runtime_instance_id")
    @classmethod
    def validate_runtime_instance_id(cls, v: str) -> str:
        if not v or not re.match(r"^[a-zA-Z0-9_\-\.:]{1,128}$", v):
            raise ValueError("Invalid runtime_instance_id")
        return v

    @field_validator("conn_id")
    @classmethod
    def validate_conn_id(cls, v: str | None) -> str | None:
        if v is not None and (not v or not re.match(r"^[a-zA-Z0-9_\-\.:]{1,128}$", v)):
            raise ValueError("Invalid conn_id")
        return v


class GatewayRegisterResponse(BaseModel):
    """Registration ACK from Gateway to StreamAgent."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["v2"]
    status: Literal["ok", "error"]
    profile_id: str
    runtime_instance_id: str
    agent_session_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$"
    )
    error: str | None = None


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
        if not v or not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid profile_id")
        return v

    @field_validator("runtime_instance_id")
    @classmethod
    def validate_runtime_instance_id(cls, v: str) -> str:
        if not v or not re.match(r"^[a-zA-Z0-9_\-\.:]{1,128}$", v):
            raise ValueError("Invalid runtime_instance_id")
        return v


RuntimeState = Literal["starting", "ready"]


class AgentRegisterPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hostname: str
    profile_id: str
    runtime_instance_id: str
    udp_port: int
    selkies_version: str = Field(min_length=1, max_length=64)
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


AgentEnvelope = Annotated[
    AgentRegisterEnvelope | AgentHeartbeatEnvelope,
    Field(discriminator="action"),
]


def validate_agent_envelope(raw: dict[str, Any]) -> AgentEnvelope:
    """Validate any Agent-originated packet against the discriminated union."""
    from pydantic import TypeAdapter

    return TypeAdapter(AgentEnvelope).validate_python(raw)
