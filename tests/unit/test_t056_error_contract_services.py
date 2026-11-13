"""t056 A15 / AC-004: Gateway and Supervisor error responses use the same
unified ErrorResponse shape as the API (error / message / retryable, no
whole-detail nesting)."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

import httpx
import pytest
from cbrowser.gateway.server import _error_response, supervisor_fence_failure
from cbrowser.supervisor.control_server import create_control_app


def _parse_gateway_response(resp) -> dict:
    assert resp.content_type == "application/json"
    return json.loads(resp.body.decode("utf-8"))


# ---------------------------------------------------------------- Gateway


def test_gateway_fence_failure_is_unified_error() -> None:
    resp = supervisor_fence_failure(None, "p1", "inst-1")
    assert resp is not None
    assert resp.status == 503
    body = _parse_gateway_response(resp)
    assert body["error"] == "agent_unavailable"
    assert body["message"] == "Agent for profile p1 is unavailable"
    assert body["retryable"] is True
    assert "detail" not in body


def test_gateway_fence_conflict_is_unified_error() -> None:
    from types import SimpleNamespace

    agent = SimpleNamespace(instance_id="inst-9", ws=SimpleNamespace(closed=False))
    resp = supervisor_fence_failure(agent, "p1", "inst-1")
    assert resp is not None
    assert resp.status == 409
    body = _parse_gateway_response(resp)
    assert body["error"] == "instance_conflict"
    assert "inst-9" in body["message"] and "inst-1" in body["message"]
    assert body["retryable"] is False
    assert "detail" not in body


def test_gateway_error_response_shape() -> None:
    resp = _error_response(400, "bad_request", "Invalid JSON body")
    assert resp.status == 400
    body = _parse_gateway_response(resp)
    assert body == {
        "error": "bad_request",
        "message": "Invalid JSON body",
        "retryable": False,
    }


# ---------------------------------------------------------------- Supervisor


def _supervisor_app(tmp_path: Path, token: str):
    key = tmp_path / "supervisor-key"
    key.write_text(token)
    key.chmod(0o600)
    from types import SimpleNamespace

    return create_control_app(SimpleNamespace(), key)


@pytest.mark.asyncio
async def test_supervisor_401_is_unified_error(tmp_path: Path) -> None:
    token = secrets.token_urlsafe(32)
    app = _supervisor_app(tmp_path, token)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://supervisor"
    ) as client:
        denied = await client.get("/supervisor/v1/health")
        assert denied.status_code == 401
        body = denied.json()
        assert body["error"] == "unauthorized"
        assert isinstance(body["message"], str) and body["message"]
        assert body["retryable"] is False
        assert "detail" not in body
        assert token not in denied.text


@pytest.mark.asyncio
async def test_supervisor_404_is_unified_error(tmp_path: Path) -> None:
    token = secrets.token_urlsafe(32)
    app = _supervisor_app(tmp_path, token)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://supervisor"
    ) as client:
        missing = await client.get(
            "/supervisor/v1/no-such-route",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert missing.status_code == 404
        body = missing.json()
        assert body["error"] == "not_found"
        assert isinstance(body["message"], str) and body["message"]
        assert "detail" not in body


@pytest.mark.asyncio
async def test_supervisor_422_is_unified_error(tmp_path: Path) -> None:
    token = secrets.token_urlsafe(32)
    app = _supervisor_app(tmp_path, token)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://supervisor"
    ) as client:
        invalid = await client.post(
            "/supervisor/v1/profiles/start",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert invalid.status_code == 422
        body = invalid.json()
        assert body["error"] == "validation_error"
        assert isinstance(body["message"], str) and body["message"]
        assert isinstance(body["details"], list) and body["details"]
        assert "detail" not in body
