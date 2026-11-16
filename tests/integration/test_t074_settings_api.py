"""t074 AC-001: settings API auth, CSRF, validation and persistence.

Drives the real FastAPI app with a temporary SQLite DB; no Docker needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api_auth import create_auth_context
from cbrowser.api.app import create_app


@pytest.fixture
def env(tmp_path: Path):
    ctx = create_auth_context(tmp_path)
    app = create_app(
        db_path=tmp_path / "t074.db",
        admin_password_file=ctx.admin_password_file,
        artifacts_root=tmp_path / "artifacts",
    )
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        login = client.post(
            "/api/v1/auth/login", json={"password": ctx.admin_password}
        )
        assert login.status_code == 200
        yield client, ctx, login.json()["csrf_token"]


def _auth(ctx, csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf, "Origin": ctx.allowed_origin}


def test_get_requires_session(env) -> None:
    client, _ctx, _csrf = env
    client.cookies.clear()
    assert client.get("/api/v1/settings").status_code == 401


def test_get_returns_defaults(env) -> None:
    client, ctx, csrf = env
    resp = client.get("/api/v1/settings", headers=_auth(ctx, csrf))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"theme": "dark", "locale": "zh"}


def test_patch_requires_csrf(env) -> None:
    client, ctx, _csrf = env
    resp = client.patch(
        "/api/v1/settings",
        json={"theme": "light"},
        headers={"Origin": ctx.allowed_origin},
    )
    assert resp.status_code == 403


def test_patch_rejects_unknown_key(env) -> None:
    client, ctx, csrf = env
    resp = client.patch(
        "/api/v1/settings",
        json={"theme": "light", "bogus": "x"},
        headers=_auth(ctx, csrf),
    )
    assert resp.status_code == 422, resp.text


def test_patch_persists_across_sessions(env, tmp_path) -> None:
    client, ctx, csrf = env
    resp = client.patch(
        "/api/v1/settings",
        json={"theme": "light", "locale": "en"},
        headers=_auth(ctx, csrf),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"theme": "light", "locale": "en"}

    second = create_app(
        db_path=tmp_path / "t074.db",
        admin_password_file=ctx.admin_password_file,
        artifacts_root=tmp_path / "artifacts",
    )
    with TestClient(second, base_url=ctx.allowed_origin) as client2:
        login2 = client2.post(
            "/api/v1/auth/login", json={"password": ctx.admin_password}
        )
        assert login2.status_code == 200
        read = client2.get(
            "/api/v1/settings",
            headers=_auth(ctx, login2.json()["csrf_token"]),
        )
        assert read.status_code == 200
        assert read.json() == {"theme": "light", "locale": "en"}


def test_partial_patch_keeps_other_field(env) -> None:
    client, ctx, csrf = env
    resp = client.patch(
        "/api/v1/settings",
        json={"locale": "en"},
        headers=_auth(ctx, csrf),
    )
    assert resp.status_code == 200
    assert resp.json() == {"theme": "dark", "locale": "en"}
