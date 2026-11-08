"""PATCH semantics: explicit null name is invalid."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.api.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(tmp_path: Path):
    db_file = tmp_path / "patch.db"
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


def _create(client: TestClient) -> str:
    response = client.post("/api/v1/profiles", json={"name": "patch_profile"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_explicit_null_name_returns_422_without_mutation(api_client) -> None:
    profile_id = _create(api_client)
    response = api_client.patch(
        f"/api/v1/profiles/{profile_id}", json={"name": None}
    )
    assert response.status_code == 422
    assert api_client.get(f"/api/v1/profiles/{profile_id}").json()["name"] == (
        "patch_profile"
    )
