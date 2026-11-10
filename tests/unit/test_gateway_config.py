"""Unit tests for Gateway configuration validation and applied origin derivation (t042 AC-007)."""

import secrets
from pathlib import Path
import pytest

from cbrowser.domain.models import AppliedNetworkAccessVersion, NetworkAccessConfig, utc_now_iso
from cbrowser.gateway.config import GatewayConfig
from cbrowser.network_config import write_applied_network_state


def _set_required_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("agent_key", "gw_token", "api_token"):
        path = tmp_path / f"{name}.txt"
        path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        path.chmod(0o600)
    monkeypatch.setenv("CBROWSER_AGENT_KEY_FILE", str(tmp_path / "agent_key.txt"))
    monkeypatch.setenv("CBROWSER_GATEWAY_TOKEN_FILE", str(tmp_path / "gw_token.txt"))
    monkeypatch.setenv("CBROWSER_GATEWAY_API_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("CBROWSER_GATEWAY_API_TOKEN_FILE", str(tmp_path / "api_token.txt"))
    monkeypatch.setenv("CBROWSER_NETWORK_STATE_DIR", str(tmp_path / "network"))
    monkeypatch.setenv("CBROWSER_HTTPS_PORT", "56661")


def test_gateway_config_from_env_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_required_env(tmp_path, monkeypatch)

    cfg = GatewayConfig.from_env()

    assert cfg.api_url == "http://127.0.0.1:8000"
    # When network state file doesn't exist, origins is empty (fails closed per supervisory directive)
    assert cfg.allowed_origins == []
    assert cfg.agent_heartbeat_timeout_sec == 30.0


def _gateway_config(tmp_path: Path, net_dir: Path) -> GatewayConfig:
    key = tmp_path / "key.txt"
    key.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    key.chmod(0o600)
    return GatewayConfig(
        agent_key_file=key,
        gateway_token_file=key,
        api_url="http://127.0.0.1:8000",
        api_token_file=key,
        network_state_dir=net_dir,
    )


def test_gateway_baseline_is_explicit_and_mtime_does_not_switch(tmp_path: Path) -> None:
    net_dir = tmp_path / "network"
    net_dir.mkdir(parents=True, exist_ok=True)
    v1 = AppliedNetworkAccessVersion(
        version=1,
        config=NetworkAccessConfig(lan_access_enabled=False),
        applied_at=utc_now_iso(),
        caddyfile_sha256="1" * 64,
        origin_whitelist=["https://127.0.0.1:56661", "https://localhost:56661"],
    )
    write_applied_network_state(net_dir, v1, "dummy caddyfile 1")

    cfg = _gateway_config(tmp_path, net_dir)
    assert "https://127.0.0.1:56661" in cfg.allowed_origins

    v2 = AppliedNetworkAccessVersion(
        version=2,
        config=NetworkAccessConfig(
            lan_access_enabled=True, lan_advertised_ip="192.168.31.76"
        ),
        applied_at=utc_now_iso(),
        caddyfile_sha256="2" * 64,
        origin_whitelist=["https://127.0.0.1:56661", "https://192.168.31.76:56661"],
    )
    write_applied_network_state(net_dir, v2, "dummy caddyfile 2")

    assert "https://192.168.31.76:56661" not in cfg.allowed_origins
    assert cfg.active_publication()["operation_id"] == "baseline"


def test_gateway_requires_authorized_ack_to_activate_new_origins(
    tmp_path: Path,
) -> None:
    net_dir = tmp_path / "network"
    net_dir.mkdir(parents=True, exist_ok=True)
    v1 = AppliedNetworkAccessVersion(
        version=1,
        config=NetworkAccessConfig(lan_access_enabled=False),
        applied_at=utc_now_iso(),
        caddyfile_sha256="1" * 64,
        origin_whitelist=["https://127.0.0.1:56661"],
    )
    write_applied_network_state(net_dir, v1, "dummy caddyfile 1")
    cfg = _gateway_config(tmp_path, net_dir)

    cfg.authorize_publication(
        "op-1", 3, "candidate-hash", ["https://lan.example:56661"]
    )
    assert "https://lan.example:56661" not in cfg.allowed_origins
    ack = cfg.acknowledge_publication("op-1", 3, "candidate-hash")
    assert ack["acked"] is True
    assert "https://lan.example:56661" in cfg.allowed_origins
    assert cfg.active_publication()["generation"] == 3

    cfg.revoke_publication("op-1")
    assert "https://lan.example:56661" not in cfg.allowed_origins
    assert "https://127.0.0.1:56661" in cfg.allowed_origins


def test_gateway_authorize_rejects_stale_generation(tmp_path: Path) -> None:
    from cbrowser.gateway.config import NetworkPublicationAuthority

    authority = NetworkPublicationAuthority()
    authority.import_baseline(
        ["https://127.0.0.1:56661"], generation=0, snapshot_hash="base"
    )
    assert authority.authorize("op-new", 4, "hash-new", ["https://lan:56661"])[
        "authorized"
    ] is True
    assert authority.acknowledge("op-new", 4, "hash-new")["acked"] is True

    stale = authority.authorize("op-stale", 3, "hash-stale", ["https://evil:56661"])
    assert stale["authorized"] is False
    assert authority.acknowledge("op-stale", 3, "hash-stale")["acked"] is False
    assert "https://lan:56661" in authority.active()["origins"]


def test_gateway_mtime_is_only_a_reread_hint_for_active_publication(
    tmp_path: Path,
) -> None:
    net_dir = tmp_path / "network"
    net_dir.mkdir(parents=True, exist_ok=True)
    v1 = AppliedNetworkAccessVersion(
        version=1,
        config=NetworkAccessConfig(lan_access_enabled=False),
        applied_at=utc_now_iso(),
        caddyfile_sha256="1" * 64,
        origin_whitelist=["https://127.0.0.1:56661"],
    )
    write_applied_network_state(net_dir, v1, "dummy caddyfile 1")
    cfg = _gateway_config(tmp_path, net_dir)

    before = cfg.active_publication()
    v2 = v1.model_copy(
        update={
            "version": 2,
            "origin_whitelist": ["https://192.168.31.76:56661"],
        }
    )
    write_applied_network_state(net_dir, v2, "dummy caddyfile 2")
    _ = cfg.allowed_origins

    assert cfg.active_publication() == before
    assert "https://192.168.31.76:56661" not in cfg.active_publication()["origins"]


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_gateway_config_rejects_invalid_heartbeat_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    _set_required_env(tmp_path, monkeypatch)
    monkeypatch.setenv("CBROWSER_AGENT_HEARTBEAT_TIMEOUT_SEC", value)
    with pytest.raises(ValueError, match="finite positive"):
        GatewayConfig.from_env()


def test_gateway_config_missing_env_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CBROWSER_AGENT_KEY_FILE", raising=False)
    with pytest.raises(ValueError, match="CBROWSER_AGENT_KEY_FILE"):
        GatewayConfig.from_env()


def test_gateway_config_short_secret_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_key_file = tmp_path / "agent_key.txt"
    agent_key_file.write_text("too_short", encoding="utf-8")
    agent_key_file.chmod(0o600)

    dummy = tmp_path / "dummy.txt"
    dummy.write_text("d" * 40, encoding="utf-8")
    dummy.chmod(0o600)
    monkeypatch.setenv("CBROWSER_AGENT_KEY_FILE", str(agent_key_file))
    monkeypatch.setenv("CBROWSER_GATEWAY_TOKEN_FILE", str(dummy))
    monkeypatch.setenv("CBROWSER_GATEWAY_API_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("CBROWSER_GATEWAY_API_TOKEN_FILE", str(dummy))

    with pytest.raises(ValueError, match="at least 32 bytes"):
        GatewayConfig.from_env()
