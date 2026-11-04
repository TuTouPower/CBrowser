"""Gateway runtime configuration and environment parsing."""

from __future__ import annotations

import math
import os
from pathlib import Path

from cbrowser.gateway.endpoint import (
    DEFAULT_GATEWAY_PORT,
    normalize_origins,
)
from cbrowser.secret_files import read_secret_file
from pydantic import BaseModel, ConfigDict, field_validator


def _read_and_verify_key_file(env_var_name: str, path_str: str) -> Path:
    p = Path(path_str)
    try:
        read_secret_file(p, label=f"{env_var_name} key file", minimum_bytes=32)
    except RuntimeError as exc:
        raise ValueError(str(exc)) from None
    return p


class GatewayConfig(BaseModel):
    """Runtime configuration for Stream Gateway service."""

    model_config = ConfigDict(extra="forbid")

    host: str = "0.0.0.0"
    port: int = DEFAULT_GATEWAY_PORT
    agent_key_file: Path
    gateway_token_file: Path
    api_url: str
    api_token_file: Path
    allowed_origins: list[str]
    agent_heartbeat_timeout_sec: float = 30.0
    build_id: str = "dev"

    @field_validator("agent_heartbeat_timeout_sec")
    @classmethod
    def validate_heartbeat_timeout(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0:
            raise ValueError("agent_heartbeat_timeout_sec must be a finite positive number")
        return v

    @classmethod
    def from_env(cls) -> GatewayConfig:
        """Instantiates GatewayConfig from environment with validation."""

        def get_required(key: str) -> str:
            val = os.environ.get(key)
            if not val or not val.strip():
                raise ValueError(f"Missing required environment variable: {key}")
            return val.strip()

        agent_key_file = _read_and_verify_key_file(
            "CBROWSER_AGENT_KEY_FILE", get_required("CBROWSER_AGENT_KEY_FILE")
        )
        gateway_token_file = _read_and_verify_key_file(
            "CBROWSER_GATEWAY_TOKEN_FILE", get_required("CBROWSER_GATEWAY_TOKEN_FILE")
        )
        api_token_file = _read_and_verify_key_file(
            "CBROWSER_GATEWAY_API_TOKEN_FILE",
            get_required("CBROWSER_GATEWAY_API_TOKEN_FILE"),
        )

        api_url = get_required("CBROWSER_GATEWAY_API_URL").rstrip("/")

        raw_origins = get_required("CBROWSER_ALLOWED_ORIGINS")
        try:
            allowed_origins = normalize_origins(raw_origins)
        except ValueError as exc:
            raise ValueError(f"Invalid CBROWSER_ALLOWED_ORIGINS: {exc}") from None
        if not allowed_origins:
            raise ValueError("CBROWSER_ALLOWED_ORIGINS cannot be empty")

        host = os.environ.get("CBROWSER_GATEWAY_HOST", "0.0.0.0").strip()
        port = int(
            os.environ.get("CBROWSER_GATEWAY_PORT", str(DEFAULT_GATEWAY_PORT)).strip()
        )
        hb_timeout = float(
            os.environ.get("CBROWSER_AGENT_HEARTBEAT_TIMEOUT_SEC", "30.0")
        )

        return cls(
            host=host,
            port=port,
            agent_key_file=agent_key_file,
            gateway_token_file=gateway_token_file,
            api_url=api_url,
            api_token_file=api_token_file,
            allowed_origins=allowed_origins,
            agent_heartbeat_timeout_sec=hb_timeout,
            build_id=(os.environ.get("CBROWSER_BUILD_ID") or "dev").strip(),
        )
