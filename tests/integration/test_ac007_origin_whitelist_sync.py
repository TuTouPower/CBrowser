"""Integration tests for t042 AC-007:
API and Gateway Origin whitelist derived strictly from the same applied network version,
unlisted origins rejected, and mode-switch updates whitelist simultaneously across both services.
"""

from pathlib import Path
import secrets
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cbrowser.adapters.database.models import Base
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.api.app import create_app
from cbrowser.domain.models import NetworkAccessConfig
from cbrowser.gateway.config import GatewayConfig
from cbrowser.network_config import write_applied_network_state


@pytest_asyncio.fixture
async def session_maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_ac007_origin_whitelist_sync_and_rejection(session_maker, tmp_path, monkeypatch):
    """AC-007: Single source Origin whitelist across API and Gateway, mode switch updates both."""
    db_file = tmp_path / "ac007.db"
    net_dir = tmp_path / "network"
    net_dir.mkdir(parents=True, exist_ok=True)

    admin_pwd_file = tmp_path / "admin_pwd.txt"
    admin_pwd_file.write_text("admin_secret_pass_123", encoding="utf-8")
    admin_pwd_file.chmod(0o600)

    gw_key_file = tmp_path / "gw_key.txt"
    gw_key_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    gw_key_file.chmod(0o600)

    from cbrowser.adapters.database.migrations import run_database_migrations
    from cbrowser.network_config import create_default_applied_version, write_applied_network_state
    run_database_migrations(db_file)

    # Initial deployment produces baseline version 1 file in network state dir
    v1_init = create_default_applied_version()
    write_applied_network_state(net_dir, v1_init, "caddyfile dummy")

    # 1. Start API (defaults to applied version 1: local-only)
    app = create_app(
        db_path=db_file,
        admin_password_file=admin_pwd_file,
    )
    with TestClient(app, base_url="https://127.0.0.1:56661") as api_client:
        # 2. Start Gateway configuration pointing to the same network state dir
        gw_cfg = GatewayConfig(
            agent_key_file=gw_key_file,
            gateway_token_file=gw_key_file,
            api_url="http://127.0.0.1:8000",
            api_token_file=gw_key_file,
            network_state_dir=net_dir,
        )

        # Login to API
        login_resp = api_client.post("/api/v1/auth/login", json={"password": "admin_secret_pass_123"})
        assert login_resp.status_code == 200
        csrf_token = login_resp.json()["csrf_token"]

        # Verify Initial Baseline Whitelist
        # - Local loopback is allowed in API and Gateway
        assert "https://127.0.0.1:56661" in app.state.allowed_origins
        assert "https://127.0.0.1:56661" in gw_cfg.allowed_origins

        # - LAN Origin is unlisted in initial mode -> MUST be rejected in both
        lan_origin = "https://192.168.31.76:56661"
        assert lan_origin not in app.state.allowed_origins
        assert lan_origin not in gw_cfg.allowed_origins

        # API rejects unlisted LAN origin
        resp_api_rejected = api_client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf_token, "Origin": lan_origin},
        )
        assert resp_api_rejected.status_code == 403

        # 3. Mode Switch: Apply LAN configuration
        net_service = app.state.network_service
        # Mock supervisor for integration test
        net_service.supervisor_client = MagicMock()
        net_service.supervisor_client.rebuild_edge = AsyncMock(return_value={"status": "ok"})
        net_service.supervisor_client.converge_network_streams = AsyncMock(return_value={"status": "ok", "rebuilt_streams": 0})
        net_service.export_dir = net_dir

        # Update pending to LAN mode
        await net_service.update_pending_config(
            NetworkAccessConfig(
                lan_access_enabled=True,
                lan_advertised_ip="192.168.31.76",
            )
        )
        # Apply configuration
        op = await net_service.apply_configuration("admin_secret_pass_123")
        await net_service.wait_for_operation(op.operation_id, timeout=5.0)

        # 4. Verify New Whitelist Takes Effect in BOTH API and Gateway Simultaneously
        # - API reflects new origin
        assert lan_origin in app.state.allowed_origins
        # - Gateway reflects new origin from the single applied version file
        assert lan_origin in gw_cfg.allowed_origins

        # Re-login to get fresh CSRF
        login_resp2 = api_client.post("/api/v1/auth/login", json={"password": "admin_secret_pass_123"})
        csrf_token2 = login_resp2.json()["csrf_token"]

        # Still rejects unlisted attacker origin with 403
        resp_attacker = api_client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf_token2, "Origin": "https://evil-hacker.com"},
        )
        assert resp_attacker.status_code == 403
        assert "https://evil-hacker.com" not in gw_cfg.allowed_origins

        # Now LAN origin is accepted by API
        resp_api_accepted = api_client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf_token2, "Origin": lan_origin},
        )
        assert resp_api_accepted.status_code == 200


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
