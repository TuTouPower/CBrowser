"""Network access configuration, deterministic Caddyfile generation, and Origin derivation."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
from pathlib import Path

from cbrowser.domain.models import (
    AppliedNetworkAccessVersion,
    NetworkAccessConfig,
    utc_now_iso,
)
from cbrowser.supervisor.file_storage import atomic_write_text

logger = logging.getLogger("cbrowser.network_config")

DEFAULT_HTTPS_PORT = 56661
APPLIED_VERSION_FILENAME = "applied_network_version.json"
CADDYFILE_FILENAME = "Caddyfile"


def validate_lan_ip(ip_str: str | None) -> str:
    """Validate that ip_str is a non-loopback, non-unspecified, non-multicast unicast IPv4."""
    if not ip_str or not isinstance(ip_str, str):
        raise ValueError("LAN advertised IP must be a non-empty string")
    cleaned = ip_str.strip()
    try:
        ip = ipaddress.IPv4Address(cleaned)
    except Exception as e:
        raise ValueError(f"Invalid IPv4 address: {cleaned}") from e
    if ip.is_loopback:
        raise ValueError(f"Loopback IP {cleaned} cannot be used as advertised LAN IP")
    if ip.is_unspecified:
        raise ValueError(f"Unspecified IP {cleaned} cannot be used as advertised LAN IP")
    if ip.is_multicast:
        raise ValueError(f"Multicast IP {cleaned} cannot be used as advertised LAN IP")
    return cleaned


def _format_origin(host: str, port: int, scheme: str = "https") -> str:
    """Format scheme://host[:port], omitting default ports (https/443, http/80).

    Keeps parity with request-side ``normalize_origin`` which strips default
    ports, so whitelist entries compare equal without caller changes.
    """
    default_port = 443 if scheme == "https" else 80
    if port == default_port:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def derive_origin_whitelist(
    version: AppliedNetworkAccessVersion,
) -> list[str]:
    """Derive allowed origin URLs strictly from the applied network access version (HTTPS only).
    Port is taken directly from version.config.https_port (single source of truth).
    Default HTTPS port 443 is normalized to the port-less form to match
    request-side normalization; non-default ports are kept.
    """
    port = version.config.https_port
    origins = [
        _format_origin("127.0.0.1", port),
        _format_origin("localhost", port),
    ]
    if version.config.lan_access_enabled and version.config.lan_advertised_ip:
        lan_ip = version.config.lan_advertised_ip.strip()
        origins.append(_format_origin(lan_ip, port))
    return origins


def create_default_applied_version(
    https_port: int = DEFAULT_HTTPS_PORT,
) -> AppliedNetworkAccessVersion:
    """Create default immutable baseline version 1 (local-only, single source of port)."""
    cfg = NetworkAccessConfig(lan_access_enabled=False, https_port=https_port)
    ver = AppliedNetworkAccessVersion(
        version=1,
        config=cfg,
        bind_host="127.0.0.1",
        applied_at=utc_now_iso(),
        caddyfile_sha256="",
        origin_whitelist=[],
    )
    ver.origin_whitelist = derive_origin_whitelist(ver)
    return ver


def generate_caddyfile(
    version: AppliedNetworkAccessVersion,
    api_upstream: str = "http://api:8000",
    gateway_upstream: str = "http://gateway:18080",
    frontend_dir: str = "/var/www/html",
) -> str:
    """Deterministically generate a Caddyfile based strictly on the applied version.
    No hardcoded machine names or static external IPs.
    """
    is_lan = version.config.lan_access_enabled and bool(version.config.lan_advertised_ip)
    default_sni = version.config.lan_advertised_ip.strip() if is_lan else "127.0.0.1"

    site_addresses = ["https://127.0.0.1", "https://localhost"]
    if is_lan and version.config.lan_advertised_ip:
        site_addresses.append(f"https://{version.config.lan_advertised_ip.strip()}")

    sites_line = ", ".join(site_addresses)

    caddyfile = f"""{{
    admin off
    auto_https disable_redirects
    default_sni {default_sni}
}}

{sites_line} {{
    tls internal

    handle /api/* {{
        reverse_proxy {api_upstream}
    }}

    handle /stream/* {{
        reverse_proxy {gateway_upstream}
    }}

    handle {{
        root * {frontend_dir}
        try_files {{path}} /index.html
        file_server
    }}
}}
"""
    return caddyfile


def compute_caddyfile_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_applied_network_state(
    export_dir: Path,
    version: AppliedNetworkAccessVersion,
    caddyfile_content: str,
) -> None:
    """Atomic write applied version and Caddyfile to the shared directory with 0600/0644 permissions."""
    export_dir.mkdir(parents=True, exist_ok=True)
    version_file = export_dir / APPLIED_VERSION_FILENAME
    caddy_file = export_dir / CADDYFILE_FILENAME

    atomic_write_text(
        version_file, version.model_dump_json(indent=2), mode=0o644
    )
    atomic_write_text(caddy_file, caddyfile_content, mode=0o644)


def read_applied_network_state(
    export_dir: Path,
) -> tuple[AppliedNetworkAccessVersion, str] | None:
    """Read exported applied version and Caddyfile from shared directory if present."""
    version_file = export_dir / APPLIED_VERSION_FILENAME
    caddy_file = export_dir / CADDYFILE_FILENAME
    if not version_file.is_file() or not caddy_file.is_file():
        return None
    try:
        data = json.loads(version_file.read_text(encoding="utf-8"))
        ver = AppliedNetworkAccessVersion.model_validate(data)
        caddy_text = caddy_file.read_text(encoding="utf-8")
        return ver, caddy_text
    except Exception as e:
        logger.warning("Failed to read applied network state from %s: %s", export_dir, e)
        return None
