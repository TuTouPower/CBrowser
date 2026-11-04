"""t031 Supervisor close-tunnels endpoint (AC-002 close cascade)."""

from __future__ import annotations

import secrets
from pathlib import Path
from types import SimpleNamespace

import pytest
from cbrowser.supervisor.control_server import create_control_app
from fastapi.testclient import TestClient


@pytest.fixture
def supervisor_env(tmp_path: Path):
    token = secrets.token_urlsafe(32)
    token_file = tmp_path / "supervisor.txt"
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)
    released: list[str] = []

    async def release_attendant(profile_id: str) -> bool:
        released.append(profile_id)
        return True

    core = SimpleNamespace(release_dialog_attendant=release_attendant)
    app = create_control_app(core, token_file)
    with TestClient(app) as client:
        yield {
            "client": client,
            "app": app,
            "token": token,
            "released": released,
        }


def test_close_tunnels_closes_and_fences(supervisor_env) -> None:
    client = supervisor_env["client"]
    app = supervisor_env["app"]
    headers = {"Authorization": f"Bearer {supervisor_env['token']}"}
    closed: list[str] = []

    async def close_fn():
        closed.append("sup-tunnel")

    registry = app.state.supervisor_tunnels
    registry.register("p1", close_fn, generation=4)
    # Wrong token: 401.
    resp = client.post(
        "/supervisor/v1/profiles/p1/control/close-tunnels",
        json={"generation": 5},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401
    # Valid close: tunnel closed, attendant released, fence at 5.
    resp = client.post(
        "/supervisor/v1/profiles/p1/control/close-tunnels",
        json={"generation": 5},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile_id"] == "p1"
    assert body["generation"] == 5
    assert len(body["closed_tunnel_ids"]) == 1
    assert body["attendant_released"] is True
    assert closed == ["sup-tunnel"]
    assert supervisor_env["released"] == ["p1"]
    assert registry.is_generation_fenced("p1", 5) is True
    assert registry.is_generation_fenced("p1", 6) is False
    # A forwarded handshake at the fenced generation is stale.
    resp = client.post(
        "/supervisor/v1/profiles/p1/control/close-tunnels",
        json={"generation": 5},
        headers=headers,
    )
    assert resp.status_code == 200


def test_close_tunnels_empty_profile_still_fences(supervisor_env) -> None:
    client = supervisor_env["client"]
    app = supervisor_env["app"]
    headers = {"Authorization": f"Bearer {supervisor_env['token']}"}
    resp = client.post(
        "/supervisor/v1/profiles/p9/control/close-tunnels",
        json={"generation": 3},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["closed_tunnel_ids"] == []
    assert app.state.supervisor_tunnels.is_generation_fenced("p9", 3) is True
