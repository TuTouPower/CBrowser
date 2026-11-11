"""t054: deploy-time network configuration (ADR 031).

The network configuration is a deploy-time input, not a runtime setting:
the HTTPS port comes from the deployment environment, the Caddyfile is
rendered once by deploy.sh, and API + Gateway derive the Origin whitelist
from the same port. There is no LAN mode, no runtime apply path, and no
on-disk applied-state file beyond the Caddyfile itself.
"""

from __future__ import annotations

import hashlib

import pytest

from cbrowser.network_config import (
    CADDYFILE_FILENAME,
    DEFAULT_HTTPS_PORT,
    compute_caddyfile_sha256,
    derive_origin_whitelist,
    generate_caddyfile,
)


def test_default_https_port_is_the_single_constant() -> None:
    assert DEFAULT_HTTPS_PORT == 56661


def test_origin_whitelist_is_loopback_only_with_port() -> None:
    assert derive_origin_whitelist(56661) == [
        "https://127.0.0.1:56661",
        "https://localhost:56661",
    ]
    assert derive_origin_whitelist(8443) == [
        "https://127.0.0.1:8443",
        "https://localhost:8443",
    ]


def test_origin_whitelist_normalizes_default_https_port() -> None:
    assert derive_origin_whitelist(443) == [
        "https://127.0.0.1",
        "https://localhost",
    ]


def test_origin_whitelist_rejects_invalid_ports() -> None:
    for bad in (0, -1, 65536, 100000):
        with pytest.raises(ValueError, match="https_port"):
            derive_origin_whitelist(bad)


def test_caddyfile_is_loopback_only_and_deterministic() -> None:
    first = generate_caddyfile(56661)
    assert generate_caddyfile(56661) == first
    assert "https://127.0.0.1, https://localhost" in first
    assert "default_sni 127.0.0.1" in first
    assert "0.0.0.0" not in first
    assert "192.168." not in first
    assert "10.0.0." not in first


def test_caddyfile_changes_with_port_only() -> None:
    assert generate_caddyfile(56661) != generate_caddyfile(58888)
    assert "56661" not in generate_caddyfile(58888)


def test_caddyfile_honors_upstreams_and_frontend_dir() -> None:
    content = generate_caddyfile(
        56661,
        api_upstream="http://api:8000",
        gateway_upstream="http://gateway:18080",
        frontend_dir="/var/www/html",
    )
    assert "reverse_proxy http://api:8000" in content
    assert "reverse_proxy http://gateway:18080" in content
    assert "root * /var/www/html" in content


def test_caddyfile_sha256_is_plain_sha256() -> None:
    content = generate_caddyfile(56661)
    assert compute_caddyfile_sha256(content) == hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()
    assert CADDYFILE_FILENAME == "Caddyfile"


def test_runtime_apply_surface_is_gone() -> None:
    import cbrowser.network_config as module

    for name in (
        "validate_lan_ip",
        "build_applied_network_version",
        "write_applied_network_state",
        "read_applied_network_state",
        "APPLIED_VERSION_FILENAME",
    ):
        assert not hasattr(module, name), name
