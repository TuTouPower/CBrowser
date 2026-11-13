"""Gateway configuration.

Single source of truth for Gateway settings. All required fields must be
provided; nothing is guessed. ``allowed_origins`` is derived from the
deployment HTTPS port (``CBROWSER_HTTPS_PORT``, default
``DEFAULT_HTTPS_PORT``) — the same input API uses — so the two services
cannot drift (t054, ADR 031). There is no runtime network state: the
port is fixed at deploy time and the whitelist is a pure function of it.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from cbrowser.shared.endpoints import DEFAULT_GATEWAY_PORT
from cbrowser.network_config import DEFAULT_HTTPS_PORT, derive_origin_whitelist
from cbrowser.secret_files import read_secret_file


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
    viewer_grant_key_file: Path
    agent_heartbeat_timeout_sec: float = 30.0
    build_id: str = "dev"
    https_port: int = DEFAULT_HTTPS_PORT

    @field_validator("agent_heartbeat_timeout_sec")
    @classmethod
    def validate_heartbeat_timeout(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0:
            raise ValueError("agent_heartbeat_timeout_sec must be a finite positive number")
        return v

    @field_validator("https_port")
    @classmethod
    def validate_https_port(cls, v: int) -> int:
        if type(v) is not int or not 1 <= v <= 65535:
            raise ValueError("https_port must be an integer between 1 and 65535")
        return v

    @model_validator(mode="before")
    @classmethod
    def _parse_https_port_from_env(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "https_port" not in data:
            env_value = os.environ.get("CBROWSER_HTTPS_PORT")
            if env_value:
                data["https_port"] = int(env_value)
        return data

    @property
    def allowed_origins(self) -> list[str]:
        """Origin whitelist, deterministically derived from the deploy port."""
        return derive_origin_whitelist(self.https_port)

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
        viewer_grant_key_file = _read_and_verify_key_file(
            "CBROWSER_VIEWER_GRANT_KEY_FILE",
            get_required("CBROWSER_VIEWER_GRANT_KEY_FILE"),
        )

        api_url = get_required("CBROWSER_GATEWAY_API_URL").rstrip("/")

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
            viewer_grant_key_file=viewer_grant_key_file,
            agent_heartbeat_timeout_sec=hb_timeout,
            build_id=(os.environ.get("CBROWSER_BUILD_ID") or "dev").strip(),
        )
