"""Integration tests for the edge viewer-authorize resolver (t064).

Caddy's forward_auth calls GET /api/v1/internal/edge/viewer-authorize
before proxying a viewer signal handshake to the Gateway. The endpoint is
the only place the management session cookie is resolved into an
authorization context: it authenticates the edge caller by the deployment
edge-proof secret, re-validates session/Origin/Profile through
AuthService, and answers with a short-lived viewer grant for the Gateway.
"""

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
from cbrowser.shared.viewer_grants import (
    AUTHORIZED_PROFILE_HEADER,
    EDGE_PROOF_HEADER,
    VIEWER_GRANT_HEADER,
    ViewerGrantAuthority,
)
from fastapi.testclient import TestClient

EDGE_PATH = "/api/v1/internal/edge/viewer-authorize"
PROFILE_ID = "prof-edge-064"


def _write_secret(tmp_path: Path, name: str) -> tuple[str, Path]:
    value = secrets.token_urlsafe(32)
    path = tmp_path / name
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)
    return value, path


@pytest.fixture
def edge_env(tmp_path: Path):
    db_file = tmp_path / "edge_auth.db"
    run_database_migrations(db_file)

    admin_pass, admin_pwd_file = _write_secret(tmp_path, "admin_pass.txt")
    gateway_token, gateway_token_file = _write_secret(tmp_path, "gateway_token.txt")
    edge_proof, edge_proof_file = _write_secret(tmp_path, "edge_proof_key")
    _, grant_key_file = _write_secret(tmp_path, "viewer_grant_key")

    origin = "https://127.0.0.1:56661"
    app = create_app(
        db_path=db_file,
        admin_password_file=admin_pwd_file,
        gateway_token_file=gateway_token_file,
        edge_proof_file=edge_proof_file,
        viewer_grant_key_file=grant_key_file,
    )

    async def _seed_profile() -> None:
        engine, session_maker = create_engine_and_maker(db_file)
        async with session_maker() as session, write_transaction(session):
            session.add(
                ProfileModel(
                    display_number=1,
                    id=PROFILE_ID,
                    name="Edge Profile",
                    fingerprint_seed=424242,
                    user_data_dir="/tmp/edge",
                )
            )
        await engine.dispose()

    import asyncio

    asyncio.run(_seed_profile())

    with TestClient(app, base_url=origin) as client:
        yield {
            "client": client,
            "admin_pass": admin_pass,
            "gateway_token": gateway_token,
            "edge_proof": edge_proof,
            "grant_key_file": grant_key_file,
            "allowed_origin": origin,
        }


def _login(edge_env) -> tuple[str, str]:
    resp = edge_env["client"].post(
        "/api/v1/auth/login", json={"password": edge_env["admin_pass"]}
    )
    assert resp.status_code == 200
    session_cookie = resp.cookies.get("cbrowser_session")
    assert session_cookie
    return session_cookie, resp.json()["csrf_token"]


def _authorize(edge_env, *, proof, uri, cookie=None, origin=None):
    headers = {"X-Forwarded-Uri": uri}
    if proof is not None:
        headers[EDGE_PROOF_HEADER] = proof
    if cookie is not None:
        headers["Cookie"] = f"cbrowser_session={cookie}"
    if origin is not None:
        headers["Origin"] = origin
    return edge_env["client"].get(EDGE_PATH, headers=headers)


def test_missing_or_wrong_edge_proof_is_forbidden(edge_env):
    cookie, _ = _login(edge_env)
    uri = f"/stream/{PROFILE_ID}/signal"
    missing = _authorize(edge_env, proof=None, uri=uri, cookie=cookie)
    assert missing.status_code == 403
    assert VIEWER_GRANT_HEADER not in missing.headers
    wrong = _authorize(
        edge_env, proof=secrets.token_urlsafe(32), uri=uri, cookie=cookie
    )
    assert wrong.status_code == 403
    assert VIEWER_GRANT_HEADER not in wrong.headers


def test_missing_or_invalid_session_is_unauthorized(edge_env):
    uri = f"/stream/{PROFILE_ID}/signal"
    missing = _authorize(edge_env, proof=edge_env["edge_proof"], uri=uri)
    assert missing.status_code == 401
    bogus = _authorize(
        edge_env,
        proof=edge_env["edge_proof"],
        uri=uri,
        cookie="not-a-session",
        origin=edge_env["allowed_origin"],
    )
    assert bogus.status_code == 401


def test_bad_origin_and_unknown_profile_are_forbidden(edge_env):
    cookie, _ = _login(edge_env)
    bad_origin = _authorize(
        edge_env,
        proof=edge_env["edge_proof"],
        uri=f"/stream/{PROFILE_ID}/signal",
        cookie=cookie,
        origin="https://attacker.example",
    )
    assert bad_origin.status_code == 403
    unknown_profile = _authorize(
        edge_env,
        proof=edge_env["edge_proof"],
        uri="/stream/prof-missing/signal",
        cookie=cookie,
        origin=edge_env["allowed_origin"],
    )
    assert unknown_profile.status_code == 403


def test_non_signal_forwarded_uri_is_forbidden(edge_env):
    cookie, _ = _login(edge_env)
    for uri in ("/api/v1/profiles", f"/stream/{PROFILE_ID}/other", "/stream//signal"):
        resp = _authorize(
            edge_env,
            proof=edge_env["edge_proof"],
            uri=uri,
            cookie=cookie,
            origin=edge_env["allowed_origin"],
        )
        assert resp.status_code == 403, uri


def test_happy_path_returns_gateway_verifiable_grant(edge_env):
    cookie, _ = _login(edge_env)
    resp = _authorize(
        edge_env,
        proof=edge_env["edge_proof"],
        uri=f"/stream/{PROFILE_ID}/signal",
        cookie=cookie,
        origin=edge_env["allowed_origin"],
    )
    assert resp.status_code == 200
    assert resp.headers[AUTHORIZED_PROFILE_HEADER] == PROFILE_ID
    grant = resp.headers[VIEWER_GRANT_HEADER]
    authority = ViewerGrantAuthority(edge_env["grant_key_file"])
    claims = authority.verify(grant, PROFILE_ID)
    assert claims is not None
    assert claims.profile_id == PROFILE_ID
    assert authority.verify(grant, "prof-other") is None


def test_revoked_session_no_longer_authorizes(edge_env):
    cookie, csrf_token = _login(edge_env)
    uri = f"/stream/{PROFILE_ID}/signal"
    ok = _authorize(
        edge_env,
        proof=edge_env["edge_proof"],
        uri=uri,
        cookie=cookie,
        origin=edge_env["allowed_origin"],
    )
    assert ok.status_code == 200
    logout = edge_env["client"].post(
        "/api/v1/auth/logout",
        headers={
            "Origin": edge_env["allowed_origin"],
            "X-CSRF-Token": csrf_token,
            "Cookie": f"cbrowser_session={cookie}",
        },
    )
    assert logout.status_code == 200
    after = _authorize(
        edge_env,
        proof=edge_env["edge_proof"],
        uri=uri,
        cookie=cookie,
        origin=edge_env["allowed_origin"],
    )
    assert after.status_code == 401


def test_old_gateway_viewer_authorize_endpoint_is_gone(edge_env):
    removed = edge_env["client"].post(
        "/api/v1/internal/gateway/viewer-authorize",
        json={"session_cookie": "x", "origin": "https://127.0.0.1:56661", "profile_id": PROFILE_ID},
        headers={"Authorization": f"Bearer {edge_env['gateway_token']}"},
    )
    assert removed.status_code == 404


def test_unconfigured_edge_authorization_fails_closed(tmp_path: Path):
    db_file = tmp_path / "edge_unconfigured.db"
    run_database_migrations(db_file)
    _, admin_pwd_file = _write_secret(tmp_path, "admin_pass.txt")
    _, gateway_token_file = _write_secret(tmp_path, "gateway_token.txt")
    app = create_app(
        db_path=db_file,
        admin_password_file=admin_pwd_file,
        gateway_token_file=gateway_token_file,
    )
    with TestClient(app, base_url="https://127.0.0.1:56661") as client:
        resp = client.get(
            EDGE_PATH,
            headers={
                EDGE_PROOF_HEADER: "anything",
                "X-Forwarded-Uri": f"/stream/{PROFILE_ID}/signal",
            },
        )
    assert resp.status_code == 503
