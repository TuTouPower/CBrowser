"""t020 AC-002/AC-006: font_bundle over the public profile API."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.api.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(tmp_path: Path):
    db_file = tmp_path / "fonts.db"
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
        allowed_origins=["https://app.cbrowser.local"],
    )
    with TestClient(app, base_url="https://app.cbrowser.local") as client:
        login = client.post("/api/v1/auth/login", json={"password": admin_pass})
        assert login.status_code == 200
        client.headers.update(
            {
                "X-CSRF-Token": login.json()["csrf_token"],
                "Origin": "https://app.cbrowser.local",
            }
        )
        yield client


def test_create_defaults_font_bundle_to_none(api_client) -> None:
    response = api_client.post("/api/v1/profiles", json={"name": "plain"})
    assert response.status_code == 201, response.text
    assert response.json()["font_bundle"] == "none"


def test_create_and_read_back_each_bundle(api_client) -> None:
    for bundle in ("wqy-microhei", "wqy-zenhei"):
        response = api_client.post(
            "/api/v1/profiles",
            json={"name": f"p-{bundle}", "font_bundle": bundle},
        )
        assert response.status_code == 201, response.text
        assert response.json()["font_bundle"] == bundle
        fetched = api_client.get(f"/api/v1/profiles/{response.json()['id']}")
        assert fetched.json()["font_bundle"] == bundle


def test_create_rejects_unknown_bundle(api_client) -> None:
    response = api_client.post(
        "/api/v1/profiles", json={"name": "bad", "font_bundle": "simsun"}
    )
    assert response.status_code == 422


def test_update_font_bundle_bumps_version_and_echoes(api_client) -> None:
    created = api_client.post("/api/v1/profiles", json={"name": "updatable"})
    profile_id = created.json()["id"]
    assert created.json()["current_config_version"] == 1

    updated = api_client.patch(
        f"/api/v1/profiles/{profile_id}", json={"font_bundle": "wqy-microhei"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["font_bundle"] == "wqy-microhei"
    assert updated.json()["current_config_version"] == 2

    rejected = api_client.patch(
        f"/api/v1/profiles/{profile_id}", json={"font_bundle": None}
    )
    assert rejected.status_code == 422
    rejected = api_client.patch(
        f"/api/v1/profiles/{profile_id}", json={"font_bundle": "yahei"}
    )
    assert rejected.status_code == 422

    fetched = api_client.get(f"/api/v1/profiles/{profile_id}")
    assert fetched.json()["font_bundle"] == "wqy-microhei"
    assert fetched.json()["current_config_version"] == 2
