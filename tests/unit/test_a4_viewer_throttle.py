"""A4: Viewer authorization throttle keeps (source, profile_id) buckets behind a trusted proxy."""

from __future__ import annotations

import pytest
from aiohttp.test_utils import TestClient, TestServer
from cbrowser.shared.client_ip import (
    parse_trusted_proxy_cidrs,
    resolve_client_ip,
)
from cbrowser.gateway.config import GatewayConfig
from cbrowser.gateway.server import create_gateway_app


class _StubApi:
    async def get_profile_runtime(self, profile_id):
        return {"runtime_instance_id": "inst-1", "observed_state": "running"}

    async def close(self):
        return None


def _build(tmp_path, monkeypatch, trusted_raw):
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
    return TestClient(TestServer(app))


async def _probe(client, profile_id, xff=None):
    headers = {"X-Forwarded-For": xff} if xff is not None else {}
    response = await client.get(f"/stream/{profile_id}/signal", headers=headers)
    status = response.status
    await response.read()
    return status


@pytest.mark.asyncio
async def test_viewer_same_profile_different_sources_are_isolated(tmp_path, monkeypatch):
    async with _build(tmp_path, monkeypatch, "127.0.0.1/32,::1/128") as client:
        for _ in range(10):
            assert await _probe(client, "p1", "203.0.113.10") == 403
        assert await _probe(client, "p1", "203.0.113.10") == 429
        assert await _probe(client, "p1", "203.0.113.11") == 403


@pytest.mark.asyncio
async def test_viewer_bucket_is_source_and_profile_not_source_only(tmp_path, monkeypatch):
    async with _build(tmp_path, monkeypatch, "127.0.0.1/32,::1/128") as client:
        for _ in range(10):
            assert await _probe(client, "p1", "203.0.113.10") == 403
        assert await _probe(client, "p1", "203.0.113.10") == 429
        assert await _probe(client, "p2", "203.0.113.10") == 403


@pytest.mark.asyncio
async def test_viewer_xff_chain_resolves_trusted_hops(tmp_path, monkeypatch):
    async with _build(tmp_path, monkeypatch, "127.0.0.1/32,::1/128") as client:
        for _ in range(10):
            assert await _probe(client, "p1", "203.0.113.10, 127.0.0.1") == 403
        assert await _probe(client, "p1", "203.0.113.10, 127.0.0.1") == 429
        assert await _probe(client, "p1", "203.0.113.11, 127.0.0.1") == 403


@pytest.mark.asyncio
async def test_viewer_untrusted_peer_ignores_spoofed_xff(tmp_path, monkeypatch):
    async with _build(tmp_path, monkeypatch, "198.51.100.0/24") as client:
        for _ in range(10):
            assert await _probe(client, "p1", "203.0.113.10") == 403
        assert await _probe(client, "p1", "203.0.113.10") == 429
        assert await _probe(client, "p1", "203.0.113.11") == 429


@pytest.mark.asyncio
async def test_viewer_threshold_is_ten_failures(tmp_path, monkeypatch):
    async with _build(tmp_path, monkeypatch, "127.0.0.1/32,::1/128") as client:
        for _ in range(9):
            assert await _probe(client, "p1", "203.0.113.10") == 403
        assert await _probe(client, "p1", "203.0.113.10") == 403
        assert await _probe(client, "p1", "203.0.113.10") == 429

def test_shared_direct_peer_keeps_verifiable_transport_ip():
    networks = parse_trusted_proxy_cidrs("10.0.0.0/8")
    assert resolve_client_ip("172.18.0.7", "203.0.113.99", networks) == "172.18.0.7"


def test_shared_malformed_trusted_cidr_is_rejected():
    with pytest.raises(ValueError, match="trusted proxy CIDR"):
        parse_trusted_proxy_cidrs("not-a-cidr")
