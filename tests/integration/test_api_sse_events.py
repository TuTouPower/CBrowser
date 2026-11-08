"""Integration tests for GET /api/v1/events against real uvicorn and SQLite."""

from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path

import httpx
import pytest
import uvicorn
from cbrowser.api.app import create_app


@pytest.fixture
async def uvicorn_server(tmp_path: Path):
    db_path = tmp_path / "sse_api.db"
    admin_pwd_file = tmp_path / "admin_pwd.txt"
    admin_pwd = secrets.token_urlsafe(32)
    admin_pwd_file.write_text(admin_pwd, encoding="utf-8")
    origin = "https://127.0.0.1:56661"

    app = create_app(
        db_path=db_path,
        admin_password_file=admin_pwd_file,
            )

    config = uvicorn.Config(app=app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)

    port = server.servers[0].sockets[0].getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"

    try:
        yield {
            "base_url": base_url,
            "origin": origin,
            "admin_pwd": admin_pwd,
            "app": app,
        }
    finally:
        server.should_exit = True
        await server_task


@pytest.mark.asyncio
async def test_sse_endpoint_requires_authentication(uvicorn_server):
    """GET /api/v1/events requires a valid session cookie; 401 otherwise."""
    base_url = uvicorn_server["base_url"]
    async with httpx.AsyncClient(base_url=base_url, trust_env=False) as client:
        resp = await client.get("/api/v1/events")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_sse_endpoint_streams_events_and_recovers_with_last_event_id(
    uvicorn_server,
):
    """Authenticated client gets a snapshot, live updates and Last-Event-ID catch-up."""
    base_url = uvicorn_server["base_url"]
    origin = uvicorn_server["origin"]
    admin_pwd = uvicorn_server["admin_pwd"]

    async with httpx.AsyncClient(base_url=base_url, trust_env=False) as client:
        # 1. Login
        login_resp = await client.post(
            "/api/v1/auth/login", json={"password": admin_pwd}
        )
        assert login_resp.status_code == 200
        csrf_token = login_resp.json()["csrf_token"]
        session_token = login_resp.cookies.get("cbrowser_session")
        auth_headers = {
            "Origin": origin,
            "X-CSRF-Token": csrf_token,
            "Cookie": f"cbrowser_session={session_token}",
        }
        sse_headers = {
            "Cookie": f"cbrowser_session={session_token}",
        }

        # 2. Create a profile
        p_resp = await client.post(
            "/api/v1/profiles", json={"name": "sse_profile_1"}, headers=auth_headers
        )
        assert p_resp.status_code == 201
        profile_id = p_resp.json()["id"]

        # 3. Connect to SSE stream and read initial snapshot
        async with client.stream(
            "GET", "/api/v1/events", headers=sse_headers
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

            lines = []
            async for line in response.aiter_lines():
                lines.append(line)
                if line == "" and len(lines) >= 3:
                    break

            raw_event = "\n".join(lines)
            assert "event: runtime_state" in raw_event
            assert profile_id in raw_event

            # Verify all 8 required fields in SSE payload
            data_line = next(ln for ln in lines if ln.startswith("data: "))
            payload = json.loads(data_line[len("data: ") :])
            for field in [
                "profile_id",
                "desired_state",
                "observed_state",
                "runtime_instance_id",
                "failure_count",
                "restart_blocked",
                "last_coordinator_error",
                "updated_at",
            ]:
                assert field in payload, (
                    f"Missing required field {field} in SSE payload"
                )

            last_id_line = next(ln for ln in lines if ln.startswith("id: "))
            last_event_id = last_id_line[len("id: ") :]

        # 4. Update desired-state while disconnected
        patch_resp = await client.patch(
            f"/api/v1/profiles/{profile_id}/runtime/desired-state",
            json={"desired_state": "running"},
            headers=auth_headers,
        )
        assert patch_resp.status_code == 200

        # 5. Reconnect with Last-Event-ID
        reconnect_headers = {
            **sse_headers,
            "Last-Event-ID": last_event_id,
        }
        async with client.stream(
            "GET", "/api/v1/events", headers=reconnect_headers
        ) as reconnect_resp:
            assert reconnect_resp.status_code == 200
            rec_lines = []
            async for line in reconnect_resp.aiter_lines():
                rec_lines.append(line)
                if line == "" and len(rec_lines) >= 3:
                    break

            raw_rec = "\n".join(rec_lines)
            assert "event: runtime_state" in raw_rec
            assert profile_id in raw_rec
            assert '"desired_state":"running"' in raw_rec
