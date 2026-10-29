"""
Pydantic models and serialization schemas for StreamAgent <->
Gateway/Supervisor communications.
"""

import json
import math
import re
from enum import Enum
from typing import Any, Dict, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)


class AgentAction(str, Enum):
    REGISTER = "register"
    REGISTERED = "registered"
    VIEWER_JOINED = "viewer_joined"
    VIEWER_LEFT = "viewer_left"
    SIGNAL = "signal"
    VISIBILITY_UPDATE = "visibility_update"
    SUPERVISOR_QUOTA = "supervisor_quota"
    ICE_RESTART = "ice_restart"
    ICE_RESTART_OFFER = "ice_restart_offer"
    ICE_RESTART_ANSWER = "ice_restart_answer"
    HEARTBEAT = "heartbeat"
    ERROR = "error"


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
    data: Optional[str] = None
    code: Optional[int] = None
    reason: Optional[str] = None

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
    def validate_data(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v.encode("utf-8")) > 1024 * 1024:
            raise ValueError("data exceeds 1MB limit")
        return v

    @model_validator(mode="after")
    def validate_type_fields(self) -> "GatewayTunnelEnvelope":
        if self.type == "msg" and self.data is None:
            raise ValueError("msg tunnel packet requires data field")
        return self


class GatewayControlEnvelope(BaseModel):
    """Wire envelope for control plane packets from Gateway to StreamAgent."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["v2"]
    action: AgentAction
    profile_id: str
    runtime_instance_id: str
    agent_session_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$"
    )
    conn_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[str] = None

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
    def validate_conn_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and (not v or not re.match(r"^[a-zA-Z0-9_\-\.:]{1,128}$", v)):
            raise ValueError("Invalid conn_id")
        return v

    @field_validator("payload")
    @classmethod
    def validate_payload_bound(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        dumped = json.dumps(v)
        if len(dumped.encode("utf-8")) > 1024 * 1024:
            raise ValueError("Payload size exceeds 1MB limit")
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
    error: Optional[str] = None


class ProtocolEnvelope(BaseModel):
    """Outbound protocol envelope sent by StreamAgent to Gateway."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["v2"] = "v2"
    action: AgentAction
    profile_id: str
    runtime_instance_id: str
    agent_session_id: Optional[str] = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$"
    )
    conn_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[str] = None

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


class AgentRegisterPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hostname: str
    profile_id: str
    runtime_instance_id: str
    udp_port: int
    video_streaming_mode: bool = False
    max_fps: int = 30
    min_fps: int = 8
    width: int = 1920
    height: int = 1080

    @field_validator("udp_port")
    @classmethod
    def validate_udp_port(cls, v: int) -> int:
        if v < 30000 or v > 30991:
            raise ValueError("udp_port must be in allocated range [30000, 30991]")
        return v

    @field_validator("min_fps")
    @classmethod
    def validate_min_fps(cls, v: int) -> int:
        if v != 8:
            raise ValueError("min_fps must be 8")
        return v

    @field_validator("max_fps")
    @classmethod
    def validate_max_fps(cls, v: int) -> int:
        if v != 30:
            raise ValueError("max_fps must be 30")
        return v

    @field_validator("video_streaming_mode")
    @classmethod
    def validate_video_mode(cls, v: bool) -> bool:
        if v is not False:
            raise ValueError("video_streaming_mode must be False")
        return v


class SupervisorQuotaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_fps_cap: Optional[float] = None
    reason: Optional[str] = None

    @field_validator("max_fps_cap")
    @classmethod
    def validate_quota_cap(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if not math.isfinite(v) or v < 8.0 or v > 30.0:
                raise ValueError(
                    "Supervisor quota must be finite and within [8.0, 30.0]"
                )
        return v


class VisibilityUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    viewer_id: str
    visible: StrictBool

    @field_validator("viewer_id")
    @classmethod
    def validate_viewer_id(cls, v: str) -> str:
        if not v or not re.match(r"^[a-zA-Z0-9_\-\.:]{1,128}$", v):
            raise ValueError("Invalid viewer_id")
        return v


class ICERestartOfferPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conn_id: str
    sdp: str
    type: str = "offer"
    generation: int


class ICERestartAnswerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conn_id: str
    sdp: str
    type: str = "answer"
    generation: int
