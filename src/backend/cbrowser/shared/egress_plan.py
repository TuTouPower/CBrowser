"""Unified Profile egress plan shared across Supervisor and Runner.

Single source of truth for direct vs proxied egress semantics:
- Derives CloakBrowser SDK ``proxy=`` URLs (all schemes: http/https/socks5, with auth).
- Selects defense-in-depth Chromium hardening flags in proxied mode.
- Derives IPv4/IPv6 ``NetworkPolicySpec`` dictionaries identically for container startup,
  periodic convergence verification, and readiness checks.
"""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

PROXY_SCHEMES = frozenset({"http", "https", "socks5"})
PROXY_CREDENTIALS_CHANGED = "proxy_credentials_changed"
DOCKER_EMBEDDED_DNS: tuple[str, int] = ("127.0.0.11", 53)
PROXY_HARDENING_ARGS: tuple[str, ...] = (
    "--disable-quic",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
)


class ProxyCredentialsChangedError(RuntimeError):
    """Fail-closed error raised when mounted proxy credentials are invalid or stale."""

    def __init__(self, code: str = PROXY_CREDENTIALS_CHANGED) -> None:
        super().__init__(code)
        self.code = code


def is_ip_literal(host: str) -> bool:
    """Return True when ``host`` parses as an IPv4 or IPv6 literal (with or without brackets)."""
    cleaned = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        ipaddress.ip_address(cleaned)
        return True
    except ValueError:
        return False


def _validated_proxy_parts(creds: Any) -> tuple[str, str, int, str | None, str | None]:
    """Validate proxy credentials/endpoint mapping without exposing secret values."""
    if not isinstance(creds, Mapping):
        raise ProxyCredentialsChangedError(PROXY_CREDENTIALS_CHANGED)
    scheme = creds.get("scheme")
    host = creds.get("host")
    port = creds.get("port")
    username = creds.get("username")
    password = creds.get("password")
    if (
        not isinstance(scheme, str)
        or scheme not in PROXY_SCHEMES
        or not isinstance(host, str)
        or not host
        or any(ch in host for ch in ("@", "/", " ", "\\", "?", "#", "\t", "\r", "\n"))
        or type(port) is not int
        or not (1 <= port <= 65535)
    ):
        raise ProxyCredentialsChangedError(PROXY_CREDENTIALS_CHANGED)
    if password is not None and (not isinstance(password, str) or not username):
        raise ProxyCredentialsChangedError(PROXY_CREDENTIALS_CHANGED)
    if username is not None and (not isinstance(username, str) or not username):
        raise ProxyCredentialsChangedError(PROXY_CREDENTIALS_CHANGED)
    return scheme, host, port, username, password


def _bracketed_host(host: str) -> str:
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def format_proxy_url(creds: Any, *, include_auth: bool = True) -> str:
    """Build an RFC-3986 proxy URL for SDK ``proxy=`` or policy resolution."""
    scheme, host, port, username, password = _validated_proxy_parts(creds)
    netloc_host = _bracketed_host(host)
    if include_auth and username is not None:
        userinfo = quote(username, safe="")
        if password is not None:
            userinfo = f"{userinfo}:{quote(password, safe='')}"
        return f"{scheme}://{userinfo}@{netloc_host}:{port}"
    return f"{scheme}://{netloc_host}:{port}"


def parse_upstream_endpoint(creds_path: Path) -> tuple[str, bool] | None:
    """Return ``(credentialless_upstream_url, needs_proxy_dns)`` or None if unusable."""
    try:
        creds = json.loads(creds_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        scheme, host, port, _, _ = _validated_proxy_parts(creds)
    except ProxyCredentialsChangedError:
        return None
    upstream = f"{scheme}://{_bracketed_host(host)}:{port}"
    return upstream, not is_ip_literal(host)


@dataclass(frozen=True)
class ProfileEgressPlan:
    """Authoritative egress plan shared by runtime launch and Supervisor netfilter."""

    mode: Literal["direct", "proxy"]
    proxy_enforced: bool
    proxy_url: str | None
    upstream_url: str | None
    needs_proxy_dns: bool
    extra_browser_args: tuple[str, ...]

    def to_network_policy_spec(
        self,
        allowed_tcp: list[tuple[str, int]] | tuple[tuple[str, int], ...],
    ) -> dict[str, Any]:
        """Derive the Browser ``NetworkPolicySpec`` payload."""
        return {
            "role": "browser",
            "allowed_tcp": list(allowed_tcp) if self.proxy_enforced else [],
            "allowed_udp": (
                [DOCKER_EMBEDDED_DNS]
                if (self.proxy_enforced and self.needs_proxy_dns)
                else []
            ),
            "udp_mux_port": None,
            "proxy_enforced": self.proxy_enforced,
        }


DIRECT_EGRESS_PLAN = ProfileEgressPlan(
    mode="direct",
    proxy_enforced=False,
    proxy_url=None,
    upstream_url=None,
    needs_proxy_dns=False,
    extra_browser_args=(),
)


def resolve_runtime_egress_plan(
    proxy_id: str | None,
    expected_credential_revision: int | None,
    credentials_path: Path,
) -> ProfileEgressPlan:
    """Resolve and validate Browser Runner's egress plan; fail closed on any drift."""
    if not proxy_id:
        return DIRECT_EGRESS_PLAN
    try:
        creds = json.loads(credentials_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ProxyCredentialsChangedError(PROXY_CREDENTIALS_CHANGED) from None
    if not isinstance(creds, dict):
        raise ProxyCredentialsChangedError(PROXY_CREDENTIALS_CHANGED)
    revision = creds.get("credential_revision")
    if type(revision) is not int or revision != expected_credential_revision:
        raise ProxyCredentialsChangedError(PROXY_CREDENTIALS_CHANGED)
    proxy_url = format_proxy_url(creds, include_auth=True)
    upstream_url = format_proxy_url(creds, include_auth=False)
    host = str(creds["host"])
    return ProfileEgressPlan(
        mode="proxy",
        proxy_enforced=True,
        proxy_url=proxy_url,
        upstream_url=upstream_url,
        needs_proxy_dns=not is_ip_literal(host),
        extra_browser_args=PROXY_HARDENING_ARGS,
    )


def derive_supervisor_egress_plan(
    *,
    has_proxy: bool,
    creds_path: Path,
) -> ProfileEgressPlan:
    """Derive Supervisor's egress plan for Browser start, verify, and readiness."""
    if not has_proxy:
        return DIRECT_EGRESS_PLAN
    parsed = parse_upstream_endpoint(creds_path)
    if parsed is None:
        # Proxied profiles stay strictly fail-closed (OUTPUT -j DROP, empty allowlist)
        # when credentials cannot be read instead of widening to OUTPUT ACCEPT.
        return ProfileEgressPlan(
            mode="proxy",
            proxy_enforced=True,
            proxy_url=None,
            upstream_url=None,
            needs_proxy_dns=False,
            extra_browser_args=PROXY_HARDENING_ARGS,
        )
    upstream_url, needs_proxy_dns = parsed
    return ProfileEgressPlan(
        mode="proxy",
        proxy_enforced=True,
        proxy_url=None,
        upstream_url=upstream_url,
        needs_proxy_dns=needs_proxy_dns,
        extra_browser_args=PROXY_HARDENING_ARGS,
    )
