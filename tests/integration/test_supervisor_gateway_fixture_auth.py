"""Verify the real HTTP fixture cannot silently bypass control authentication."""

import importlib.util
import secrets
from pathlib import Path

import httpx
import pytest
from cbrowser.supervisor.agent_credentials import AgentCredentials


@pytest.mark.asyncio
async def test_fixture_rejects_foreign_control_credentials(tmp_path):
    fixture_path = (
        Path(__file__).parents[1]
        / "fixtures/supervisor_recovery_probe/gateway_fixture.py"
    )
    spec = importlib.util.spec_from_file_location(
        "gateway_fixture_auth_probe", fixture_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    agent_key = tmp_path / "agent_key"
    agent_key.write_text(secrets.token_urlsafe(32))
    agent_key.chmod(0o600)
    control_key = tmp_path / "control_key"
    token = secrets.token_urlsafe(32)
    control_key.write_text(token)
    gateway = module.SupervisorGatewayFixture(
        0, AgentCredentials(agent_key), control_key
    )
    await gateway.start()
    port = gateway._site._server.sockets[0].getsockname()[1]
    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}", trust_env=False
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
                response = await client.request(
                    method,
                    f"/gateway/v1/internal/profiles/profile/{operation}",
                    **kwargs,
                )
                assert response.status_code == 401
                response = await client.request(
                    method,
                    f"/gateway/v1/internal/profiles/profile/{operation}",
                    headers={"Authorization": "Bearer " + secrets.token_urlsafe(32)},
                    **kwargs,
                )
                assert response.status_code == 401
                assert token not in response.text
    finally:
        await gateway.stop()
