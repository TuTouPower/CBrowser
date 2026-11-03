"""Unit tests for Gateway configuration validation."""

import secrets
from pathlib import Path

import pytest
from cbrowser.gateway.config import GatewayConfig


def _set_required_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("agent_key", "gw_token", "api_token"):
        path = tmp_path / f"{name}.txt"
        path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        path.chmod(0o600)
    monkeypatch.setenv("CBROWSER_AGENT_KEY_FILE", str(tmp_path / "agent_key.txt"))
    monkeypatch.setenv(
        "CBROWSER_GATEWAY_TOKEN_FILE", str(tmp_path / "gw_token.txt")
    )
    monkeypatch.setenv("CBROWSER_GATEWAY_API_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv(
        "CBROWSER_GATEWAY_API_TOKEN_FILE", str(tmp_path / "api_token.txt")
    )
    monkeypatch.setenv(
        "CBROWSER_ALLOWED_ORIGINS", "https://localhost:8443,http://127.0.0.1:3000"
    )


def test_gateway_config_from_env_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_required_env(tmp_path, monkeypatch)

    cfg = GatewayConfig.from_env()

    assert cfg.api_url == "http://127.0.0.1:8000"
    assert cfg.allowed_origins == ["https://localhost:8443", "http://127.0.0.1:3000"]
    assert cfg.agent_heartbeat_timeout_sec == 30.0
    for removed in (
        "webrtc_mode",
        "turn_secret_file",
        "turn_public_urls",
        "credential_lifetime_sec",
        "generation_interval_sec",
        "ice_restart_lead_time_sec",
    ):
        assert not hasattr(cfg, removed)


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

    monkeypatch.setenv("CBROWSER_AGENT_KEY_FILE", str(agent_key_file))
    monkeypatch.setenv("CBROWSER_GATEWAY_TOKEN_FILE", str(tmp_path / "dummy.txt"))
    monkeypatch.setenv("CBROWSER_GATEWAY_API_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("CBROWSER_GATEWAY_API_TOKEN_FILE", str(tmp_path / "dummy.txt"))
    monkeypatch.setenv("CBROWSER_ALLOWED_ORIGINS", "http://localhost:3000")

    with pytest.raises(ValueError, match="at least 32 bytes"):
        GatewayConfig.from_env()


def test_gateway_config_normalizes_trailing_slash_origins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_required_env(tmp_path, monkeypatch)
    monkeypatch.setenv("CBROWSER_ALLOWED_ORIGINS", "https://app.example.com/")

    cfg = GatewayConfig.from_env()
    assert cfg.port == 18080
    assert cfg.allowed_origins == ["https://app.example.com"]
