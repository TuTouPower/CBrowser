"""t054 AC-004/AC-008/AC-009: Origin whitelist is derived from the deploy port.

API and Gateway read the same deployment input (``CBROWSER_HTTPS_PORT``)
and derive the identical whitelist; there is no applied-state file, no
publication handshake, and no mode switch at runtime. Under a non-default
port both services accept that port's origins and reject the default
port's origins. The Gateway viewer gate enforces the same list.
"""

from __future__ import annotations

import secrets
from pathlib import Path

import httpx
import pytest
from aiohttp.test_utils import TestServer
from fastapi.testclient import TestClient

from cbrowser.api.app import create_app
from cbrowser.gateway.config import GatewayConfig
from cbrowser.gateway.server import create_gateway_app
from cbrowser.network_config import derive_origin_whitelist


def _key_file(tmp_path: Path, name: str) -> Path:
    key = tmp_path / name
    key.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    key.chmod(0o600)
    return key


def test_api_and_gateway_derive_identical_whitelist_from_deploy_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom_port = 58888
    monkeypatch.setenv("CBROWSER_HTTPS_PORT", str(custom_port))
    admin_pwd_file = _key_file(tmp_path, "admin_pwd.txt")
    admin_pwd_file.write_text("admin_secret_pass_123", encoding="utf-8")
    gw_key = _key_file(tmp_path, "gw_key.txt")

    app = create_app(
        db_path=tmp_path / "custom_port.db",
        admin_password_file=admin_pwd_file,
    )
    expected = derive_origin_whitelist(custom_port)

    gw_cfg = GatewayConfig(
        agent_key_file=gw_key,
        gateway_token_file=gw_key,
        api_url="http://127.0.0.1:8000",
        api_token_file=gw_key,
        viewer_grant_key_file=gw_key,
        https_port=custom_port,
    )
    assert gw_cfg.allowed_origins == expected

    with TestClient(app, base_url=f"https://127.0.0.1:{custom_port}") as client:
        # allowed_origins is assigned by the lifespan at startup.
        assert app.state.allowed_origins == expected
        login_resp = client.post(
            "/api/v1/auth/login", json={"password": "admin_secret_pass_123"}
        )
        assert login_resp.status_code == 200
        csrf = login_resp.json()["csrf_token"]
        # The default port origin is rejected (403).
        bad_resp = client.post(
            "/api/v1/auth/logout",
            headers={
                "X-CSRF-Token": csrf,
                "Origin": "https://127.0.0.1:56661",
            },
        )
        assert bad_resp.status_code == 403
        # The deploy port origin is accepted (200).
        ok_resp = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf, "Origin": expected[0]},
        )
        assert ok_resp.status_code == 200


class _StubApi:
    async def get_profile_runtime(self, *args, **kwargs):
        return None

    async def report_human_takeover(self, *args, **kwargs):
        return {}

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_gateway_viewer_gate_uses_deploy_port_origins(
    tmp_path: Path,
) -> None:
    key = _key_file(tmp_path, "key.txt")
    config = GatewayConfig(
        agent_key_file=key,
        gateway_token_file=key,
        api_url="http://127.0.0.1:8000",
        api_token_file=key,
        viewer_grant_key_file=key,
        https_port=58888,
    )
    assert config.allowed_origins == [
        "https://127.0.0.1:58888",
        "https://localhost:58888",
    ]
    server = TestServer(create_gateway_app(config, api_client=_StubApi()))
    await server.start_server()
    signal_url = str(server.make_url("/stream/t054/signal"))
    try:
        async with httpx.AsyncClient(trust_env=False) as probe:
            async def status(origin: str) -> int:
                resp = await probe.get(signal_url, headers={"Origin": origin})
                return resp.status_code

            # Deploy-port origin passes the origin gate (401: no viewer
            # grant), any other port is rejected at the gate (403).
            assert await status("https://127.0.0.1:58888") == 401
            assert await status("https://localhost:58888") == 401
            assert await status("https://127.0.0.1:56661") == 403
            assert await status("https://192.168.31.76:58888") == 403
    finally:
        await server.close()


def test_gateway_config_has_no_publication_or_disk_baseline() -> None:
    import cbrowser.gateway.config as module

    assert not hasattr(module, "NetworkPublicationAuthority")
    assert "network_state_dir" not in GatewayConfig.model_fields
    assert "allowed_origins" not in GatewayConfig.model_fields
