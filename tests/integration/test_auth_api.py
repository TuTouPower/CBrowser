"""Integration tests for Auth API and Internal Gateway RPC endpoints."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.models import ProfileModel
from cbrowser.adapters.database.session import (
    create_engine_and_maker,
    write_transaction,
)
from cbrowser.api.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def auth_env(tmp_path: Path):
    db_file = tmp_path / "auth_api_test.db"
    run_database_migrations(db_file)

    admin_pass = secrets.token_urlsafe(32)
    admin_pwd_file = tmp_path / "admin_pass.txt"
    admin_pwd_file.write_text(admin_pass, encoding="utf-8")
    admin_pwd_file.chmod(0o600)

    gateway_token = secrets.token_urlsafe(32)
    gateway_token_file = tmp_path / "gateway_token.txt"
    gateway_token_file.write_text(gateway_token, encoding="utf-8")
    gateway_token_file.chmod(0o600)

    origin = "https://127.0.0.1:56661"

    app = create_app(
        db_path=db_file,
        admin_password_file=admin_pwd_file,
        gateway_token_file=gateway_token_file,
    )

    with TestClient(app, base_url=origin) as client:
        yield {
            "client": client,
            "admin_pass": admin_pass,
            "gateway_token": gateway_token,
            "db_file": db_file,
            "allowed_origin": origin,
        }


def test_login_success_and_cookie_attributes(auth_env):
    client = auth_env["client"]
    admin_pass = auth_env["admin_pass"]

    # 1. Login with correct password
    resp = client.post(
        "/api/v1/auth/login",
        json={"password": admin_pass},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "csrf_token" in body
    csrf_token = body["csrf_token"]

    # Check cookies
    session_cookie = resp.cookies.get("cbrowser_session")
    csrf_cookie = resp.cookies.get("cbrowser_csrf")
    assert session_cookie is not None
    assert csrf_cookie == csrf_token

    # Check cookie headers for HttpOnly, Secure, SameSite=Strict
    set_cookies = resp.headers.get_list("set-cookie")
    session_header = next(c for c in set_cookies if "cbrowser_session=" in c)
    csrf_header = next(c for c in set_cookies if "cbrowser_csrf=" in c)

    assert "httponly" in session_header.lower()
    assert "secure" in session_header.lower()
    assert "samesite=strict" in session_header.lower()

    # CSRF cookie is NOT HttpOnly (accessible to JS for double-submit)
    assert "httponly" not in csrf_header.lower()
    assert "secure" in csrf_header.lower()
    assert "samesite=strict" in csrf_header.lower()


def test_login_rate_limiting(auth_env):
    client = auth_env["client"]

    # 5 failed login attempts
    for _ in range(5):
        resp = client.post("/api/v1/auth/login", json={"password": "wrong_password"})
        assert resp.status_code == 401

    # 6th attempt is rate-limited (429)
    resp = client.post("/api/v1/auth/login", json={"password": "wrong_password"})
    assert resp.status_code == 429
    assert "too many" in resp.json()["message"].lower()


def test_session_check_and_logout(auth_env):
    client = auth_env["client"]
    admin_pass = auth_env["admin_pass"]
    allowed_origin = auth_env["allowed_origin"]

    # Session check without login -> 401
    resp = client.get("/api/v1/auth/session")
    assert resp.status_code == 401

    # Login
    login_resp = client.post("/api/v1/auth/login", json={"password": admin_pass})
    csrf_token = login_resp.json()["csrf_token"]
    session_token = login_resp.cookies.get("cbrowser_session")

    # Session check with cookie -> 200
    resp = client.get("/api/v1/auth/session")
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is True
    assert resp.json()["csrf_token"] == csrf_token

    # Logout without CSRF -> 403
    resp_no_csrf = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": allowed_origin},
    )
    assert resp_no_csrf.status_code == 403

    # Logout without Origin -> 403
    resp_no_origin = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp_no_origin.status_code == 403

    # Logout with CSRF + Origin -> 200
    resp_logout = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token, "Origin": allowed_origin},
    )
    assert resp_logout.status_code == 200

    # Subsequent session check -> 401
    resp_after = client.get(
        "/api/v1/auth/session",
        cookies={"cbrowser_session": session_token},
    )
    assert resp_after.status_code == 401


def _login(client, admin_pass):
    resp = client.post("/api/v1/auth/login", json={"password": admin_pass})
    assert resp.status_code == 200
    return resp.json()["csrf_token"]


def test_csrf_referer_fallback_allows_same_origin(auth_env):
    """AC-005 (A7): no Origin + allow-listed Referer passes the source check.

    The request carries a valid CSRF token, so it can only succeed by
    entering the Referer fallback branch of require_csrf_and_origin.
    """
    client = auth_env["client"]
    csrf_token = _login(client, auth_env["admin_pass"])
    resp = client.post(
        "/api/v1/auth/logout",
        headers={
            "X-CSRF-Token": csrf_token,
            "Referer": f"{auth_env['allowed_origin']}/profiles?page=2",
        },
    )
    assert resp.status_code == 200


def test_csrf_referer_fallback_rejects_external_referer(auth_env):
    client = auth_env["client"]
    csrf_token = _login(client, auth_env["admin_pass"])
    resp = client.post(
        "/api/v1/auth/logout",
        headers={
            "X-CSRF-Token": csrf_token,
            "Referer": "https://attacker.example/phish",
        },
    )
    assert resp.status_code == 403


@pytest.mark.parametrize(
    "referer",
    [
        "not a url",
        "http://[::1/broken-ipv6",
        "/relative/path-only",
    ],
)
def test_csrf_referer_fallback_rejects_malformed_referer(auth_env, referer):
    client = auth_env["client"]
    csrf_token = _login(client, auth_env["admin_pass"])
    resp = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token, "Referer": referer},
    )
    assert resp.status_code == 403


def test_automation_token_endpoints_and_audit(auth_env):
    client = auth_env["client"]
    admin_pass = auth_env["admin_pass"]
    allowed_origin = auth_env["allowed_origin"]

    # 1. Unauthenticated -> 401
    resp_unauth = client.post(
        "/api/v1/automation/tokens",
        json={"name": "test", "profile_ids": ["p1"]},
    )
    assert resp_unauth.status_code == 401

    # Login
    login_resp = client.post("/api/v1/auth/login", json={"password": admin_pass})
    csrf_token = login_resp.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_token, "Origin": allowed_origin}

    # 2. Create token
    create_resp = client.post(
        "/api/v1/automation/tokens",
        json={"name": "bot_token", "profile_ids": ["prof-1", "prof-2"]},
        headers=headers,
    )
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    token_id = created_data["id"]
    raw_token = created_data["token"]
    assert raw_token.startswith("cbat_")
    assert created_data["profile_ids"] == ["prof-1", "prof-2"]

    # 3. List tokens: raw token is NOT in the response
    list_resp = client.get("/api/v1/automation/tokens")
    assert list_resp.status_code == 200
    tokens = list_resp.json()
    matching = [t for t in tokens if t["id"] == token_id]
    assert len(matching) == 1
    assert "token" not in matching[0]

    # 4. Revoke token
    del_resp = client.delete(f"/api/v1/automation/tokens/{token_id}", headers=headers)
    assert del_resp.status_code == 204

    # 5. Revoking again -> 404
    del_again = client.delete(f"/api/v1/automation/tokens/{token_id}", headers=headers)
    assert del_again.status_code == 404


@pytest.mark.asyncio
async def test_internal_gateway_endpoints(auth_env):
    client = auth_env["client"]
    admin_pass = auth_env["admin_pass"]
    gateway_token = auth_env["gateway_token"]
    allowed_origin = auth_env["allowed_origin"]
    db_file = auth_env["db_file"]

    # Create dummy profile and runtime in DB
    prof_id = "prof-gtw-123"
    engine, session_maker = create_engine_and_maker(db_file)
    async with session_maker() as session, write_transaction(session):
        session.add(
            ProfileModel(
                id=prof_id,
                name="Gateway Profile",
                fingerprint_seed=888999,
                user_data_dir="/tmp/gtw",
            )
        )
        from cbrowser.adapters.database.models import ProfileRuntimeModel

        session.add(
            ProfileRuntimeModel(
                profile_id=prof_id,
                desired_state="stopped",
                observed_state="stopped",
                config_version=1,
            )
        )
    await engine.dispose()

    # 1. Gateway auth enforcement
    no_auth = client.post(
        "/api/v1/internal/gateway/viewer-authorize",
        json={"session_token": "abc", "origin": allowed_origin, "profile_id": prof_id},
    )
    assert no_auth.status_code == 401

    bad_auth = client.post(
        "/api/v1/internal/gateway/viewer-authorize",
        json={"session_token": "abc", "origin": allowed_origin, "profile_id": prof_id},
        headers={"Authorization": "Bearer wrong_token_123456789012345678901234"},
    )
    assert bad_auth.status_code == 401

    gw_headers = {"Authorization": f"Bearer {gateway_token}"}

    # Login to obtain valid user session
    login_resp = client.post("/api/v1/auth/login", json={"password": admin_pass})
    session_token = login_resp.cookies.get("cbrowser_session")
    csrf_token = login_resp.json()["csrf_token"]

    # 2. viewer-authorize: valid
    v_ok = client.post(
        "/api/v1/internal/gateway/viewer-authorize",
        json={
            "session_token": session_token,
            "origin": allowed_origin,
            "profile_id": prof_id,
        },
        headers=gw_headers,
    )
    assert v_ok.status_code == 200
    assert v_ok.json()["allowed"] is True

    # viewer-authorize: bad origin
    v_bad_origin = client.post(
        "/api/v1/internal/gateway/viewer-authorize",
        json={
            "session_token": session_token,
            "origin": "https://attacker.site",
            "profile_id": prof_id,
        },
        headers=gw_headers,
    )
    assert v_bad_origin.status_code == 200
    assert v_bad_origin.json()["allowed"] is False
    assert v_bad_origin.json()["reason"] == "invalid_origin"

    # 3. The internal automation-authorize surface was removed (A42): it
    # had no production consumer — the real CDP entry point is the v1
    # automation router backed by AuthService. The route must be gone.
    removed = client.post(
        "/api/v1/internal/gateway/automation-authorize",
        json={"token": "cbat_whatever", "profile_id": prof_id},
        headers=gw_headers,
    )
    assert removed.status_code == 404

    # 4. Gateway runtime inspection
    rt_res = client.get(
        f"/api/v1/internal/gateway/profiles/{prof_id}/runtime",
        headers=gw_headers,
    )
    assert rt_res.status_code == 200
    rt_data = rt_res.json()
    assert rt_data["profile_id"] == prof_id
    assert rt_data["desired_state"] == "stopped"

    # Nonexistent profile -> 404
    rt_notfound = client.get(
        "/api/v1/internal/gateway/profiles/prof-nonexistent/runtime",
        headers=gw_headers,
    )
    assert rt_notfound.status_code == 404


def test_no_secret_or_token_leak_in_responses(auth_env):
    """AC-001/AC-006: Master/Selkies token and password must not leak."""
    client = auth_env["client"]
    admin_pass = auth_env["admin_pass"]
    allowed_origin = auth_env["allowed_origin"]

    # Login
    login_resp = client.post("/api/v1/auth/login", json={"password": admin_pass})
    assert login_resp.status_code == 200
    assert admin_pass not in login_resp.text
    assert "master_token" not in login_resp.text
    assert "selkies_token" not in login_resp.text

    csrf_token = login_resp.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_token, "Origin": allowed_origin}

    # Session
    sess_resp = client.get("/api/v1/auth/session")
    assert admin_pass not in sess_resp.text
    assert "master_token" not in sess_resp.text
    assert "selkies_token" not in sess_resp.text

    # Automation tokens
    tok_resp = client.post(
        "/api/v1/automation/tokens",
        json={"name": "audit_probe", "profile_ids": ["p1"]},
        headers=headers,
    )
    assert tok_resp.status_code == 201
    assert "master_token" not in tok_resp.text
    assert "selkies_token" not in tok_resp.text

    list_resp = client.get("/api/v1/automation/tokens")
    assert "master_token" not in list_resp.text
    assert "selkies_token" not in list_resp.text


def test_public_runtime_endpoints_require_auth_and_csrf(auth_env):
    """Verify that public desired-state requires login, CSRF, and Origin."""
    client = auth_env["client"]
    admin_pass = auth_env["admin_pass"]
    allowed_origin = auth_env["allowed_origin"]

    prof_id = "test-prof-auth-probe"

    # 1. Unauthenticated PATCH -> 401
    resp_unauth = client.patch(
        f"/api/v1/profiles/{prof_id}/runtime/desired-state",
        json={"desired_state": "running"},
    )
    assert resp_unauth.status_code == 401

    # Login
    login_resp = client.post("/api/v1/auth/login", json={"password": admin_pass})
    csrf_token = login_resp.json()["csrf_token"]

    # 2. Authenticated but missing CSRF -> 403
    resp_no_csrf = client.patch(
        f"/api/v1/profiles/{prof_id}/runtime/desired-state",
        json={"desired_state": "running"},
        headers={"Origin": allowed_origin},
    )
    assert resp_no_csrf.status_code == 403

    # 3. Authenticated but wrong Origin -> 403
    resp_bad_origin = client.patch(
        f"/api/v1/profiles/{prof_id}/runtime/desired-state",
        json={"desired_state": "running"},
        headers={
            "X-CSRF-Token": csrf_token,
            "Origin": "https://unauthorized-origin.com",
        },
    )
    assert resp_bad_origin.status_code == 403


# TDD removal note: test_startup_requires_explicit_allowed_origins removed because
# CBROWSER_ALLOWED_ORIGINS and create_app(allowed_origins=...) were retired per t042 AC-007;
# Origin whitelist is now derived strictly and deterministically from AppliedNetworkAccessVersion.
def test_applied_network_origin_single_source_and_unlisted_rejected(tmp_path: Path) -> None:
    """t042 AC-007: Origin whitelist is derived from applied network version, unlisted is 403."""
    db_file = tmp_path / "origin_strict.db"
    run_database_migrations(db_file)
    admin_pass = secrets.token_urlsafe(32)
    admin_pwd_file = tmp_path / "admin_pass.txt"
    admin_pwd_file.write_text(admin_pass, encoding="utf-8")
    admin_pwd_file.chmod(0o600)

    app = create_app(
        db_path=db_file,
        admin_password_file=admin_pwd_file,
    )
    with TestClient(app, base_url="https://127.0.0.1:56661") as client:
        # Applied whitelist has https://127.0.0.1:56661
        login = client.post("/api/v1/auth/login", json={"password": admin_pass})
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]

        # Unlisted origin is rejected with 403
        resp_bad = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf, "Origin": "https://unauthorized.evil.com"},
        )
        assert resp_bad.status_code == 403

        # Valid applied origin succeeds
        resp_ok = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf, "Origin": "https://127.0.0.1:56661"},
        )
        assert resp_ok.status_code == 200


def test_allowed_origin_with_trailing_slash_is_accepted(tmp_path: Path) -> None:
    db_file = tmp_path / "origin_slash.db"
    run_database_migrations(db_file)
    admin_pass = secrets.token_urlsafe(32)
    admin_pwd_file = tmp_path / "admin_pass.txt"
    admin_pwd_file.write_text(admin_pass, encoding="utf-8")
    admin_pwd_file.chmod(0o600)
    gateway_token = secrets.token_urlsafe(32)
    gateway_token_file = tmp_path / "gateway_token.txt"
    gateway_token_file.write_text(gateway_token, encoding="utf-8")
    gateway_token_file.chmod(0o600)

    app = create_app(
        db_path=db_file,
        admin_password_file=admin_pwd_file,
        gateway_token_file=gateway_token_file,
    )
    with TestClient(app, base_url="https://127.0.0.1:56661") as client:
        login = client.post("/api/v1/auth/login", json={"password": admin_pass})
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        logout = client.post(
            "/api/v1/auth/logout",
            headers={
                "X-CSRF-Token": csrf,
                "Origin": "https://127.0.0.1:56661/",
            },
        )
        assert logout.status_code == 200


def test_login_uses_xff_from_trusted_proxy_and_returns_retry_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CBROWSER_TRUSTED_PROXY_CIDRS", "127.0.0.1/32")
    db_file = tmp_path / "xff.db"
    run_database_migrations(db_file)
    admin_pass = secrets.token_urlsafe(32)
    admin_pwd_file = tmp_path / "admin_pass_xff.txt"
    admin_pwd_file.write_text(admin_pass, encoding="utf-8")
    admin_pwd_file.chmod(0o600)
    gateway_token = secrets.token_urlsafe(32)
    gateway_token_file = tmp_path / "gateway_token_xff.txt"
    gateway_token_file.write_text(gateway_token, encoding="utf-8")
    gateway_token_file.chmod(0o600)

    app = create_app(
        db_path=db_file,
        admin_password_file=admin_pwd_file,
        gateway_token_file=gateway_token_file,
    )
    with TestClient(
        app, base_url="https://127.0.0.1:56661", client=("127.0.0.1", 4321)
    ) as client:
        for _ in range(5):
            resp = client.post(
                "/api/v1/auth/login",
                json={"password": "wrong_password"},
                headers={"X-Forwarded-For": "203.0.113.10"},
            )
            assert resp.status_code == 401
        limited = client.post(
            "/api/v1/auth/login",
            json={"password": "wrong_password"},
            headers={"X-Forwarded-For": "203.0.113.10"},
        )
        assert limited.status_code == 429
        assert int(limited.headers["Retry-After"]) >= 1

        # A different forwarded client is counted independently.
        other = client.post(
            "/api/v1/auth/login",
            json={"password": "wrong_password"},
            headers={"X-Forwarded-For": "203.0.113.11"},
        )
        assert other.status_code == 401
