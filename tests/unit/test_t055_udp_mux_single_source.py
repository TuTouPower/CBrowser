"""t055 A11: the UDP mux range is parsed once, at Supervisor startup.

``udp_mux_bounds()`` is the single source of truth; the runner must use
it instead of self-parsing the environment, so an empty value falls back
to the default and an illegal value fails startup with a clear error.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from cbrowser.supervisor import runner as runner_module


@pytest.fixture
def _fake_docker(monkeypatch):
    client = SimpleNamespace(
        containers=SimpleNamespace(list=lambda **kw: []),
        networks=SimpleNamespace(list=lambda **kw: []),
        close=lambda: None,
    )
    monkeypatch.setattr(runner_module.docker, "from_env", lambda: client)


@pytest.fixture
def _images(monkeypatch):
    monkeypatch.setenv(
        "CBROWSER_BROWSER_IMAGE",
        "sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346",
    )
    monkeypatch.setenv(
        "CBROWSER_STREAM_IMAGE",
        "sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531",
    )


@pytest.fixture
def _fake_serve(monkeypatch):
    served: list = []

    async def _serve(core, host, port):
        served.append(core)

    monkeypatch.setattr(runner_module, "serve_supervisor", _serve)
    return served


def _files(tmp_path: Path):
    (tmp_path / "data" / "engine" / "geoip").mkdir(parents=True)
    agent_key = tmp_path / "agent_key"
    agent_key.write_text("k" * 40, encoding="utf-8")
    agent_key.chmod(0o600)
    gateway_token = tmp_path / "gateway_token"
    gateway_token.write_text("g" * 40, encoding="utf-8")
    gateway_token.chmod(0o600)
    return agent_key, gateway_token


@pytest.mark.asyncio
async def test_empty_mux_env_uses_default_range(
    tmp_path, monkeypatch, _fake_docker, _fake_serve, _images
):
    """AC-008: an empty mux env falls back to the default range."""
    monkeypatch.setenv("CBROWSER_UDP_MUX_MIN_PORT", "")
    monkeypatch.setenv("CBROWSER_UDP_MUX_MAX_PORT", "")
    agent_key, gateway_token = _files(tmp_path)

    await runner_module.run_supervisor(
        api_url="http://api.invalid",
        data_root=tmp_path / "data",
        engine_cache=tmp_path / "data" / "engine",
        agent_key_file=agent_key,
        gateway_control_url="http://gateway.invalid",
        gateway_token_file=gateway_token,
    )

    assert len(_fake_serve) == 1
    assert _fake_serve[0].ports.min_port == 30000
    assert _fake_serve[0].ports.max_port == 30991


@pytest.mark.asyncio
async def test_custom_mux_env_reaches_port_allocator(
    tmp_path, monkeypatch, _fake_docker, _fake_serve, _images
):
    """AC-008: a custom mux range reaches the PortAllocator unchanged."""
    monkeypatch.setenv("CBROWSER_UDP_MUX_MIN_PORT", "31000")
    monkeypatch.setenv("CBROWSER_UDP_MUX_MAX_PORT", "31010")
    agent_key, gateway_token = _files(tmp_path)

    await runner_module.run_supervisor(
        api_url="http://api.invalid",
        data_root=tmp_path / "data",
        engine_cache=tmp_path / "data" / "engine",
        agent_key_file=agent_key,
        gateway_control_url="http://gateway.invalid",
        gateway_token_file=gateway_token,
    )

    assert len(_fake_serve) == 1
    assert _fake_serve[0].ports.min_port == 31000
    assert _fake_serve[0].ports.max_port == 31010


@pytest.mark.asyncio
async def test_inverted_mux_range_fails_startup(
    tmp_path, monkeypatch, _fake_docker, _fake_serve, _images
):
    """AC-008: an inverted range fails Supervisor startup with a clear error."""
    monkeypatch.setenv("CBROWSER_UDP_MUX_MIN_PORT", "31010")
    monkeypatch.setenv("CBROWSER_UDP_MUX_MAX_PORT", "31000")
    agent_key, gateway_token = _files(tmp_path)

    with pytest.raises(ValueError, match="Invalid UDP mux port range"):
        await runner_module.run_supervisor(
            api_url="http://api.invalid",
            data_root=tmp_path / "data",
            engine_cache=tmp_path / "data" / "engine",
            agent_key_file=agent_key,
            gateway_control_url="http://gateway.invalid",
            gateway_token_file=gateway_token,
        )


@pytest.mark.asyncio
async def test_non_integer_mux_env_fails_startup(
    tmp_path, monkeypatch, _fake_docker, _fake_serve, _images
):
    """AC-008: a non-integer mux value fails startup with a clear error."""
    monkeypatch.setenv("CBROWSER_UDP_MUX_MIN_PORT", "abc")
    monkeypatch.delenv("CBROWSER_UDP_MUX_MAX_PORT", raising=False)
    agent_key, gateway_token = _files(tmp_path)

    with pytest.raises(ValueError, match="Invalid integer in CBROWSER_UDP_MUX_MIN_PORT"):
        await runner_module.run_supervisor(
            api_url="http://api.invalid",
            data_root=tmp_path / "data",
            engine_cache=tmp_path / "data" / "engine",
            agent_key_file=agent_key,
            gateway_control_url="http://gateway.invalid",
            gateway_token_file=gateway_token,
        )
