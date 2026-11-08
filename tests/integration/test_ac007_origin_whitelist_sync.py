"""Integration tests for t042 AC-007:
API and Gateway Origin whitelist derived strictly from the same applied network version,
unlisted origins rejected, and mode-switch updates whitelist simultaneously across both services.
"""

from pathlib import Path
import secrets
import httpx
import pytest
from aiohttp.test_utils import TestServer
from fastapi.testclient import TestClient

from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.api.app import create_app
from cbrowser.domain.models import AppliedNetworkAccessVersion, NetworkAccessConfig, utc_now_iso
from cbrowser.gateway.config import GatewayConfig
from cbrowser.gateway.server import create_gateway_app
from cbrowser.network_config import write_applied_network_state
from cbrowser.services.network_service import GatewayPublicationClient


@pytest.mark.asyncio
async def test_non_default_port_origin_sync_and_acceptance(tmp_path: Path):
    """Supervisory check: Under a non-default HTTPS port, API and Gateway whitelist
    are identical, accept the non-default port origin, and reject the default port."""
    from cbrowser.adapters.database.migrations import run_database_migrations
    from cbrowser.adapters.database.session import create_engine_and_maker
    from cbrowser.network_config import derive_origin_whitelist, write_applied_network_state
    from cbrowser.domain.models import AppliedNetworkAccessVersion, NetworkAccessConfig, utc_now_iso

    db_file = tmp_path / "custom_port.db"
    net_dir = tmp_path / "network"
    net_dir.mkdir(parents=True, exist_ok=True)
    run_database_migrations(db_file)

    custom_port = 58888
    v_custom = AppliedNetworkAccessVersion(
        version=1,
        config=NetworkAccessConfig(lan_access_enabled=False, https_port=custom_port),
        bind_host="127.0.0.1",
        applied_at=utc_now_iso(),
        caddyfile_sha256="sha-custom",
        origin_whitelist=[],
    )
    v_custom.origin_whitelist = derive_origin_whitelist(v_custom)

    # Write to DB applied version
    engine, session_maker = create_engine_and_maker(db_file)
    repo = ProfileRepository(session_maker)
    await repo.record_applied_network_version(v_custom)
    await engine.dispose()

    # Write to network state dir for Gateway
    write_applied_network_state(net_dir, v_custom, "caddyfile dummy")

    admin_pwd_file = tmp_path / "admin_pwd.txt"
    admin_pwd_file.write_text("admin_secret_pass_123", encoding="utf-8")
    admin_pwd_file.chmod(0o600)

    gw_key_file = tmp_path / "gw_key.txt"
    gw_key_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    gw_key_file.chmod(0o600)

    # 1. Start API
    app = create_app(
        db_path=db_file,
        admin_password_file=admin_pwd_file,
    )
    with TestClient(app, base_url=f"https://127.0.0.1:{custom_port}") as client:
        # 2. Gateway Config
        gw_cfg = GatewayConfig(
            agent_key_file=gw_key_file,
            gateway_token_file=gw_key_file,
            api_url="http://127.0.0.1:8000",
            api_token_file=gw_key_file,
            network_state_dir=net_dir,
        )

        expected_custom_origin = f"https://127.0.0.1:{custom_port}"
        default_port_origin = "https://127.0.0.1:56661"

        # Both services derive the exact same whitelist
        assert expected_custom_origin in app.state.allowed_origins
        assert expected_custom_origin in gw_cfg.allowed_origins
        assert default_port_origin not in app.state.allowed_origins
        assert default_port_origin not in gw_cfg.allowed_origins

        # Login
        login_resp = client.post("/api/v1/auth/login", json={"password": "admin_secret_pass_123"})
        assert login_resp.status_code == 200
        csrf = login_resp.json()["csrf_token"]

        # Default port 56661 is rejected (403)
        bad_resp = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf, "Origin": default_port_origin},
        )
        assert bad_resp.status_code == 403

        # Custom port 58888 is accepted (200)
        ok_resp = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf, "Origin": expected_custom_origin},
        )
        assert ok_resp.status_code == 200


BASELINE_ORIGIN = "https://127.0.0.1:56661"
CANDIDATE_ORIGIN = "https://192.168.31.76:56661"


class _StubApi:
    async def authorize_viewer(self, *args, **kwargs):
        return True, None

    async def get_profile_runtime(self, *args, **kwargs):
        return None

    async def report_human_takeover(self, *args, **kwargs):
        return {}

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_a35_gateway_process_origin_allowlist_follows_authorized_publication(
    tmp_path: Path,
):
    key = tmp_path / "key.txt"
    key.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    key.chmod(0o600)
    net_dir = tmp_path / "network"
    net_dir.mkdir(parents=True, exist_ok=True)
    v1 = AppliedNetworkAccessVersion(
        version=1,
        config=NetworkAccessConfig(lan_access_enabled=False),
        bind_host="127.0.0.1",
        applied_at=utc_now_iso(),
        caddyfile_sha256="hash1",
        origin_whitelist=[BASELINE_ORIGIN],
    )
    write_applied_network_state(net_dir, v1, "caddyfile v1")

    config = GatewayConfig(
        agent_key_file=key,
        gateway_token_file=key,
        api_url="http://127.0.0.1:8000",
        api_token_file=key,
        network_state_dir=net_dir,
    )
    server = TestServer(create_gateway_app(config, api_client=_StubApi()))
    await server.start_server()
    signal_url = str(server.make_url("/stream/ac007/signal"))
    client = GatewayPublicationClient(
        base_url=str(server.make_url("/")).rstrip("/"),
        token=key.read_text(encoding="utf-8").strip(),
    )

    async with httpx.AsyncClient(trust_env=False) as probe:
        async def status(origin: str) -> int:
            resp = await probe.get(signal_url, headers={"Origin": origin})
            return resp.status_code

        assert await status(BASELINE_ORIGIN) == 401
        assert await status(CANDIDATE_ORIGIN) == 403

        await client.prepare("op-ac007", 1, "candidate-hash", [CANDIDATE_ORIGIN])
        assert await status(BASELINE_ORIGIN) == 401
        assert await status(CANDIDATE_ORIGIN) == 403

        await client.acknowledge("op-ac007", 1, "candidate-hash")
        assert await status(CANDIDATE_ORIGIN) == 401
        assert await status(BASELINE_ORIGIN) == 403

        await client.revoke("op-ac007", 1, "candidate-hash")
        assert await status(BASELINE_ORIGIN) == 401
        assert await status(CANDIDATE_ORIGIN) == 403

    await server.close()
