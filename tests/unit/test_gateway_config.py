"""Unit tests for Gateway configuration validation and Origin derivation (t054).

The Origin whitelist is derived from the deployment HTTPS port
(CBROWSER_HTTPS_PORT, default DEFAULT_HTTPS_PORT) — the same input the
API uses. There is no network state directory, no disk baseline, and no
publication handshake anymore: the whitelist is a pure function of the
port, so it cannot drift and cannot be switched at runtime.
"""

import secrets
from pathlib import Path

import pytest
from pydantic import ValidationError

from cbrowser.gateway.config import GatewayConfig


def _set_required_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("agent_key", "gw_token", "api_token"):
        path = tmp_path / f"{name}.txt"
        path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        path.chmod(0o600)
    monkeypatch.setenv("CBROWSER_AGENT_KEY_FILE", str(tmp_path / "agent_key.txt"))
    monkeypatch.setenv("CBROWSER_GATEWAY_TOKEN_FILE", str(tmp_path / "gw_token.txt"))
    monkeypatch.setenv("CBROWSER_GATEWAY_API_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv(
        "CBROWSER_GATEWAY_API_TOKEN_FILE", str(tmp_path / "api_token.txt")
    )
    monkeypatch.setenv("CBROWSER_HTTPS_PORT", "56661")


def _gateway_config(tmp_path: Path, **kwargs) -> GatewayConfig:
    key = tmp_path / "key.txt"
    key.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    key.chmod(0o600)
    return GatewayConfig(
        agent_key_file=key,
        gateway_token_file=key,
        api_url="http://127.0.0.1:8000",
        api_token_file=key,
        **kwargs,
    )


def test_gateway_config_from_env_derives_origins_from_deploy_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_required_env(tmp_path, monkeypatch)

    cfg = GatewayConfig.from_env()

    assert cfg.api_url == "http://127.0.0.1:8000"
    assert cfg.https_port == 56661
    assert cfg.allowed_origins == [
        "https://127.0.0.1:56661",
        "https://localhost:56661",
    ]
    assert cfg.agent_heartbeat_timeout_sec == 30.0


def test_gateway_config_from_env_uses_custom_deploy_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_required_env(tmp_path, monkeypatch)
    monkeypatch.setenv("CBROWSER_HTTPS_PORT", "58888")

    cfg = GatewayConfig.from_env()

    assert cfg.https_port == 58888
    assert cfg.allowed_origins == [
        "https://127.0.0.1:58888",
        "https://localhost:58888",
    ]


def test_gateway_config_explicit_port_wins_over_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CBROWSER_HTTPS_PORT", "56661")
    cfg = _gateway_config(tmp_path, https_port=58888)
    assert cfg.allowed_origins == [
        "https://127.0.0.1:58888",
        "https://localhost:58888",
    ]


def test_gateway_config_defaults_to_default_port_without_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CBROWSER_HTTPS_PORT", raising=False)
    cfg = _gateway_config(tmp_path)
    assert cfg.https_port == 56661
    assert cfg.allowed_origins == [
        "https://127.0.0.1:56661",
        "https://localhost:56661",
    ]


@pytest.mark.parametrize("value", [0, -1, 70000])
def test_gateway_config_rejects_invalid_https_port(
    tmp_path: Path, value
) -> None:
    with pytest.raises(ValidationError, match="https_port"):
        _gateway_config(tmp_path, https_port=value)


def test_gateway_config_has_no_network_state_dir_or_publication(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError):
        _gateway_config(tmp_path, network_state_dir=tmp_path / "network")
    cfg = _gateway_config(tmp_path)
    for name in (
        "authorize_publication",
        "acknowledge_publication",
        "active_publication",
        "revoke_publication",
        "import_baseline_from_disk",
        "note_network_state_mtime",
    ):
        assert not hasattr(cfg, name), name
    assert "network_state_dir" not in GatewayConfig.model_fields


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
