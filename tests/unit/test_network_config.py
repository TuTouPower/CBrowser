"""Unit tests for NetworkAccessConfig, Caddyfile generation, and Origin derivation."""

import ipaddress
import pytest
from pydantic import ValidationError

from cbrowser.domain.models import (
    AppliedNetworkAccessVersion,
    NetworkAccessConfig,
    NetworkApplyPhase,
)
from cbrowser.network_config import (
    derive_origin_whitelist,
    generate_caddyfile,
    validate_lan_ip,
)


def test_validate_lan_ip():
    assert validate_lan_ip("192.168.1.100") == "192.168.1.100"
    assert validate_lan_ip("10.0.0.1") == "10.0.0.1"
    assert validate_lan_ip("172.16.0.5") == "172.16.0.5"

    with pytest.raises(ValueError, match="Invalid IPv4 address"):
        validate_lan_ip("not-an-ip")
    with pytest.raises(ValueError, match="Loopback IP"):
        validate_lan_ip("127.0.0.1")
    with pytest.raises(ValueError, match="Unspecified"):
        validate_lan_ip("0.0.0.0")
    with pytest.raises(ValueError, match="Multicast"):
        validate_lan_ip("224.0.0.1")


def test_network_access_config_validation():
    # Default is disabled, lan_advertised_ip can be None
    cfg = NetworkAccessConfig(lan_access_enabled=False)
    assert not cfg.lan_access_enabled
    assert cfg.lan_advertised_ip is None

    # Enabled requires valid non-loopback IPv4
    cfg_enabled = NetworkAccessConfig(
        lan_access_enabled=True,
        lan_advertised_ip="192.168.31.76",
    )
    assert cfg_enabled.lan_access_enabled
    assert cfg_enabled.lan_advertised_ip == "192.168.31.76"

    # Enabled with missing advertised IP raises ValidationError
    with pytest.raises(ValidationError):
        NetworkAccessConfig(lan_access_enabled=True, lan_advertised_ip=None)

    # Enabled with invalid IP raises ValidationError
    with pytest.raises(ValidationError):
        NetworkAccessConfig(lan_access_enabled=True, lan_advertised_ip="127.0.0.1")


def test_derive_origin_whitelist():
    # Loopback only
    v1 = AppliedNetworkAccessVersion(
        version=1,
        config=NetworkAccessConfig(lan_access_enabled=False),
        applied_at="2026-11-08T00:00:00+08:00",
        caddyfile_sha256="dummy",
        origin_whitelist=[],
    )
    whitelist_local = derive_origin_whitelist(v1)
    assert "https://127.0.0.1:56661" in whitelist_local
    assert "https://localhost:56661" in whitelist_local
    assert not any("192.168" in o for o in whitelist_local)

    # LAN enabled
    v2 = AppliedNetworkAccessVersion(
        version=2,
        config=NetworkAccessConfig(
            lan_access_enabled=True,
            lan_advertised_ip="192.168.31.76",
        ),
        applied_at="2026-11-08T00:01:00+08:00",
        caddyfile_sha256="dummy",
        origin_whitelist=[],
    )
    whitelist_lan = derive_origin_whitelist(v2)
    assert "https://127.0.0.1:56661" in whitelist_lan
    assert "https://localhost:56661" in whitelist_lan
    assert "https://192.168.31.76:56661" in whitelist_lan


def test_generate_caddyfile():
    v1 = AppliedNetworkAccessVersion(
        version=1,
        config=NetworkAccessConfig(lan_access_enabled=False),
        applied_at="2026-11-08T00:00:00+08:00",
        caddyfile_sha256="dummy",
        origin_whitelist=[],
    )
    caddy_v1 = generate_caddyfile(
        version=v1,
        api_upstream="http://api:8000",
        gateway_upstream="http://gateway:18080",
    )
    assert "default_sni 127.0.0.1" in caddy_v1
    assert "https://127.0.0.1" in caddy_v1
    assert "reverse_proxy http://api:8000" in caddy_v1
    assert "reverse_proxy http://gateway:18080" in caddy_v1
    assert "192.168" not in caddy_v1

    v2 = AppliedNetworkAccessVersion(
        version=2,
        config=NetworkAccessConfig(
            lan_access_enabled=True,
            lan_advertised_ip="192.168.31.76",
        ),
        applied_at="2026-11-08T00:01:00+08:00",
        caddyfile_sha256="dummy",
        origin_whitelist=[],
    )
    caddy_v2 = generate_caddyfile(
        version=v2,
        api_upstream="http://api:8000",
        gateway_upstream="http://gateway:18080",
    )
    assert "default_sni 192.168.31.76" in caddy_v2
    assert "https://192.168.31.76" in caddy_v2
    assert "https://127.0.0.1" in caddy_v2
