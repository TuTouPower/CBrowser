"""Control failures must not expose upstream diagnostics or launch secrets."""

import logging
import secrets
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.supervisor.control_server import create_control_app


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["start", "stop"])
async def test_upstream_failure_redacts_response_and_logs(tmp_path, caplog, action):
    canary = "private_proxy_" + secrets.token_hex(16)
    token = secrets.token_urlsafe(32)
    key = tmp_path / "key"
    key.write_text(token)
    key.chmod(0o600)

    async def fail(*args, **kwargs):
        raise RuntimeError(canary)

    core = SimpleNamespace(
        api=SimpleNamespace(get=fail),
        _auth_headers=dict,
        stop_profile=fail,
    )
    app = create_control_app(core, key)
    body = {"profile_id": "p1"}
    if action == "start":
        body.update(profile_number=1)
    if action == "stop":
        body.update(runtime_instance_id="i1", operation_id="op1")
    with caplog.at_level(logging.WARNING):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://supervisor",
            headers={"Authorization": "Bearer " + token},
        ) as client:
            response = await client.post(f"/supervisor/v1/profiles/{action}", json=body)
    assert response.status_code in (500, 502)
    assert canary not in response.text
    assert canary not in caplog.text
