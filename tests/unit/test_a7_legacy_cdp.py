"""A7: legacy CDP compatibility router is fully removed."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api_auth import create_auth_context
from cbrowser.api import app as app_module
from cbrowser.api.app import create_app
from cbrowser.api.v1 import automation_router as automation_module


LEGACY_PATH = "/api/profiles/{profile_id}/cdp"
CURRENT_PATH = "/api/v1/automation/profiles/{profile_id}/cdp"


def _collect_paths(app) -> set[str]:
    paths: set[str] = set()

    def walk(routes, prefix: str = "") -> None:
        for route in routes:
            nested = getattr(route, "original_router", None)
            if nested is not None:
                context = getattr(route, "include_context", None)
                extra = getattr(context, "prefix", "") or ""
                walk(nested.routes, prefix + extra)
            elif hasattr(route, "path"):
                paths.add(prefix + route.path)
            else:
                sub = getattr(route, "routes", None)
                if sub:
                    walk(sub, prefix)

    walk(app.routes)
    return paths


def _app(tmp_path: Path):
    ctx = create_auth_context(tmp_path)
    app = create_app(
        db_path=tmp_path / "a7.db",
        admin_password_file=ctx.admin_password_file,
        artifacts_root=tmp_path / "artifacts",
    )
    return app, ctx


def test_production_modules_have_no_legacy_router() -> None:
    assert not hasattr(automation_module, "legacy_cdp_router")
    source = inspect.getsource(automation_module)
    assert "legacy_cdp_router" not in source
    assert "add_api_websocket_route" not in source
    app_source = inspect.getsource(app_module)
    assert "legacy_cdp_router" not in app_source


def test_official_app_registers_only_current_cdp_route(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    paths = _collect_paths(app)
    assert CURRENT_PATH in paths
    assert LEGACY_PATH not in paths
    assert not any("legacy" in path for path in paths)
    schema = app.openapi()
    assert LEGACY_PATH not in schema["paths"]
    assert not any("legacy" in path for path in schema["paths"])


def test_legacy_cdp_address_is_not_connectable(tmp_path: Path) -> None:
    app, ctx = _app(tmp_path)
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        login = client.post("/api/v1/auth/login", json={"password": ctx.admin_password})
        assert login.status_code == 200
        headers = {
            "X-CSRF-Token": login.json()["csrf_token"],
            "Origin": ctx.allowed_origin,
        }
        profile = client.post(
            "/api/v1/profiles", json={"name": "cdp"}, headers=headers
        ).json()
        pid = profile["id"]
        token = client.post(
            "/api/v1/automation/tokens",
            json={"name": "bot", "profile_ids": [pid]},
            headers=headers,
        )
        assert token.status_code == 201
        bearer = {"Authorization": f"Bearer {token.json()['token']}"}
        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect(
                f"/api/profiles/{pid}/cdp", headers=bearer
            ):
                pass
        assert closed.value.code != 4401
        with pytest.raises(WebSocketDisconnect) as current:
            with client.websocket_connect(
                f"/api/v1/automation/profiles/{pid}/cdp",
                headers={"Authorization": "Bearer cbat_wrong"},
            ):
                pass
        assert current.value.code == 4401
