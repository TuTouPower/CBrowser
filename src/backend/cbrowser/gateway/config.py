"""Gateway runtime configuration and environment parsing."""

from __future__ import annotations

import os
from pathlib import Path

from cbrowser.gateway.endpoint import (
    DEFAULT_GATEWAY_PORT,
    normalize_origins,
)
from pydantic import BaseModel, ConfigDict


def _read_and_verify_key_file(env_var_name: str, path_str: str) -> Path:
    p = Path(path_str)
    try:
        content = p.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise ValueError(f"Cannot read file for {env_var_name} at {p}") from None
    if len(content.encode("utf-8")) < 32:
        raise ValueError(f"{env_var_name} key file must contain at least 32 bytes")
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
    turn_secret_file: Path
    webrtc_mode: str
    turn_public_urls: list[str]
    credential_lifetime_sec: float = 24 * 3600.0
    generation_interval_sec: float = 12 * 3600.0
    ice_restart_lead_time_sec: float = 6 * 3600.0
    agent_heartbeat_timeout_sec: float = 30.0

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
        turn_secret_file = _read_and_verify_key_file(
            "CBROWSER_TURN_SECRET_FILE", get_required("CBROWSER_TURN_SECRET_FILE")
        )

        api_url = get_required("CBROWSER_GATEWAY_API_URL").rstrip("/")

        raw_origins = get_required("CBROWSER_ALLOWED_ORIGINS")
        try:
            allowed_origins = normalize_origins(raw_origins)
        except ValueError as exc:
            raise ValueError(f"Invalid CBROWSER_ALLOWED_ORIGINS: {exc}") from None
        if not allowed_origins:
            raise ValueError("CBROWSER_ALLOWED_ORIGINS cannot be empty")

        webrtc_mode = get_required("CBROWSER_WEBRTC_MODE")
        if webrtc_mode not in ("local", "lan", "public", "relay-only"):
            raise ValueError(
                f"Invalid CBROWSER_WEBRTC_MODE '{webrtc_mode}', must be one of "
                "local|lan|public|relay-only"
            )

        raw_public_turn = get_required("CBROWSER_TURN_PUBLIC_URLS")
        turn_public_urls = [u.strip() for u in raw_public_turn.split(",") if u.strip()]
        if not turn_public_urls:
            raise ValueError("CBROWSER_TURN_PUBLIC_URLS cannot be empty")

        host = os.environ.get("CBROWSER_GATEWAY_HOST", "0.0.0.0").strip()
        port = int(
            os.environ.get("CBROWSER_GATEWAY_PORT", str(DEFAULT_GATEWAY_PORT)).strip()
        )

        lifetime = float(
            os.environ.get("CBROWSER_RTC_CREDENTIAL_LIFETIME_SEC", str(24 * 3600.0))
        )
        interval = float(
            os.environ.get("CBROWSER_RTC_GENERATION_INTERVAL_SEC", str(12 * 3600.0))
        )
        lead_time = float(
            os.environ.get("CBROWSER_RTC_ICE_RESTART_LEAD_TIME_SEC", str(6 * 3600.0))
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
            turn_secret_file=turn_secret_file,
            webrtc_mode=webrtc_mode,
            turn_public_urls=turn_public_urls,
            credential_lifetime_sec=lifetime,
            generation_interval_sec=interval,
            ice_restart_lead_time_sec=lead_time,
            agent_heartbeat_timeout_sec=hb_timeout,
        )
