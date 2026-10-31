"""
Pydantic models and serialization schemas for StreamAgent <->
Gateway/Supervisor communications.
"""

import ipaddress
import json
import math
import re
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import quote

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
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
    SUPERVISOR_QUOTA = "supervisor_quota"
    ICE_RESTART = "ice_restart"
    ICE_RESTART_OFFER = "ice_restart_offer"
    ICE_RESTART_ANSWER = "ice_restart_answer"
    ICE_RESTART_COMMITTED = "ice_restart_committed"
    HEARTBEAT = "heartbeat"
    RTC_CONFIG = "rtc_config"
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
    turn_host: str
    turn_port: int = Field(ge=1, le=65535)
    video_streaming_mode: bool = False
    max_fps: int = 30
    min_fps: int = 8
    width: int = 1920
    height: int = 1080

    @field_validator("turn_host")
    @classmethod
    def validate_turn_host(cls, v: str) -> str:
        try:
            ipaddress.ip_address(v)
        except ValueError:
            raise ValueError("turn_host must be a valid IPv4 or IPv6 address")
        return v

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


class AgentHeartbeatPayload(BaseModel):
    """Application-level health message sent every 10 seconds.

    The video fields come from Selkies peer state, not from page reports.
    """

    model_config = ConfigDict(extra="forbid")

    runtime_state: RuntimeState
    viewer_count: int = Field(ge=0)
    unpaused_video_consumers: int = Field(ge=0)
    capture_running: StrictBool


class IceServer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    urls: List[str] = Field(min_length=1)
    username: Optional[str] = Field(default=None, max_length=256)
    credential: Optional[SecretStr] = None

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, v: List[str]) -> List[str]:
        for url in v:
            if not url.startswith(("stun:", "turn:", "turns:")):
                raise ValueError("ICE server URL must use stun, turn or turns")
        return v


class RtcConfigPayload(BaseModel):
    """Stream-side ICE servers for new PeerConnections and restarts."""

    model_config = ConfigDict(extra="forbid")

    generation: int = Field(ge=1)
    ice_servers: List[IceServer] = Field(min_length=1)
    relay_only: StrictBool = False

    def selkies_server_urls(self) -> Tuple[List[str], List[str]]:
        """STUN and TURN URL lists as Selkies RTCApp.update_rtc_config takes them.

        Selkies parses TURN entries as turn://user:pass@host:port?query and
        unquotes the credentials, so they are percent-encoded here.
        """
        stun: List[str] = []
        turn: List[str] = []
        for server in self.ice_servers:
            for url in server.urls:
                scheme, rest = url.split(":", 1)
                if scheme == "stun":
                    stun.append(url)
                    continue
                auth = ""
                if server.username is not None and server.credential is not None:
                    secret = server.credential.get_secret_value()
                    auth = (
                        f"{quote(server.username, safe='')}:{quote(secret, safe='')}@"
                    )
                turn.append(f"{scheme}://{auth}{rest}")
        return stun, turn

    def wire_ice_servers(self) -> List[Dict[str, Any]]:
        servers = []
        for server in self.ice_servers:
            entry: Dict[str, Any] = {"urls": list(server.urls)}
            if server.username is not None:
                entry["username"] = server.username
            if server.credential is not None:
                entry["credential"] = server.credential.get_secret_value()
            servers.append(entry)
        return servers
