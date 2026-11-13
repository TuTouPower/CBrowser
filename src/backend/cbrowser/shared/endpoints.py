"""Neutral home for endpoint value objects, Origin normalization and the
control-plane port constants shared by every service image.

Nothing in this module imports another ``cbrowser`` package: Gateway,
Supervisor, API and the deploy tooling all depend on it, never the
reverse (t062).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

DEFAULT_GATEWAY_PORT = 18080
DEFAULT_GATEWAY_HOST = "host.docker.internal"

#: The one authoritative default for the Supervisor control plane.
#: The Supervisor runner/CLI, compose and every client derive from this
#: value; a divergent literal (the old 8091 in the control client) is a
#: bug, not a configuration.
DEFAULT_SUPERVISOR_PORT = 8005
DEFAULT_SUPERVISOR_URL = f"http://127.0.0.1:{DEFAULT_SUPERVISOR_PORT}"


def normalize_origin(value: str) -> str:
    """Return scheme://host[:non-default-port] with no trailing slash."""
    parsed = urlsplit(value.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"Invalid origin: {value!r}")
    if parsed.username or parsed.password or parsed.path not in ("", "/"):
        raise ValueError(f"Invalid origin: {value!r}")
    if parsed.query or parsed.fragment:
        raise ValueError(f"Invalid origin: {value!r}")
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    default_port = 80 if parsed.scheme == "http" else 443
    netloc = host if port in (None, default_port) else f"{host}:{port}"
    return f"{parsed.scheme}://{netloc}"


def normalize_origins(raw: str | list[str] | tuple[str, ...]) -> list[str]:
    values = raw.split(",") if isinstance(raw, str) else raw
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        origin = normalize_origin(text)
        if origin not in normalized:
            normalized.append(origin)
    return normalized


@dataclass(frozen=True)
class GatewayEndpoint:
    """Gateway signaling endpoint shared by Supervisor and Stream startup."""

    host: str = DEFAULT_GATEWAY_HOST
    port: int = DEFAULT_GATEWAY_PORT
    secure: bool = False

    def __post_init__(self) -> None:
        if not self.host:
            raise ValueError("Gateway endpoint host is required")
        if not 1 <= int(self.port) <= 65535:
            raise ValueError(f"Invalid Gateway port: {self.port}")

    @property
    def ws_url(self) -> str:
        scheme = "wss" if self.secure else "ws"
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{scheme}://{host}:{self.port}"

    @classmethod
    def from_url(cls, url: str) -> GatewayEndpoint:
        parsed = urlsplit(url.strip())
        if parsed.scheme not in ("ws", "wss", "http", "https"):
            raise ValueError(f"Invalid Gateway URL scheme: {parsed.scheme!r}")
        if not parsed.hostname:
            raise ValueError("Gateway URL requires a host")
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("Gateway URL must not contain a path, query or fragment")
        return cls(
            host=parsed.hostname,
            port=parsed.port or DEFAULT_GATEWAY_PORT,
            secure=parsed.scheme in ("wss", "https"),
        )


def gateway_port_from_env() -> int:
    raw = os.environ.get("CBROWSER_GATEWAY_PORT", str(DEFAULT_GATEWAY_PORT)).strip()
    return int(raw)
