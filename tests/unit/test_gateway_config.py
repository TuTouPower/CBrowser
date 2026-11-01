"""Unit tests for Gateway configuration validation."""

import secrets
from pathlib import Path

import pytest
from cbrowser.gateway.config import GatewayConfig


def test_gateway_config_from_env_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_key_file = tmp_path / "agent_key.txt"
    agent_key_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    agent_key_file.chmod(0o600)

    gw_token_file = tmp_path / "gw_token.txt"
    gw_token_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    gw_token_file.chmod(0o600)

    api_token_file = tmp_path / "api_token.txt"
    api_token_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    api_token_file.chmod(0o600)

    turn_secret_file = tmp_path / "turn_secret.txt"
    turn_secret_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    turn_secret_file.chmod(0o600)

    monkeypatch.setenv("CBROWSER_AGENT_KEY_FILE", str(agent_key_file))
    monkeypatch.setenv("CBROWSER_GATEWAY_TOKEN_FILE", str(gw_token_file))
    monkeypatch.setenv("CBROWSER_GATEWAY_API_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("CBROWSER_GATEWAY_API_TOKEN_FILE", str(api_token_file))
    monkeypatch.setenv(
        "CBROWSER_ALLOWED_ORIGINS", "https://localhost:8443,http://127.0.0.1:3000"
    )
    monkeypatch.setenv("CBROWSER_TURN_SECRET_FILE", str(turn_secret_file))
    monkeypatch.setenv("CBROWSER_WEBRTC_MODE", "relay-only")
    monkeypatch.setenv(
        "CBROWSER_TURN_PUBLIC_URLS", "turn:turn.example.com:3478?transport=udp"
    )

    cfg = GatewayConfig.from_env()

    assert cfg.api_url == "http://127.0.0.1:8000"
    assert cfg.webrtc_mode == "relay-only"
    assert cfg.allowed_origins == ["https://localhost:8443", "http://127.0.0.1:3000"]
    assert cfg.turn_public_urls == ["turn:turn.example.com:3478?transport=udp"]
    assert cfg.credential_lifetime_sec == 86400.0
    assert cfg.generation_interval_sec == 43200.0
    assert cfg.ice_restart_lead_time_sec == 21600.0
    assert not hasattr(cfg, "stream_turn_urls")


def test_gateway_config_no_turn_stream_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_key_file = tmp_path / "agent_key.txt"
    agent_key_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    agent_key_file.chmod(0o600)
    gw_token_file = tmp_path / "gw_token.txt"
    gw_token_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    gw_token_file.chmod(0o600)
    api_token_file = tmp_path / "api_token.txt"
    api_token_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    api_token_file.chmod(0o600)
    turn_secret_file = tmp_path / "turn_secret.txt"
    turn_secret_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    turn_secret_file.chmod(0o600)

    monkeypatch.setenv("CBROWSER_AGENT_KEY_FILE", str(agent_key_file))
    monkeypatch.setenv("CBROWSER_GATEWAY_TOKEN_FILE", str(gw_token_file))
    monkeypatch.setenv("CBROWSER_GATEWAY_API_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("CBROWSER_GATEWAY_API_TOKEN_FILE", str(api_token_file))
    monkeypatch.setenv("CBROWSER_ALLOWED_ORIGINS", "https://localhost:8443")
    monkeypatch.setenv("CBROWSER_TURN_SECRET_FILE", str(turn_secret_file))
    monkeypatch.setenv("CBROWSER_WEBRTC_MODE", "public")
    monkeypatch.setenv("CBROWSER_TURN_PUBLIC_URLS", "turn:turn.example.com:3478")
    monkeypatch.setenv("CBROWSER_TURN_STREAM_URLS", "turn:custom:3478")

    cfg = GatewayConfig.from_env()
    assert not hasattr(cfg, "stream_turn_urls")


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
    monkeypatch.setenv("CBROWSER_TURN_SECRET_FILE", str(tmp_path / "dummy.txt"))
    monkeypatch.setenv("CBROWSER_WEBRTC_MODE", "public")
    monkeypatch.setenv("CBROWSER_TURN_PUBLIC_URLS", "turn:turn.example.com:3478")

    with pytest.raises(ValueError, match="at least 32 bytes"):
        GatewayConfig.from_env()


def test_gateway_config_normalizes_trailing_slash_origins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_key_file = tmp_path / "agent_key.txt"
    agent_key_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    agent_key_file.chmod(0o600)
    gw_token_file = tmp_path / "gw_token.txt"
    gw_token_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    gw_token_file.chmod(0o600)
    api_token_file = tmp_path / "api_token.txt"
    api_token_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    api_token_file.chmod(0o600)
    turn_secret_file = tmp_path / "turn_secret.txt"
    turn_secret_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    turn_secret_file.chmod(0o600)

    monkeypatch.setenv("CBROWSER_AGENT_KEY_FILE", str(agent_key_file))
    monkeypatch.setenv("CBROWSER_GATEWAY_TOKEN_FILE", str(gw_token_file))
    monkeypatch.setenv("CBROWSER_GATEWAY_API_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("CBROWSER_GATEWAY_API_TOKEN_FILE", str(api_token_file))
    monkeypatch.setenv("CBROWSER_ALLOWED_ORIGINS", "https://app.example.com/")
    monkeypatch.setenv("CBROWSER_TURN_SECRET_FILE", str(turn_secret_file))
    monkeypatch.setenv("CBROWSER_WEBRTC_MODE", "public")
    monkeypatch.setenv("CBROWSER_TURN_PUBLIC_URLS", "turn:turn.example.com:3478")

    cfg = GatewayConfig.from_env()
    assert cfg.port == 18080
    assert cfg.allowed_origins == ["https://app.example.com"]
