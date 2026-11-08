"""Gateway runtime configuration and environment parsing."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

from cbrowser.domain.models import AppliedNetworkAccessVersion, NetworkAccessConfig, utc_now_iso
from cbrowser.gateway.endpoint import (
    DEFAULT_GATEWAY_PORT,
    normalize_origins,
)
from cbrowser.network_config import (
    DEFAULT_HTTPS_PORT,
    derive_origin_whitelist,
    compute_caddyfile_sha256,
    read_applied_network_state,
)
from cbrowser.secret_files import read_secret_file
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)


class NetworkPublicationAuthority:
    def __init__(self) -> None:
        self._authorized: dict[str, Any] | None = None
        self._active: dict[str, Any] = {
            "operation_id": "none",
            "generation": 0,
            "snapshot_hash": "",
            "origins": [],
        }
        self._previous: dict[str, Any] | None = None
        self._last_mtime: float = -1.0

    def note_mtime(self, mtime: float) -> None:
        self._last_mtime = mtime

    def import_baseline(
        self,
        origins: list[str],
        *,
        generation: int = 0,
        snapshot_hash: str = "",
    ) -> dict[str, Any]:
        if self._active.get("operation_id") not in ("none", "baseline"):
            return {"imported": False, "publication": dict(self._active)}
        self._active = {
            "operation_id": "baseline",
            "generation": generation,
            "snapshot_hash": snapshot_hash,
            "origins": list(origins),
        }
        return {"imported": True, "publication": dict(self._active)}

    def authorize(
        self,
        operation_id: str,
        generation: int,
        snapshot_hash: str,
        origins: list[str],
    ) -> dict[str, Any]:
        if generation < self._active["generation"]:
            return {
                "authorized": False,
                "operation_id": operation_id,
                "generation": generation,
                "snapshot_hash": snapshot_hash,
                "active_generation": self._active["generation"],
            }
        self._authorized = {
            "operation_id": operation_id,
            "generation": generation,
            "snapshot_hash": snapshot_hash,
            "origins": list(origins),
        }
        return {"authorized": True, **self._authorized}

    def acknowledge(
        self, operation_id: str, generation: int, snapshot_hash: str
    ) -> dict[str, Any]:
        authorized = self._authorized
        if (
            authorized is None
            or authorized["operation_id"] != operation_id
            or authorized["generation"] != generation
            or authorized["snapshot_hash"] != snapshot_hash
        ):
            return {
                "acked": False,
                "operation_id": operation_id,
                "generation": generation,
                "snapshot_hash": snapshot_hash,
                "origins": list(self._active["origins"]),
            }
        self._previous = dict(self._active)
        self._active = dict(authorized)
        self._authorized = None
        return {"acked": True, **self._active}

    def active(self) -> dict[str, Any]:
        return dict(self._active)

    def revoke(self, operation_id: str) -> dict[str, Any]:
        if (
            self._active.get("operation_id") == operation_id
            and self._previous is not None
        ):
            self._active = dict(self._previous)
            self._previous = None
        self._authorized = None
        return {"revoked": True, "publication": dict(self._active)}


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
    _publications: NetworkPublicationAuthority = PrivateAttr(
        default_factory=NetworkPublicationAuthority
    )
    agent_heartbeat_timeout_sec: float = 30.0
    build_id: str = "dev"

    @field_validator("agent_heartbeat_timeout_sec")
    @classmethod
    def validate_heartbeat_timeout(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0:
            raise ValueError("agent_heartbeat_timeout_sec must be a finite positive number")
        return v

    @model_validator(mode="after")
    def _import_initial_baseline(self) -> GatewayConfig:
        self.import_baseline_from_disk()
        return self

    def note_network_state_mtime(self) -> None:
        if self.network_state_dir and self.network_state_dir.is_dir():
            state_file = self.network_state_dir / "applied_network_version.json"
            if state_file.is_file():
                try:
                    self._publications.note_mtime(state_file.stat().st_mtime)
                except OSError:
                    pass

    @property
    def allowed_origins(self) -> list[str]:
        self.note_network_state_mtime()
        return list(self._publications.active().get("origins", []))

    def import_baseline_from_disk(self) -> dict[str, Any]:
        if not self.network_state_dir:
            return {"imported": False}
        state = read_applied_network_state(self.network_state_dir)
        if state is None:
            return {"imported": False}
        version, caddyfile = state
        return self._publications.import_baseline(
            normalize_origins(",".join(version.origin_whitelist)),
            generation=version.version - 1,
            snapshot_hash=compute_caddyfile_sha256(caddyfile),
        )

    def authorize_publication(
        self,
        operation_id: str,
        generation: int,
        snapshot_hash: str,
        origins: list[str],
    ) -> dict[str, Any]:
        return self._publications.authorize(
            operation_id, generation, snapshot_hash, origins
        )

    def acknowledge_publication(
        self, operation_id: str, generation: int, snapshot_hash: str
    ) -> dict[str, Any]:
        return self._publications.acknowledge(
            operation_id, generation, snapshot_hash
        )

    def active_publication(self) -> dict[str, Any]:
        return self._publications.active()

    def revoke_publication(self, operation_id: str) -> dict[str, Any]:
        return self._publications.revoke(operation_id)

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
        _ = instance.allowed_origins
        instance.import_baseline_from_disk()
        return instance
