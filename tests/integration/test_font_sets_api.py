"""Integration tests for GET /api/v1/font-sets and font-set binding
validation (t041 AC-002/AC-003)."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.api.app import create_app
from cbrowser.font_sets import import_font_set
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch):
    source = tmp_path / "src"
    source.mkdir()
    (source / "arial.ttf").write_bytes(b"FONT:arial")
    (source / "calibri.ttf").write_bytes(b"FONT:calibri")
    fonts_root = tmp_path / "fonts"
    result = import_font_set(
        "windows", [str(source)], "win11-test", root=str(fonts_root)
    )
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(fonts_root))
    fonts = {
        "root": fonts_root,
        "set_id": result["set_id"],
        "set_dir": Path(result["dir"]),
    }

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
        yield client, fonts


def test_font_sets_requires_session(api_client) -> None:
    client, _ = api_client
    client.cookies.clear()
    response = client.get("/api/v1/font-sets")
    assert response.status_code in (401, 403), response.text


def test_font_sets_lists_integrity_and_used_by_count(api_client) -> None:
    client, fonts = api_client
    response = client.get("/api/v1/font-sets")
    assert response.status_code == 200, response.text
    items = response.json()
    assert len(items) == 1
    item = items[0]
    assert item["platform"] == "windows"
    assert item["set_id"] == fonts["set_id"]
    assert item["integrity"]["ok"] is True
    assert "problems" in item["integrity"]
    assert "detection" in item["integrity"]
    assert item["used_by_count"] == 0

    created = client.post("/api/v1/profiles", json={"name": "binds"})
    assert created.status_code == 201, created.text
    assert created.json()["font_set_id"] == fonts["set_id"]

    after = client.get("/api/v1/font-sets").json()
    assert after[0]["used_by_count"] == 1


def test_create_profile_rejects_invalid_font_set_id(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/api/v1/profiles",
        json={"name": "invalid", "font_set_id": "0" * 64},
    )
    assert response.status_code == 422, response.text


def test_patch_profile_rejects_invalid_font_set_id(api_client) -> None:
    client, _ = api_client
    created = client.post("/api/v1/profiles", json={"name": "patch_target"})
    assert created.status_code == 201, created.text
    response = client.patch(
        f"/api/v1/profiles/{created.json()['id']}",
        json={"font_set_id": "0" * 64},
    )
    assert response.status_code == 422, response.text


def test_font_set_integrity_reflects_tampering(api_client) -> None:
    client, fonts = api_client
    before = client.get("/api/v1/font-sets").json()
    assert before[0]["integrity"]["ok"] is True

    (fonts["set_dir"] / "arial.ttf").write_bytes(b"TAMPERED")
    after = client.get("/api/v1/font-sets").json()
    assert after[0]["integrity"]["ok"] is False
    assert "arial.ttf" in after[0]["integrity"]["hash_mismatches"]
