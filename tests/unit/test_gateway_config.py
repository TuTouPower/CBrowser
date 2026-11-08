"""Unit tests for Gateway configuration validation and applied origin derivation (t042 AC-007)."""

import json
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


def test_gateway_config_derives_origins_from_applied_state_and_reloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """t042 AC-007: Gateway reads origin whitelist from the single applied network version file,
    and hot-reloads when the file is updated upon mode switch."""
    _set_required_env(tmp_path, monkeypatch)
    net_dir = tmp_path / "network"
    net_dir.mkdir(parents=True, exist_ok=True)

    # 1. Initial applied state (Local only)
    v1 = AppliedNetworkAccessVersion(
        version=1,
        config=NetworkAccessConfig(lan_access_enabled=False),
        applied_at=utc_now_iso(),
        caddyfile_sha256="hash1",
        origin_whitelist=["https://127.0.0.1:56661", "https://localhost:56661"],
    )
    write_applied_network_state(net_dir, v1, "dummy caddyfile 1")

    cfg = GatewayConfig.from_env()
    assert cfg.allowed_origins == ["https://127.0.0.1:56661", "https://localhost:56661"]

    # 2. Mode switch: write new applied state with LAN IP
    v2 = AppliedNetworkAccessVersion(
        version=2,
        config=NetworkAccessConfig(lan_access_enabled=True, lan_advertised_ip="192.168.31.76"),
        applied_at=utc_now_iso(),
        caddyfile_sha256="hash2",
        origin_whitelist=[
            "https://127.0.0.1:56661",
            "https://localhost:56661",
            "https://192.168.31.76:56661",
        ],
    )
    import time
    time.sleep(0.05)  # Ensure mtime increments
    write_applied_network_state(net_dir, v2, "dummy caddyfile 2")

    # Gateway dynamically reflects new origin whitelist without restarting (AC-007)
    assert "https://192.168.31.76:56661" in cfg.allowed_origins


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
