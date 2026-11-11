"""A6 (t056 A15): unified ErrorResponse contract for HTTPException responses.

Rewritten wholesale in t056: the old shape nested the whole dict detail
under a ``detail`` key (duplicating the top-level error/message/retryable)
and used ``detail`` for the 422 field-error list.  The unified shape is
``error`` / ``message`` / ``retryable`` plus optional structured
``details`` that never repeat the top-level fields; 429 maps to
``rate_limited`` with a Retry-After header.  Two tests from the old file
survive verbatim (plain-string detail mapping, 503 retryable); the rest
were deleted and replaced with new-shape coverage below.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from api_auth import create_auth_context
from cbrowser.api.app import create_app


def _app(tmp_path: Path):
    ctx = create_auth_context(tmp_path)
    app = create_app(
        db_path=tmp_path / "a6.db",
        admin_password_file=ctx.admin_password_file,
        artifacts_root=tmp_path / "artifacts",
    )
    return app, ctx


def _login(client: TestClient, ctx) -> dict[str, str]:
    login = client.post("/api/v1/auth/login", json={"password": ctx.admin_password})
    assert login.status_code == 200
    return {
        "X-CSRF-Token": login.json()["csrf_token"],
        "Origin": ctx.allowed_origin,
    }


def _body(response) -> dict:
    return json.loads(response.body)


@pytest.mark.asyncio
async def test_handler_maps_plain_string_detail(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[StarletteHTTPException]
    resp = await handler(MagicMock(), HTTPException(404, "Profile p1 not found"))
    assert resp.status_code == 404
    body = _body(resp)
    assert body["error"] == "not_found"
    assert body["message"] == "Profile p1 not found"
    assert body["retryable"] is False
    assert "detail" not in body
    assert "{" not in body["message"]


@pytest.mark.asyncio
async def test_handler_dict_code_message_and_extra_to_details(tmp_path: Path) -> None:
    """t056 A15: a dict detail contributes code/message/retryable to the
    top level; only the *remaining* keys land in ``details`` — the whole
    dict is never nested again."""
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[StarletteHTTPException]
    detail = {
        "code": "control_second_agent",
        "message": "Another agent holds control for this profile",
        "used_by_count": 3,
    }
    resp = await handler(MagicMock(), HTTPException(409, detail=detail))
    assert resp.status_code == 409
    body = _body(resp)
    assert body["error"] == "control_second_agent"
    assert body["message"] == detail["message"]
    assert body["details"] == {"used_by_count": 3}
    assert "detail" not in body
    assert body["retryable"] is False
    assert "{" not in body["message"]
    assert "Traceback" not in json.dumps(body)


@pytest.mark.asyncio
async def test_handler_dict_without_message_details_only_extras(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[StarletteHTTPException]
    resp = await handler(
        MagicMock(), HTTPException(409, detail={"code": "proxy_in_use", "used_by_count": 2})
    )
    body = _body(resp)
    assert body["error"] == "proxy_in_use"
    assert isinstance(body["message"], str)
    assert "{" not in body["message"]
    assert body["details"] == {"used_by_count": 2}
    assert "detail" not in body
    assert body["retryable"] is False


@pytest.mark.asyncio
async def test_handler_dict_explicit_retryable_not_duplicated(tmp_path: Path) -> None:
    """When the dict carries nothing beyond code/message/retryable,
    there is no ``details`` key at all."""
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[StarletteHTTPException]
    resp = await handler(
        MagicMock(),
        HTTPException(409, detail={"code": "busy", "message": "busy", "retryable": True}),
    )
    body = _body(resp)
    assert body["error"] == "busy"
    assert body["retryable"] is True
    assert "details" not in body
    assert "detail" not in body


@pytest.mark.asyncio
async def test_handler_422_uses_validation_details(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[StarletteHTTPException]
    resp = await handler(MagicMock(), HTTPException(422, "invalid value"))
    assert resp.status_code == 422
    body = _body(resp)
    assert body["error"] == "validation_error"
    assert isinstance(body["details"], list)
    assert body["details"][0]["loc"] == ["body"]
    assert "detail" not in body
    assert body["retryable"] is False
    assert isinstance(body["message"], str) and body["message"]


@pytest.mark.asyncio
async def test_handler_429_maps_to_rate_limited(tmp_path: Path) -> None:
    """t056 A15 / AC-003: 429 maps to ``rate_limited`` and the
    Retry-After header set by the raiser passes through."""
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[StarletteHTTPException]
    resp = await handler(
        MagicMock(),
        HTTPException(
            429,
            detail="Too many failed login attempts, please try again later",
            headers={"Retry-After": "30"},
        ),
    )
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "30"
    body = _body(resp)
    assert body["error"] == "rate_limited"
    assert body["message"] == "Too many failed login attempts, please try again later"
    assert body["retryable"] is False
    assert "detail" not in body


@pytest.mark.asyncio
async def test_handler_503_is_retryable(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[StarletteHTTPException]
    resp = await handler(MagicMock(), HTTPException(503, "database is busy"))
    assert resp.status_code == 503
    body = _body(resp)
    assert body["error"] == "database_busy"
    assert body["message"] == "database is busy"
    assert body["retryable"] is True


def test_real_control_conflict_is_structured(tmp_path: Path) -> None:
    app, ctx = _app(tmp_path)
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        headers = _login(client, ctx)
        profile = client.post(
            "/api/v1/profiles", json={"name": "conflict"}, headers=headers
        ).json()
        pid = profile["id"]
        tokens = []
        for name in ("bot-a", "bot-b"):
            created = client.post(
                "/api/v1/automation/tokens",
                json={"name": name, "profile_ids": [pid]},
                headers=headers,
            )
            assert created.status_code == 201
            tokens.append(created.json())
        first = client.post(
            f"/api/v1/profiles/{pid}/control/claim",
            json={"agent_session_id": "exec-1"},
            headers={"Authorization": f"Bearer {tokens[0]['token']}"},
        )
        assert first.status_code == 200
        conflict = client.post(
            f"/api/v1/profiles/{pid}/control/claim",
            json={"agent_session_id": "exec-2"},
            headers={"Authorization": f"Bearer {tokens[1]['token']}"},
        )
        assert conflict.status_code == 409
        body = conflict.json()
        assert body["error"] == "control_second_agent"
        assert "detail" not in body
        assert isinstance(body["message"], str)
        assert body["retryable"] is False
        assert "{'" not in json.dumps(body)
        for token in tokens:
            assert token["token"] not in json.dumps(body)
        assert ctx.admin_password not in json.dumps(body)


def test_real_entity_reference_conflict_keeps_used_by_count(tmp_path: Path) -> None:
    app, ctx = _app(tmp_path)
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        headers = _login(client, ctx)
        proxy = client.post(
            "/api/v1/proxies",
            json={"name": "px", "proxy_url": "http://127.0.0.1:8080"},
            headers=headers,
        )
        assert proxy.status_code == 201
        proxy_id = proxy.json()["id"]
        profile = client.post(
            "/api/v1/profiles",
            json={"name": "bound", "proxy_id": proxy_id},
            headers=headers,
        )
        assert profile.status_code == 201
        conflict = client.delete(f"/api/v1/proxies/{proxy_id}", headers=headers)
        assert conflict.status_code == 409
        body = conflict.json()
        assert body["error"] == "proxy_in_use"
        assert body["details"]["used_by_count"] >= 1
        assert "detail" not in body
        assert body["retryable"] is False
        assert "{'" not in json.dumps(body)


def test_real_422_and_404_are_structured(tmp_path: Path) -> None:
    app, ctx = _app(tmp_path)
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        invalid = client.post(
            "/api/v1/profiles",
            json={"name": ""},
            headers=_login(client, ctx),
        )
        assert invalid.status_code == 422
        body = invalid.json()
        assert body["error"] == "validation_error"
        assert isinstance(body["details"], list)
        assert "detail" not in body
        assert body["retryable"] is False
        assert isinstance(body["message"], str) and body["message"]
        # t054: the old probe hit a deleted network route; a missing
        # profile is the surviving real-404 probe.
        missing = client.get(
            "/api/v1/profiles/does-not-exist",
            headers=_login(client, ctx),
        )
        assert missing.status_code == 404
        not_found = missing.json()
        assert not_found["error"] == "not_found"
        assert "{" not in not_found["message"]
        assert not_found["retryable"] is False


def test_real_login_rate_limit_is_rate_limited(tmp_path: Path) -> None:
    """t056 A15 / AC-003: five failed logins then a 429 whose error is
    ``rate_limited`` and which carries Retry-After."""
    app, ctx = _app(tmp_path)
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        for _ in range(5):
            failed = client.post(
                "/api/v1/auth/login", json={"password": "wrong-password"}
            )
            assert failed.status_code == 401
        limited = client.post(
            "/api/v1/auth/login", json={"password": "wrong-password"}
        )
        assert limited.status_code == 429
        assert "Retry-After" in limited.headers
        body = limited.json()
        assert body["error"] == "rate_limited"
        assert isinstance(body["message"], str) and body["message"]
        assert "detail" not in body


def test_real_unmatched_route_404_is_structured(tmp_path: Path) -> None:
    """t056 A15: even an unmatched route (Starlette raises its own
    HTTPException) returns the unified shape, not FastAPI's default
    ``{"detail": "Not Found"}``."""
    app, ctx = _app(tmp_path)
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        resp = client.get("/api/v1/no-such-route", headers=_login(client, ctx))
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"] == "not_found"
        assert "detail" not in body


def test_real_bind_bad_config_version_is_field_422(tmp_path: Path) -> None:
    """t056 A15: the InvalidConfigVersionError handler carries message +
    structured details and no whole-detail package."""
    from cbrowser.adapters.database.repository import InvalidConfigVersionError

    app, _ = _app(tmp_path)
    handler = app.exception_handlers[InvalidConfigVersionError]
    import asyncio

    resp = asyncio.run(
        handler(MagicMock(), InvalidConfigVersionError("Config version 99 does not exist"))
    )
    assert resp.status_code == 422
    body = _body(resp)
    assert body["error"] == "validation_error"
    assert body["message"] == "Config version 99 does not exist"
    assert body["details"][0]["loc"] == ["body", "config_version"]
    assert "detail" not in body
    assert body["retryable"] is False
