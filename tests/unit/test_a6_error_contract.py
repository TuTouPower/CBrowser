"""A6: structured business error contract for HTTPException responses."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

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
    handler = app.exception_handlers[HTTPException]
    resp = await handler(MagicMock(), HTTPException(404, "Profile p1 not found"))
    assert resp.status_code == 404
    body = _body(resp)
    assert body["error"] == "not_found"
    assert body["message"] == "Profile p1 not found"
    assert body["retryable"] is False
    assert "detail" not in body
    assert "{" not in body["message"]


@pytest.mark.asyncio
async def test_handler_preserves_dict_code_message_and_detail(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[HTTPException]
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
    assert body["detail"] == detail
    assert body["retryable"] is False
    assert "{'" not in body["message"]
    assert "Traceback" not in json.dumps(body)


@pytest.mark.asyncio
async def test_handler_dict_without_message_has_no_repr(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[HTTPException]
    resp = await handler(
        MagicMock(), HTTPException(409, detail={"code": "proxy_in_use", "used_by_count": 2})
    )
    body = _body(resp)
    assert body["error"] == "proxy_in_use"
    assert isinstance(body["message"], str)
    assert "{" not in body["message"]
    assert body["detail"]["used_by_count"] == 2
    assert body["retryable"] is False


@pytest.mark.asyncio
async def test_handler_honors_explicit_retryable(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[HTTPException]
    resp = await handler(
        MagicMock(),
        HTTPException(409, detail={"code": "busy", "message": "busy", "retryable": True}),
    )
    body = _body(resp)
    assert body["error"] == "busy"
    assert body["retryable"] is True
    assert body["detail"]["retryable"] is True


@pytest.mark.asyncio
async def test_handler_422_uses_validation_detail(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[HTTPException]
    resp = await handler(MagicMock(), HTTPException(422, "invalid value"))
    assert resp.status_code == 422
    body = _body(resp)
    assert body["error"] == "validation_error"
    assert isinstance(body["detail"], list)
    assert body["detail"][0]["loc"] == ["body"]
    assert body["retryable"] is False
    assert isinstance(body["message"], str) and body["message"]


@pytest.mark.asyncio
async def test_handler_503_is_retryable(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[HTTPException]
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
        assert body["detail"]["code"] == "control_second_agent"
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
            json={"name": "px", "scheme": "http", "host": "127.0.0.1", "port": 8080},
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
        assert body["detail"]["code"] == "proxy_in_use"
        assert body["detail"]["used_by_count"] >= 1
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
        assert isinstance(body["detail"], list)
        assert body["retryable"] is False
        assert isinstance(body["message"], str) and body["message"]
        missing = client.get(
            "/api/v1/network/operations/does-not-exist"
        )
        assert missing.status_code == 404
        not_found = missing.json()
        assert not_found["error"] == "not_found"
        assert "{" not in not_found["message"]
        assert not_found["retryable"] is False
