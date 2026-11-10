"""Unit tests for NetworkAccessConfig, Caddyfile generation, and Origin derivation.

t048 replaced every AppliedNetworkAccessVersion fixture that used a placeholder
or empty hash with the single build_applied_network_version entry point: the
model contract now forbids representable unhashed versions, so the old
"construct then mutate the hash" fixtures no longer describe valid state.
"""

import pytest
from pydantic import ValidationError

from cbrowser.domain.models import (
    AppliedNetworkAccessVersion,
    NetworkAccessConfig,
)
from cbrowser.network_config import (
    build_applied_network_version,
    compute_caddyfile_sha256,
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


def test_network_access_config_strips_advertised_ip():
    cfg = NetworkAccessConfig(
        lan_access_enabled=True,
        lan_advertised_ip="  192.168.31.76  ",
    )
    assert cfg.lan_advertised_ip == "192.168.31.76"


def test_derive_origin_whitelist():
    # Loopback only
    whitelist_local = derive_origin_whitelist(
        NetworkAccessConfig(lan_access_enabled=False)
    )
    assert "https://127.0.0.1:56661" in whitelist_local
    assert "https://localhost:56661" in whitelist_local
    assert not any("192.168" in o for o in whitelist_local)

    # LAN enabled
    whitelist_lan = derive_origin_whitelist(
        NetworkAccessConfig(
            lan_access_enabled=True,
            lan_advertised_ip="192.168.31.76",
        )
    )
    assert "https://127.0.0.1:56661" in whitelist_lan
    assert "https://localhost:56661" in whitelist_lan
    assert "https://192.168.31.76:56661" in whitelist_lan


def test_derive_origin_whitelist_default_port_443_omitted():
    whitelist = derive_origin_whitelist(
        NetworkAccessConfig(lan_access_enabled=False, https_port=443)
    )
    assert "https://127.0.0.1" in whitelist
    assert "https://localhost" in whitelist
    assert not any(o.endswith(":443") for o in whitelist)

    whitelist_lan = derive_origin_whitelist(
        NetworkAccessConfig(
            lan_access_enabled=True,
            lan_advertised_ip="192.168.31.76",
            https_port=443,
        )
    )
    assert "https://192.168.31.76" in whitelist_lan
    assert not any(o.endswith(":443") for o in whitelist_lan)


def test_derive_origin_whitelist_non_default_port_kept():
    whitelist = derive_origin_whitelist(
        NetworkAccessConfig(lan_access_enabled=False, https_port=8443)
    )
    assert "https://127.0.0.1:8443" in whitelist
    assert "https://localhost:8443" in whitelist


def test_generate_caddyfile():
    caddy_v1 = generate_caddyfile(
        NetworkAccessConfig(lan_access_enabled=False),
        api_upstream="http://api:8000",
        gateway_upstream="http://gateway:18080",
    )
    assert "default_sni 127.0.0.1" in caddy_v1
    assert "https://127.0.0.1" in caddy_v1
    assert "reverse_proxy http://api:8000" in caddy_v1
    assert "reverse_proxy http://gateway:18080" in caddy_v1
    assert "192.168" not in caddy_v1

    caddy_v2 = generate_caddyfile(
        NetworkAccessConfig(
            lan_access_enabled=True,
            lan_advertised_ip="192.168.31.76",
        ),
        api_upstream="http://api:8000",
        gateway_upstream="http://gateway:18080",
    )
    assert "default_sni 192.168.31.76" in caddy_v2
    assert "https://192.168.31.76" in caddy_v2
    assert "https://127.0.0.1" in caddy_v2


def test_applied_network_version_requires_complete_lowercase_hash():
    def payload(sha: object) -> dict[str, object]:
        data: dict[str, object] = {
            "version": 1,
            "config": {"lan_access_enabled": False},
            "applied_at": "2026-11-08T00:00:00+08:00",
            "origin_whitelist": ["https://127.0.0.1:56661"],
        }
        if sha is not None:
            data["caddyfile_sha256"] = sha
        return data

    for bad in ("", "dummy", "0" * 63, "0" * 65, "A" * 64, "g" * 64):
        with pytest.raises(ValidationError):
            AppliedNetworkAccessVersion.model_validate(payload(bad))

    # Missing field is also rejected: no implicit empty default survives.
    with pytest.raises(ValidationError):
        AppliedNetworkAccessVersion.model_validate(payload(None))

    # Deserialization path rejects the legacy empty-hash shape too.
    import json

    with pytest.raises(ValidationError):
        AppliedNetworkAccessVersion.model_validate_json(json.dumps(payload("")))

    valid = AppliedNetworkAccessVersion.model_validate(payload("a" * 64))
    assert valid.caddyfile_sha256 == "a" * 64


def test_build_applied_network_version_is_complete_and_consistent():
    configs = [
        NetworkAccessConfig(lan_access_enabled=False),
        NetworkAccessConfig(
            lan_access_enabled=True,
            lan_advertised_ip="192.168.31.76",
        ),
        NetworkAccessConfig(lan_access_enabled=False, https_port=8443),
    ]
    for index, cfg in enumerate(configs, start=1):
        version, caddyfile = build_applied_network_version(cfg, version=index)
        assert version.version == index
        assert caddyfile == generate_caddyfile(cfg)
        assert version.caddyfile_sha256 == compute_caddyfile_sha256(caddyfile)
        assert version.origin_whitelist == derive_origin_whitelist(cfg)
        assert version.bind_host == (
            "0.0.0.0" if cfg.lan_access_enabled else "127.0.0.1"
        )

    custom, custom_caddyfile = build_applied_network_version(
        NetworkAccessConfig(lan_access_enabled=False),
        version=9,
        api_upstream="http://api.internal:9000",
        gateway_upstream="http://gateway.internal:19000",
    )
    assert "reverse_proxy http://api.internal:9000" in custom_caddyfile
    assert "reverse_proxy http://gateway.internal:19000" in custom_caddyfile
    assert custom.caddyfile_sha256 == compute_caddyfile_sha256(custom_caddyfile)
