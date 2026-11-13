"""A4: Agent registration throttle keys on the resolved transport source."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer
from cbrowser.gateway.config import GatewayConfig
from cbrowser.gateway.server import create_gateway_app
from cbrowser.stream_agent.protocol import AgentRegisterEnvelope, AgentRegisterPayload
from cbrowser.shared.agent_credentials import AgentCredentials

_URL = "/stream/agent/register?profile_id=p1&runtime_instance_id=inst-1"


class _StubApi:
    async def get_profile_runtime(self, profile_id):
        return {"runtime_instance_id": "inst-1", "observed_state": "running"}

    async def close(self):
        return None


def _build(tmp_path: Path, monkeypatch, trusted_raw):
    key_file = tmp_path / "agent.key"
    key_file.write_text("k" * 40, encoding="utf-8")
    key_file.chmod(0o600)
    token_file = tmp_path / "gateway.token"
    token_file.write_text("t" * 40, encoding="utf-8")
    token_file.chmod(0o600)
    api_token_file = tmp_path / "api.token"
    api_token_file.write_text("a" * 40, encoding="utf-8")
    api_token_file.chmod(0o600)
    monkeypatch.setenv("CBROWSER_TRUSTED_PROXY_CIDRS", trusted_raw)
    config = GatewayConfig(
        agent_key_file=key_file,
        gateway_token_file=token_file,
        api_url="http://127.0.0.1:1",
        api_token_file=api_token_file,
        viewer_grant_key_file=api_token_file,
    )
    app = create_gateway_app(config, api_client=_StubApi())
    return TestClient(TestServer(app)), key_file


def _headers(token, xff):
    return {"Authorization": f"Bearer {token}", "X-Forwarded-For": xff}


async def _attempt(client, xff=None, token="invalid"):
    headers = {"Authorization": f"Bearer {token}"}
    if xff is not None:
        headers["X-Forwarded-For"] = xff
    response = await client.get(_URL, headers=headers)
    status = response.status
    await response.read()
    return status


async def _successful_register(client, token, xff):
    ws = await client.ws_connect(_URL, headers=_headers(token, xff))
    register = AgentRegisterEnvelope(
        profile_id="p1",
        runtime_instance_id="inst-1",
        payload=AgentRegisterPayload(
            hostname="test",
            profile_id="p1",
            runtime_instance_id="inst-1",
            udp_port=30006,
            selkies_version="2.1.0",
            runtime_state="ready",
            config_version=1,
        ),
    )
    await ws.send_str(register.model_dump_json())
    ack = json.loads(await asyncio.wait_for(ws.receive_str(), timeout=5))
    assert ack["status"] == "ok"
    await ws.close()


@pytest.mark.asyncio
async def test_registration_source_only_buckets_isolate_two_sources(tmp_path, monkeypatch):
    client, _ = _build(tmp_path, monkeypatch, "127.0.0.1/32,::1/128")
    async with client:
        for _ in range(20):
            assert await _attempt(client, "203.0.113.10") == 401
        assert await _attempt(client, "203.0.113.10") == 429
        assert await _attempt(client, "203.0.113.11") == 401


@pytest.mark.asyncio
async def test_registration_reservation_released_on_rejection_with_resolved_source(
    tmp_path, monkeypatch
):
    client, _ = _build(tmp_path, monkeypatch, "127.0.0.1/32,::1/128")
    async with client:
        for _ in range(6):
            assert await _attempt(client, "203.0.113.10") == 401


@pytest.mark.asyncio
async def test_registration_direct_peer_keeps_transport_ip(tmp_path, monkeypatch):
    client, _ = _build(tmp_path, monkeypatch, "")
    async with client:
        for index in range(20):
            assert await _attempt(client, f"203.0.113.{10 + index % 5}") == 401
        assert await _attempt(client, "203.0.113.99") == 429


@pytest.mark.asyncio
async def test_registration_success_releases_reservation(tmp_path, monkeypatch):
    client, key_file = _build(tmp_path, monkeypatch, "127.0.0.1/32,::1/128")
    token = AgentCredentials(key_file).token_for("p1", "inst-1")
    async with client:
        for _ in range(3):
            await _successful_register(client, token, "203.0.113.10")
        for _ in range(6):
            assert await _attempt(client, "203.0.113.10") == 401


@pytest.mark.asyncio
async def test_registration_cancel_releases_reservation(tmp_path, monkeypatch):
    client, key_file = _build(tmp_path, monkeypatch, "127.0.0.1/32,::1/128")
    token = AgentCredentials(key_file).token_for("p1", "inst-1")
    async with client:
        for _ in range(3):
            ws = await client.ws_connect(_URL, headers=_headers(token, "203.0.113.10"))
            await ws.close()
        for _ in range(6):
            assert await _attempt(client, "203.0.113.10") == 401


@pytest.mark.asyncio
async def test_registration_timeout_releases_reservation(tmp_path, monkeypatch):
    import cbrowser.gateway.server as server

    client, key_file = _build(tmp_path, monkeypatch, "127.0.0.1/32,::1/128")
    token = AgentCredentials(key_file).token_for("p1", "inst-1")
    original_wait_for = asyncio.wait_for

    class _Shim:
        async def wait_for(self, awaitable, timeout):
            return await original_wait_for(awaitable, min(timeout, 0.05))

        def __getattr__(self, name):
            return getattr(asyncio, name)

    monkeypatch.setattr(server, "asyncio", _Shim())
    async with client:
        for _ in range(3):
            ws = await client.ws_connect(_URL, headers=_headers(token, "203.0.113.10"))
            await asyncio.sleep(0.2)
            await ws.close()
        for _ in range(6):
            assert await _attempt(client, "203.0.113.10") == 401
