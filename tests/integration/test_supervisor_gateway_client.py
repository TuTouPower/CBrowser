"""Wire tests for the Supervisor side of Gateway control RPC.

Two layers (t024 AC-004/A25): the auth and fence semantics of the control
contract are exercised against a real ``create_gateway_app`` instance; the
catch-all stub below is kept only for transport-level cases (request
shapes and status propagation) and models no authorization semantics of
its own.
"""

import secrets
import socket

import httpx
import pytest
from aiohttp import web
from cbrowser.supervisor.gateway_client import GatewayControlClient
from supervisor_recovery_probe.gateway_service import ProductionGatewayService


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.asyncio
async def test_gateway_control_against_real_gateway_auth_and_availability(tmp_path):
    """Client + production gateway: wrong token is 401, and a profile with
    no registered agent is exactly 503 (the production fence/availability
    decision), never a stub-invented status."""
    agent_key = tmp_path / "agent_key"
    agent_key.write_text(secrets.token_urlsafe(32))
    agent_key.chmod(0o600)
    control_key = tmp_path / "control_key"
    control_token = secrets.token_urlsafe(32)
    control_key.write_text(control_token)
    control_key.chmod(0o600)

    gateway = ProductionGatewayService(
        port=_free_port(),
        agent_key_file=agent_key,
        gateway_token_file=control_key,
    )
    await gateway.start()
    try:
        foreign_key = tmp_path / "foreign_key"
        foreign_key.write_text(secrets.token_urlsafe(32))
        foreign_key.chmod(0o600)
        foreign_client = GatewayControlClient(gateway.control_url, foreign_key)
        try:
            with pytest.raises(httpx.HTTPStatusError) as rejected:
                await foreign_client.has_foreground_viewers("profile", "instance")
            assert rejected.value.response.status_code == 401
        finally:
            await foreign_client.close()

        client = GatewayControlClient(gateway.control_url, control_key)
        try:
            with pytest.raises(httpx.HTTPStatusError) as unavailable:
                await client.has_foreground_viewers("profile", "instance")
            assert unavailable.value.response.status_code == 503
            with pytest.raises(httpx.HTTPStatusError) as unavailable:
                await client.set_quota("profile", "instance", 8)
            assert unavailable.value.response.status_code == 503
        finally:
            await client.close()
    finally:
        await gateway.stop()


@pytest.mark.asyncio
async def test_gateway_control_wire_format_and_status_propagation(tmp_path):
    """Transport-level stub: verifies request shapes (query vs JSON body),
    quota payload sequencing and that a fence-style 409 propagates to the
    caller.  Authorization semantics are covered against the real gateway
    above, not by this stub."""
    token = secrets.token_urlsafe(32)
    key = tmp_path / "gateway_key"
    key.write_text(token)
    key.chmod(0o600)
    received = []

    async def control(request):
        if request.headers.get("Authorization") != f"Bearer {token}":
            return web.Response(status=401)
        payload = (
            dict(request.query) if request.method == "GET" else await request.json()
        )
        if payload.get("runtime_instance_id") != "current_instance":
            return web.Response(status=409)
        received.append((request.path, payload))
        return web.json_response({"has_foreground_viewers": False})

    app = web.Application()
    app.router.add_route(
        "*", "/gateway/v1/internal/profiles/{profile}/{operation}", control
    )
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    client = GatewayControlClient(f"http://127.0.0.1:{port}", key)
    try:
        assert not await client.has_foreground_viewers("profile", "current_instance")
        await client.set_quota("profile", "current_instance", 8)
        await client.set_quota("profile", "current_instance", None)
        await client.disconnect_viewers("profile", "current_instance")
        with pytest.raises(httpx.HTTPStatusError) as rejected:
            await client.set_quota("profile", "stale_instance", 8)
        assert rejected.value.response.status_code == 409
        assert [
            payload.get("max_fps_cap")
            for path, payload in received
            if path.endswith("/quota")
        ] == [8, None]
        assert len(received) == 4
    finally:
        await client.close()
        await runner.cleanup()


def test_gateway_control_requires_nonempty_external_key(tmp_path):
    key = tmp_path / "empty_key"
    key.write_text("")
    key.chmod(0o600)
    with pytest.raises(ValueError, match="at least 32 bytes"):
        GatewayControlClient("http://127.0.0.1:1", key)
