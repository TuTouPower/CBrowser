"""Verify the production Gateway cannot silently bypass control authentication."""

import secrets
import socket

import httpx
import pytest
from supervisor_recovery_probe.gateway_service import ProductionGatewayService


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.asyncio
async def test_gateway_rejects_foreign_control_credentials(tmp_path):
    agent_key = tmp_path / "agent_key"
    agent_key.write_text(secrets.token_urlsafe(32))
    agent_key.chmod(0o600)
    control_key = tmp_path / "control_key"
    token = secrets.token_urlsafe(32)
    control_key.write_text(token)
    control_key.chmod(0o600)

    gateway = ProductionGatewayService(
        port=_free_port(),
        agent_key_file=agent_key,
        gateway_token_file=control_key,
    )
    await gateway.start()
    try:
        async with httpx.AsyncClient(
            base_url=gateway.control_url, trust_env=False
        ) as client:
            for operation, method in (
                ("visibility", "GET"),
                ("quota", "POST"),
                ("disconnect", "POST"),
            ):
                kwargs = (
                    {"params": {"runtime_instance_id": "runtime"}}
                    if method == "GET"
                    else {"json": {"runtime_instance_id": "runtime", "max_fps_cap": 8}}
                )
                path = f"/gateway/v1/internal/profiles/profile/{operation}"
                response = await client.request(method, path, **kwargs)
                assert response.status_code == 401
                response = await client.request(
                    method,
                    path,
                    headers={"Authorization": "Bearer " + secrets.token_urlsafe(32)},
                    **kwargs,
                )
                assert response.status_code == 401
                assert token not in response.text
    finally:
        await gateway.stop()
