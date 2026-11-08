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


def test_legacy_cdp_entry_requires_new_automation_token(automation_env) -> None:
    client = automation_env["client"]
    profile_id = automation_env["profile_id"]
    for path in (
        f"/api/profiles/{profile_id}/cdp",
        f"/api/v1/automation/profiles/{profile_id}/cdp",
    ):
        with pytest.raises(WebSocketDisconnect) as close:
            with client.websocket_connect(
                path, headers={"Authorization": "Bearer cbat_wrong"}
            ):
                pass
        assert close.value.code == 4401
    assert "/api/profiles/{profile_id}/cdp" not in client.app.openapi()["paths"]


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
