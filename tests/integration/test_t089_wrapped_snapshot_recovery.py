"""Integration regression for wrapped config snapshots after 0014 compensation."""

from __future__ import annotations

import asyncio
import json
import secrets
import sqlite3
from pathlib import Path

import httpx
from alembic import command
from fastapi.testclient import TestClient

from cbrowser.adapters.database.migrations import (
    get_alembic_config,
    run_database_migrations,
)
from cbrowser.api.app import create_app
from cbrowser.domain.models import ProfileConfig
from cbrowser.font_sets import import_font_set
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator
from cbrowser.supervisor.recovery_coordinator import RecoveryCoordinator

LEGACY_HEAD = "d7e3a91f4c62"


def test_migrated_legacy_wrapped_snapshot_serves_valid_config_over_api_and_supervisor(
    tmp_path: Path, monkeypatch
) -> None:
    font_src = tmp_path / "src_fonts"
    font_src.mkdir()
    (font_src / "segoeui.ttf").write_bytes(b"FONT:segoeui")
    fonts_root = tmp_path / "fonts"
    imported = import_font_set(
        "windows", [str(font_src)], "win11-e2e", root=str(fonts_root)
    )
    win_set_id = imported["set_id"]
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(fonts_root))

    db_file = tmp_path / "control.db"
    command.upgrade(get_alembic_config(db_file), LEGACY_HEAD)

    profile_id = "11111111-1111-4111-8111-111111111111"
    proxy_id = "22222222-2222-4222-8222-222222222222"
    conn = sqlite3.connect(db_file)
    try:
        conn.execute(
            "INSERT INTO font_set_assets (platform, set_id, source, source_version,"
            " file_count, total_bytes, integrity, state, revision, state_seq,"
            " verified_at, audited_at, created_at, updated_at)"
            " VALUES ('windows', ?, 'local', 'win11-e2e', 1, 12, '{}', 'verified',"
            " 1, 1, '2026-01-02T00:00:00+00:00', NULL,"
            " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
            (win_set_id,),
        )
        conn.execute(
            "INSERT INTO proxies (id, name, scheme, host, port, username, password,"
            " credential_revision, region_label, notes, created_at, updated_at)"
            " VALUES (?, 'jp-relay', 'http', '127.0.0.1', 8080, 'u', 'p', 4, 'JP',"
            " '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
            (proxy_id,),
        )
        conn.execute(
            "INSERT INTO profiles (id, name, fingerprint_seed, user_data_dir, proxy_id,"
            " created_at, updated_at, display_number, color_scheme, include_cjk_fonts,"
            " locale, fingerprint_platform, font_set_id)"
            " VALUES (?, 'JP Legacy', 4242, ?, ?, '2026-01-01T00:00:00+00:00',"
            " '2026-01-01T00:00:00+00:00', 1, 'light', 0, 'en-US', 'windows', ?)",
            (profile_id, f"/data/profiles/{profile_id}", proxy_id, win_set_id),
        )
        conn.execute(
            "INSERT INTO profile_runtimes (profile_id, desired_state, observed_state,"
            " config_version, state_revision, updated_at)"
            " VALUES (?, 'stopped', 'stopped', 1, 1, '2026-01-01T00:00:00+00:00')",
            (profile_id,),
        )
        # Simulate exact buggy 0013 output: outer wrapper polluted, inner config un-migrated.
        conn.execute(
            "INSERT INTO profile_config_versions (id, profile_id, version, snapshot, created_at)"
            " VALUES ('ver-1', ?, 1, ?, '2026-01-01T00:00:00+00:00')",
            (
                profile_id,
                json.dumps(
                    {
                        "config": {
                            "name": "JP Legacy",
                            "fingerprint_seed": 4242,
                            "proxy_id": proxy_id,
                            "gpu_family": "auto",
                            "color_scheme": None,
                            "locale": "en-US",
                            "fingerprint_platform": "windows",
                            "font_set_id": None,
                        },
                        "proxy_credential_revision": 4,
                        "color_scheme": "light",
                        "include_cjk_fonts": True,
                        "font_set_id": win_set_id,
                    }
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    run_database_migrations(db_file)

    admin_pass = secrets.token_urlsafe(32)
    admin_file = tmp_path / "admin.pwd"
    admin_file.write_text(admin_pass, encoding="utf-8")
    admin_file.chmod(0o600)
    sup_token = secrets.token_urlsafe(32)
    sup_file = tmp_path / "sup.token"
    sup_file.write_text(sup_token, encoding="utf-8")
    sup_file.chmod(0o600)
    gw_token = secrets.token_urlsafe(32)
    gw_file = tmp_path / "gw.token"
    gw_file.write_text(gw_token, encoding="utf-8")
    gw_file.chmod(0o600)

    app = create_app(
        db_path=db_file,
        admin_password_file=admin_file,
        supervisor_token_file=sup_file,
        gateway_token_file=gw_file,
    )
    with TestClient(app, base_url="https://127.0.0.1:56661") as client:
        login = client.post("/api/v1/auth/login", json={"password": admin_pass})
        assert login.status_code == 200
        ui_headers = {
            "X-CSRF-Token": login.json()["csrf_token"],
            "Origin": "https://127.0.0.1:56661",
        }
        v_resp = client.get(
            f"/api/v1/profiles/{profile_id}/versions/1", headers=ui_headers
        )
        assert v_resp.status_code == 200
        body = v_resp.json()
        assert "gpu_family" not in body["config"]
        assert body["config"]["color_scheme"] == "light"
        assert body["config"]["include_cjk_fonts"] is False
        assert body["config"]["font_set_id"] == win_set_id
        ProfileConfig.model_validate(body["config"])

        sup_headers = {"Authorization": f"Bearer {sup_token}"}
        sup_resp = client.get(
            f"/api/v1/internal/supervisor/profiles/{profile_id}/versions/1",
            headers=sup_headers,
        )
        assert sup_resp.status_code == 200
        sup_body = sup_resp.json()
        assert sup_body["profile_id"] == profile_id
        assert sup_body["version"] == 1
        assert sup_body["config"] == body["config"]
        ProfileConfig.model_validate(sup_body["config"])

        creds_resp = client.get(
            f"/api/v1/internal/supervisor/proxies/{proxy_id}/credentials",
            params={"profile_id": profile_id, "version": 1},
            headers=sup_headers,
        )
        assert creds_resp.status_code == 200
        assert creds_resp.json()["proxy_credential_revision"] == 4

        async def _verify_supervisor_consumers() -> None:
            data_root = tmp_path / "sup_data"
            engine_cache = data_root / "engine_cache"
            (engine_cache / "geoip").mkdir(parents=True)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="https://127.0.0.1:56661",
            ) as sup_api:
                core = SupervisorCore(
                    docker_adapter=DockerAdapter(
                        PathValidator(data_root),
                        engine_cache,
                        docker_client=object(),
                        browser_image=f"sha256:{'a' * 64}",
                        stream_image=f"sha256:{'b' * 64}",
                    ),
                    port_allocator=PortAllocator(30000, 30010),
                    event_forwarder=EventForwarder(
                        "https://127.0.0.1:56661",
                        tmp_path / "spool",
                        token_file=sup_file,
                        client=sup_api,
                    ),
                    api_client=sup_api,
                    token_file=sup_file,
                )
                coordinator = RecoveryCoordinator(core)
                loaded_cfg = await coordinator._load_profile_config(profile_id, 1)
                assert loaded_cfg == ProfileConfig.model_validate(body["config"])
                assert loaded_cfg.include_cjk_fonts is False
                assert loaded_cfg.font_set_id == win_set_id
                resolved_creds = await core._resolve_proxy_credentials(
                    profile_id, loaded_cfg, 1
                )
                assert resolved_creds is not None
                assert resolved_creds["proxy_credential_revision"] == 4
                assert resolved_creds["credential_revision"] == 4

        asyncio.run(_verify_supervisor_consumers())
