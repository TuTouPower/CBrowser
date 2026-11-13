"""Automation status and independent Bearer-token CDP entry."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from cbrowser.api.app import create_app
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.fixture
def automation_env(tmp_path: Path):
    db_file = tmp_path / "automation.db"
    password = secrets.token_urlsafe(32)
    password_file = tmp_path / "admin.txt"
    password_file.write_text(password, encoding="utf-8")
    password_file.chmod(0o600)
    origin = "https://127.0.0.1:56661"
    app = create_app(
        db_path=db_file,
        admin_password_file=password_file,
                artifacts_root=tmp_path / "artifacts",
    )
    with TestClient(app, base_url=origin) as client:
        login = client.post("/api/v1/auth/login", json={"password": password})
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Origin": origin}
        profile = client.post(
            "/api/v1/profiles", json={"name": "Automation"}, headers=headers
        ).json()
        token = client.post(
            "/api/v1/automation/tokens",
            json={"name": "bot", "profile_ids": [profile["id"]]},
            headers=headers,
        )
        assert token.status_code == 201
        yield {
            "client": client,
            "profile_id": profile["id"],
            "token": token.json()["token"],
            "headers": headers,
        }


def test_automation_status_reports_authorized_endpoint(automation_env) -> None:
    client = automation_env["client"]
    profile_id = automation_env["profile_id"]
    response = client.get(f"/api/v1/profiles/{profile_id}/automation")
    assert response.status_code == 200
    body = response.json()
    assert body["profile_id"] == profile_id
    assert body["cdp_ws_path"] == (f"/api/v1/automation/profiles/{profile_id}/cdp")
    assert body["supervisor_configured"] is False
    assert body["token_header"].startswith("Authorization: Bearer")


def test_ordinary_profile_surfaces_do_not_leak_cdp_endpoint_or_token(
    automation_env,
) -> None:
    """t064 AC-004: the dedicated Automation status response is the only
    profile surface carrying cdp_ws_path. Ordinary profile detail/list
    responses used by the viewer UI contain neither that endpoint nor
    the one-time automation token value."""
    client = automation_env["client"]
    profile_id = automation_env["profile_id"]

    detail = client.get(f"/api/v1/profiles/{profile_id}")
    assert detail.status_code == 200
    assert "cdp_ws_path" not in detail.text
    assert automation_env["token"] not in detail.text

    listing = client.get("/api/v1/profiles")
    assert listing.status_code == 200
    assert "cdp_ws_path" not in listing.text
    assert automation_env["token"] not in listing.text


def test_automation_websocket_rejects_missing_or_foreign_token(
    automation_env,
) -> None:
    client = automation_env["client"]
    profile_id = automation_env["profile_id"]
    for headers in ({}, {"Authorization": "Bearer cbat_wrong"}):
        with pytest.raises(WebSocketDisconnect) as close:
            with client.websocket_connect(
                f"/api/v1/automation/profiles/{profile_id}/cdp",
                headers=headers,
            ):
                pass
        assert close.value.code == 4401


def test_legacy_cdp_entry_is_removed_and_current_entry_still_authenticates(
    automation_env,
) -> None:
    """A7: the legacy compatibility CDP entry is gone; the current
    automation endpoint keeps the full automation-token check."""
    client = automation_env["client"]
    profile_id = automation_env["profile_id"]
    with pytest.raises(WebSocketDisconnect) as close:
        with client.websocket_connect(
            f"/api/v1/automation/profiles/{profile_id}/cdp",
            headers={"Authorization": "Bearer cbat_wrong"},
        ):
            pass
    assert close.value.code == 4401
    assert "/api/profiles/{profile_id}/cdp" not in client.app.openapi()["paths"]

    def route_paths(routes, prefix=""):
        found = set()
        for route in routes:
            nested = getattr(route, "original_router", None)
            if nested is not None:
                context = getattr(route, "include_context", None)
                extra = getattr(context, "prefix", "") or ""
                found |= route_paths(nested.routes, prefix + extra)
            elif hasattr(route, "path"):
                found.add(prefix + route.path)
            elif getattr(route, "routes", None):
                found |= route_paths(route.routes, prefix)
        return found

    paths = route_paths(client.app.routes)
    assert "/api/profiles/{profile_id}/cdp" not in paths
    assert "/api/v1/automation/profiles/{profile_id}/cdp" in paths


def test_automation_websocket_rejects_profile_outside_token(automation_env) -> None:
    client = automation_env["client"]
    other = client.post(
        "/api/v1/profiles",
        json={"name": "Other"},
        headers=automation_env["headers"],
    ).json()["id"]
    with pytest.raises(WebSocketDisconnect) as close:
        with client.websocket_connect(
            f"/api/v1/automation/profiles/{other}/cdp",
            headers={"Authorization": f"Bearer {automation_env['token']}"},
        ):
            pass
    assert close.value.code == 4401
