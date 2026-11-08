"""Gateway runtime configuration and environment parsing."""

from __future__ import annotations

import math
import os
from pathlib import Path

from cbrowser.domain.models import AppliedNetworkAccessVersion, NetworkAccessConfig, utc_now_iso
from cbrowser.gateway.endpoint import (
    DEFAULT_GATEWAY_PORT,
    normalize_origins,
)
from cbrowser.network_config import (
    DEFAULT_HTTPS_PORT,
    derive_origin_whitelist,
    read_applied_network_state,
)
from cbrowser.secret_files import read_secret_file
from pydantic import BaseModel, ConfigDict, Field, field_validator


def _read_and_verify_key_file(env_var_name: str, path_str: str) -> Path:
    p = Path(path_str)
    try:
        read_secret_file(p, label=f"{env_var_name} key file", minimum_bytes=32)
    except RuntimeError as exc:
        raise ValueError(str(exc)) from None
    return p


class GatewayConfig(BaseModel):
    """Runtime configuration for Stream Gateway service."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    host: str = "0.0.0.0"
    port: int = DEFAULT_GATEWAY_PORT
    agent_key_file: Path
    gateway_token_file: Path
    api_url: str
    api_token_file: Path
    network_state_dir: Path | None = None
    _cached_origins: list[str] = []
    _last_mtime: float = -1.0
    agent_heartbeat_timeout_sec: float = 30.0
    build_id: str = "dev"

    @field_validator("agent_heartbeat_timeout_sec")
    @classmethod
    def validate_heartbeat_timeout(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0:
            raise ValueError("agent_heartbeat_timeout_sec must be a finite positive number")
        return v

    @property
    def allowed_origins(self) -> list[str]:
        """Origin whitelist derived strictly from the applied network configuration (t042 AC-007).
        If the applied file is not yet exported, returns empty list (fails closed).
        """
        if self.network_state_dir and self.network_state_dir.is_dir():
            state_file = self.network_state_dir / "applied_network_version.json"
            if state_file.is_file():
                try:
                    mtime = state_file.stat().st_mtime
                    if mtime != self._last_mtime:
                        state = read_applied_network_state(self.network_state_dir)
                        if state:
                            self._cached_origins = normalize_origins(",".join(state[0].origin_whitelist))
                            self._last_mtime = mtime
                    return self._cached_origins
                except Exception:
                    pass
        return self._cached_origins

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

        # Network state directory from data root or explicit variable
        net_dir_env = os.environ.get("CBROWSER_NETWORK_STATE_DIR")
        if net_dir_env:
            network_state_dir = Path(net_dir_env.strip())
        else:
            data_root = os.environ.get("CBROWSER_DATA_ROOT", "/data").strip()
            network_state_dir = Path(data_root) / "network"

        host = os.environ.get("CBROWSER_GATEWAY_HOST", "0.0.0.0").strip()
        port = int(
            os.environ.get("CBROWSER_GATEWAY_PORT", str(DEFAULT_GATEWAY_PORT)).strip()
        )
        hb_timeout = float(
            os.environ.get("CBROWSER_AGENT_HEARTBEAT_TIMEOUT_SEC", "30.0")
        )

        instance = cls(
            host=host,
            port=port,
            agent_key_file=agent_key_file,
            gateway_token_file=gateway_token_file,
            api_url=api_url,
            api_token_file=api_token_file,
            network_state_dir=network_state_dir,
            agent_heartbeat_timeout_sec=hb_timeout,
            build_id=(os.environ.get("CBROWSER_BUILD_ID") or "dev").strip(),
        )
        # Pre-warm origins
        _ = instance.allowed_origins
        return instance
