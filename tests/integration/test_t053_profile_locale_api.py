"""Integration tests for t053 AC-001/AC-005/AC-008 at the HTTP layer.

- New-profile defaults (humanize/portable_cookies on, locale en-US)
  are served by the real FastAPI app.
- Illegal locale/timezone values are rejected with field-level 422s.
- Changing locale creates a new config version (AC-008 version half;
  the runtime half needs a real engine).
"""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.api.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(tmp_path: Path):
    db_file = tmp_path / "locale.db"
    run_database_migrations(db_file)
    admin_pass = secrets.token_urlsafe(32)
    admin_file = tmp_path / "admin.pwd"
    admin_file.write_text(admin_pass, encoding="utf-8")
    admin_file.chmod(0o600)
    gateway_token = secrets.token_urlsafe(32)
    gateway_file = tmp_path / "gateway.token"
    gateway_file.write_text(gateway_token, encoding="utf-8")
    gateway_file.chmod(0o600)
    app = create_app(
        db_path=db_file,
        admin_password_file=admin_file,
        gateway_token_file=gateway_file,
    )
    with TestClient(app, base_url="https://127.0.0.1:56661") as client:
        login = client.post("/api/v1/auth/login", json={"password": admin_pass})
        assert login.status_code == 200
        client.headers.update(
            {
                "X-CSRF-Token": login.json()["csrf_token"],
                "Origin": "https://127.0.0.1:56661",
            }
        )
        yield client


def test_create_defaults_humanize_and_portable_cookies(api_client) -> None:
    response = api_client.post("/api/v1/profiles", json={"name": "Defaults"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["humanize"] is True
    assert body["portable_cookies"] is True
    assert body["transparent_proxy"] is False
    assert body["auto_launch"] is False
    assert body["allow_3p_cookies"] is True
    assert body["set_google_default"] is True
    assert body["clipboard_sync"] is True
    assert body["restore_session"] is True
    assert body["capture_preview"] is True
    assert body["locale"] == "en-US"
    assert body["timezone"] is None


def test_create_rejects_other_locales(api_client) -> None:
    for bad in ("en-GB", "en", "zh", "fr-FR"):
        response = api_client.post(
            "/api/v1/profiles", json={"name": "Bad", "locale": bad}
        )
        assert response.status_code == 422, response.text
        # t056 A15: field errors live in the unified `details` list.
        body = response.json()
        assert body["error"] == "validation_error", body
        details = body["details"]
        assert any(
            isinstance(item, dict) and "locale" in item.get("loc", [])
            for item in details
        ), details


def test_create_rejects_invalid_timezone(api_client) -> None:
    response = api_client.post(
        "/api/v1/profiles", json={"name": "Bad", "timezone": "Mars/Olympus"}
    )
    assert response.status_code == 422, response.text
    # t056 A15: field errors live in the unified `details` list.
    body = response.json()
    assert body["error"] == "validation_error", body
    details = body["details"]
    assert any(
        isinstance(item, dict) and "timezone" in item.get("loc", [])
        for item in details
    ), details


def test_create_accepts_valid_timezone_and_locale(api_client) -> None:
    response = api_client.post(
        "/api/v1/profiles",
        json={
            "name": "Ok",
            "timezone": "Asia/Shanghai",
            "locale": "zh-CN",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["timezone"] == "Asia/Shanghai"
    assert response.json()["locale"] == "zh-CN"


def test_locale_change_creates_new_config_version(api_client) -> None:
    created = api_client.post(
        "/api/v1/profiles", json={"name": "Versioned", "locale": "en-US"}
    )
    assert created.status_code == 201, created.text
    profile = created.json()
    assert profile["current_config_version"] == 1

    patched = api_client.patch(
        f"/api/v1/profiles/{profile['id']}", json={"locale": "zh-CN"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["locale"] == "zh-CN"
    assert patched.json()["current_config_version"] == 2

    versions = api_client.get(f"/api/v1/profiles/{profile['id']}/versions")
    assert versions.status_code == 200, versions.text
    assert [v["version"] for v in versions.json()] == [1, 2]
