"""
Configuration loader and security validator for StreamAgent.
Requires external secret file or explicit environment injection;
enforces no hardcoded secrets.
"""

import ipaddress
import json
import math
import os
import re
import urllib.parse
from pathlib import Path
from typing import List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)


class StreamAgentConfig(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True, extra="forbid")

    profile_id: str
    runtime_instance_id: str
    gateway_url: str
    agent_token: SecretStr
    turn_host: str = "127.0.0.1"
    turn_port: int = Field(default=3478, ge=1, le=65535)
    udp_mux_port: int = 30006
    width: int = 1920
    height: int = 1080
    depth: int = 24
    pulse_dir: str = "/pulse"
    x11_socket: str = "/tmp/.X11-unix/X99"
    xauthority_path: str = "/tmp/.Xauthority"
    min_fps: float = 8.0
    max_fps: float = 30.0
    video_streaming_mode: bool = False
    turn_servers: List[dict] = Field(default_factory=list)
    config_version: int = Field(default=1, ge=1)
    selkies_version: Optional[str] = None
    controller_token: Optional[SecretStr] = None

    @field_validator("turn_host")
    @classmethod
    def validate_turn_host(cls, v: str) -> str:
        try:
            ipaddress.ip_address(v)
        except ValueError:
            raise ValueError("turn_host must be a valid IPv4 or IPv6 address")
        return v

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, v: str) -> str:
        if not v or not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid profile_id: must match ^[a-zA-Z0-9_-]+$")
        return v

    @field_validator("runtime_instance_id")
    @classmethod
    def validate_runtime_instance_id(cls, v: str) -> str:
        if not v or not re.match(r"^[a-zA-Z0-9_\-\.:]{1,128}$", v):
            raise ValueError(
                "Invalid runtime_instance_id: must match ^[a-zA-Z0-9_\\-\\.:]{1,128}$"
            )
        return v

    @field_validator("gateway_url")
    @classmethod
    def validate_gateway_url(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError("gateway_url must be a non-empty string")
        parsed = urllib.parse.urlsplit(v)
        if parsed.scheme not in ("ws", "wss"):
            raise ValueError("gateway_url scheme must be ws or wss")
        if not parsed.hostname:
            raise ValueError("gateway_url must contain a valid hostname")
        if parsed.username or parsed.password or "@" in parsed.netloc:
            raise ValueError("gateway_url must not contain user credentials")
        if parsed.query:
            raise ValueError("gateway_url must not contain query parameters")
        if parsed.fragment:
            raise ValueError("gateway_url must not contain URL fragments")
        try:
            port = parsed.port
            if port is not None and not (1 <= port <= 65535):
                raise ValueError("gateway_url port must be between 1 and 65535")
        except ValueError:
            raise ValueError("Invalid gateway_url port: must be between 1 and 65535")
        return v

    @field_validator("agent_token")
    @classmethod
    def validate_agent_token(cls, v: SecretStr) -> SecretStr:
        val = v.get_secret_value().strip()
        if not val or len(val) < 8:
            raise ValueError("agent_token must be at least 8 characters")
        return v

    @field_validator("controller_token")
    @classmethod
    def validate_controller_token(cls, v: Optional[SecretStr]) -> Optional[SecretStr]:
        if v is not None:
            val = v.get_secret_value().strip()
            if not val or len(val) < 8:
                raise ValueError("controller_token must be at least 8 characters")
        return v

    @field_validator("udp_mux_port")
    @classmethod
    def validate_udp_mux_port(cls, v: int) -> int:
        if v < 30000 or v > 30991:
            raise ValueError("udp_mux_port must be in allocated range [30000, 30991]")
        return v

    @field_validator("width")
    @classmethod
    def validate_width(cls, v: int) -> int:
        if not 100 <= v <= 10000:
            raise ValueError("Geometry width must be between 100 and 10000")
        return v

    @field_validator("height")
    @classmethod
    def validate_height(cls, v: int) -> int:
        if not 100 <= v <= 10000:
            raise ValueError("Geometry height must be between 100 and 10000")
        return v

    @field_validator("depth")
    @classmethod
    def validate_depth(cls, v: int) -> int:
        if v != 24:
            raise ValueError("Fixed geometry depth must be 24")
        return v

    @field_validator("video_streaming_mode")
    @classmethod
    def validate_video_mode(cls, v: bool) -> bool:
        if v is not False:
            raise ValueError("video_streaming_mode must be False")
        return v

    @model_validator(mode="after")
    def validate_fps_bounds(self) -> "StreamAgentConfig":
        if not math.isfinite(self.min_fps) or not math.isfinite(self.max_fps):
            raise ValueError("min_fps and max_fps must be finite numbers")
        if self.min_fps < 8.0:
            raise ValueError("min_fps cannot be lower than 8.0 FPS floor")
        if self.max_fps > 30.0:
            raise ValueError("max_fps cannot exceed 30.0 FPS cap")
        if self.min_fps > self.max_fps:
            raise ValueError("min_fps cannot exceed max_fps")
        return self

    def __repr__(self) -> str:
        ctrl_str = "'***'" if self.controller_token is not None else "None"
        return (
            f"StreamAgentConfig(profile_id={self.profile_id!r}, "
            f"runtime_instance_id={self.runtime_instance_id!r}, "
            f"gateway_url={self.gateway_url!r}, "
            f"agent_token='***', "
            f"controller_token={ctrl_str}, "
            f"turn_host={self.turn_host!r}, "
            f"turn_port={self.turn_port}, "
            f"udp_mux_port={self.udp_mux_port}, "
            f"width={self.width}, "
            f"height={self.height}, "
            f"depth={self.depth}, "
            f"min_fps={self.min_fps}, "
            f"max_fps={self.max_fps}, "
            f"video_streaming_mode={self.video_streaming_mode}, "
            f"config_version={self.config_version})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    @classmethod
    def from_env(cls) -> "StreamAgentConfig":
        profile_id = os.environ.get("CBROWSER_PROFILE_ID")
        if not profile_id:
            raise ValueError("CBROWSER_PROFILE_ID environment variable is required")

        gateway_url = os.environ.get("CBROWSER_GATEWAY_URL")
        if not gateway_url:
            raise ValueError("CBROWSER_GATEWAY_URL environment variable is required")

        runtime_instance_id = os.environ.get("CBROWSER_RUNTIME_INSTANCE_ID")
        if not runtime_instance_id:
            raise ValueError(
                "CBROWSER_RUNTIME_INSTANCE_ID environment variable is required"
            )

        config_version_raw = os.environ.get("CBROWSER_CONFIG_VERSION")
        if not config_version_raw:
            raise ValueError("CBROWSER_CONFIG_VERSION environment variable is required")
        try:
            config_version = int(config_version_raw)
        except ValueError:
            raise ValueError("Invalid CBROWSER_CONFIG_VERSION integer")
        if config_version < 1:
            raise ValueError("CBROWSER_CONFIG_VERSION must be >= 1")

        # Secret management: loading non-empty external file fail closed,
        # no silent fallback when explicit file bad
        token_str: Optional[str] = None
        secret_file = os.environ.get("CBROWSER_AGENT_SECRET_FILE")
        if secret_file:
            path = Path(secret_file)
            if not path.is_file():
                raise ValueError("Secret file not found or not a regular file")
            token_str = path.read_text().strip()
            if not token_str:
                raise ValueError("Secret file is empty")
        else:
            token_str = os.environ.get("CBROWSER_AGENT_TOKEN")

        if not token_str:
            raise ValueError(
                "Authentication secret required: set CBROWSER_AGENT_SECRET_FILE "
                "or CBROWSER_AGENT_TOKEN"
            )

        width_raw = os.environ.get("CBROWSER_SCREEN_WIDTH")
        height_raw = os.environ.get("CBROWSER_SCREEN_HEIGHT")
        if width_raw is None and height_raw is None:
            width, height = 1920, 1080
        else:
            if not width_raw:
                raise ValueError(
                    "CBROWSER_SCREEN_WIDTH environment variable is required"
                )
            if not height_raw:
                raise ValueError(
                    "CBROWSER_SCREEN_HEIGHT environment variable is required"
                )
            try:
                width = int(width_raw)
                height = int(height_raw)
            except ValueError:
                raise ValueError("Invalid CBROWSER_SCREEN_WIDTH/HEIGHT integer")
            if not 100 <= width <= 10000 or not 100 <= height <= 10000:
                raise ValueError(
                    "CBROWSER_SCREEN_WIDTH/HEIGHT must be between 100 and 10000"
                )

        udp_port_raw = os.environ.get("CBROWSER_UDP_MUX_PORT", "30006")
        try:
            udp_port = int(udp_port_raw)
        except ValueError:
            raise ValueError("Invalid CBROWSER_UDP_MUX_PORT integer")

        turn_host = os.environ.get("SELKIES_TURN_HOST")
        if not turn_host or not turn_host.strip():
            raise ValueError("SELKIES_TURN_HOST environment variable is required")
        turn_host = turn_host.strip()
        try:
            ipaddress.ip_address(turn_host)
        except ValueError:
            raise ValueError("SELKIES_TURN_HOST must be a valid IPv4 or IPv6 address")

        turn_port_raw = os.environ.get("SELKIES_TURN_PORT")
        if not turn_port_raw or not turn_port_raw.strip():
            raise ValueError("SELKIES_TURN_PORT environment variable is required")
        try:
            turn_port = int(turn_port_raw.strip())
        except ValueError:
            raise ValueError("Invalid SELKIES_TURN_PORT integer")
        if not (1 <= turn_port <= 65535):
            raise ValueError("SELKIES_TURN_PORT must be between 1 and 65535")

        pulse_dir = os.environ.get("CBROWSER_PULSE_DIR", "/pulse")
        x11_socket = os.environ.get("CBROWSER_X11_SOCKET", "/tmp/.X11-unix/X99")
        xauth = os.environ.get("XAUTHORITY", "/tmp/.Xauthority")

        controller_token_str: Optional[str] = None
        selkies_cred_file = os.environ.get("CBROWSER_SELKIES_CREDENTIALS_FILE")
        if selkies_cred_file:
            path = Path(selkies_cred_file)
            if not path.is_file():
                raise ValueError(
                    "Selkies credentials file not found or not a regular file"
                )
            try:
                cred_data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise ValueError("Invalid Selkies credentials file") from None
            controller_token_str = cred_data.get("controller_token")
            if not controller_token_str:
                raise ValueError("controller_token missing in Selkies credentials file")

        return cls(
            profile_id=profile_id,
            runtime_instance_id=runtime_instance_id,
            gateway_url=gateway_url,
            agent_token=token_str,
            turn_host=turn_host,
            turn_port=turn_port,
            udp_mux_port=udp_port,
            width=width,
            height=height,
            pulse_dir=pulse_dir,
            x11_socket=x11_socket,
            xauthority_path=xauth,
            config_version=config_version,
            controller_token=controller_token_str,
        )
