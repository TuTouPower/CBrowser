"""Real HTTP wire tests for the Supervisor side of Gateway control RPC."""

import secrets

import httpx
import pytest
from aiohttp import web
from cbrowser.supervisor.gateway_client import GatewayControlClient


@pytest.mark.asyncio
async def test_gateway_control_uses_service_auth_and_instance_fence(tmp_path):
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
