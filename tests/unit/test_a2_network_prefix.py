"""A2: network API paths are authoritative under /api/v1/network."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from api_auth import create_auth_context
from cbrowser.api.app import create_app
from cbrowser.api.v1.network_router import create_network_router

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_PATHS = {
    "/api/v1/network/settings",
    "/api/v1/network/apply",
    "/api/v1/network/operations/{operation_id}",
    "/api/v1/network/check-disconnect",
    "/api/v1/network/root-ca",
}


def _app(tmp_path: Path):
    ctx = create_auth_context(tmp_path)
    return create_app(
        db_path=tmp_path / "a2.db",
        admin_password_file=ctx.admin_password_file,
        artifacts_root=tmp_path / "artifacts",
    ), ctx


def test_network_router_defines_api_v1_prefix() -> None:
    router = create_network_router()
    paths = {route.path for route in router.routes}
    assert paths == EXPECTED_PATHS
    assert all(path.startswith("/api/v1/network/") for path in paths)


def test_official_app_registers_all_network_paths(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    schema = app.openapi()
    paths = set(schema["paths"])
    assert EXPECTED_PATHS <= paths
    assert not any(path.startswith("/network/") or path == "/network" for path in paths)
    assert "/network/settings" not in paths


def test_official_app_endpoints_hit_handlers_and_old_paths_rejected(
    tmp_path: Path,
) -> None:
    app, ctx = _app(tmp_path)
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        login = client.post("/api/v1/auth/login", json={"password": ctx.admin_password})
        assert login.status_code == 200
        headers = {
            "X-CSRF-Token": login.json()["csrf_token"],
            "Origin": ctx.allowed_origin,
        }
        assert client.get("/api/v1/network/settings").status_code == 200
        assert client.get("/api/v1/network/check-disconnect").status_code == 200
        assert client.get("/api/v1/network/root-ca").status_code == 404
        assert (
            client.put(
                "/api/v1/network/settings",
                json={"lan_access_enabled": False},
                headers=headers,
            ).status_code
            == 200
        )
        apply_resp = client.post(
            "/api/v1/network/apply",
            json={"admin_password": ctx.admin_password},
            headers=headers,
        )
        assert apply_resp.status_code == 202
        op_id = apply_resp.json()["operation_id"]
        assert client.get(f"/api/v1/network/operations/{op_id}").status_code == 200
        for old in (
            "/network/settings",
            "/network/apply",
            "/network/check-disconnect",
            "/network/root-ca",
        ):
            assert client.get(old).status_code == 404
        assert client.post("/network/apply", json={}, headers=headers).status_code == 404


def test_regenerated_openapi_and_types_carry_real_paths() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "openapi" / "cbrowser_v1.json").read_text(encoding="utf-8")
    )
    assert EXPECTED_PATHS <= set(schema["paths"])
    assert "/network/settings" not in schema["paths"]
    generated = (
        ROOT / "src" / "frontend" / "src" / "shared" / "api" / "generated" / "cbrowser_v1.d.ts"
    ).read_text(encoding="utf-8")
    assert '"/api/v1/network/settings"' in generated
    assert '"/network/settings"' not in generated
