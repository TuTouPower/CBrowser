"""Real HTTP integration: SSE Last-Event-ID across an API process restart."""

from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path

import httpx
import pytest
import uvicorn
from cbrowser.api.app import create_app
from cbrowser.domain.models import ProfileRuntimeStatusEvent


async def _start_api(
    db_path: Path, admin_pwd_file: Path, origin: str
) -> tuple[uvicorn.Server, asyncio.Task, str]:
    app = create_app(
        db_path=db_path,
        admin_password_file=admin_pwd_file,
        allowed_origins=[origin],
    )
    config = uvicorn.Config(app=app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, task, f"http://127.0.0.1:{port}"


async def _stop_api(server: uvicorn.Server, task: asyncio.Task) -> None:
    server.should_exit = True
    await task


async def _login(client: httpx.AsyncClient, origin: str, password: str) -> dict:
    response = await client.post("/api/v1/auth/login", json={"password": password})
    assert response.status_code == 200
    csrf_token = response.json()["csrf_token"]
    session_token = response.cookies.get("cbrowser_session")
    return {
        "auth_headers": {
            "Origin": origin,
            "X-CSRF-Token": csrf_token,
            "Cookie": f"cbrowser_session={session_token}",
        },
        "sse_headers": {"Cookie": f"cbrowser_session={session_token}"},
    }


async def _read_event(lines) -> tuple[str, dict]:
    collected: list[str] = []
    while True:
        line = await lines.__anext__()
        collected.append(line)
        if line == "" and any(ln.startswith("data: ") for ln in collected):
            break
    event_id = next(ln[len("id: ") :] for ln in collected if ln.startswith("id: "))
    data_line = next(ln for ln in collected if ln.startswith("data: "))
    return event_id, json.loads(data_line[len("data: ") :])


@pytest.mark.asyncio
async def test_last_event_id_from_previous_api_epoch_receives_snapshot(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "sse_epoch.db"
    admin_pwd_file = tmp_path / "admin_pwd.txt"
    admin_pwd = secrets.token_urlsafe(32)
    admin_pwd_file.write_text(admin_pwd, encoding="utf-8")
    origin = "https://app.cbrowser.local"

    first_server, first_task, first_url = await _start_api(
        db_path, admin_pwd_file, origin
    )
    try:
        async with httpx.AsyncClient(base_url=first_url, trust_env=False) as client:
            auth = await _login(client, origin, admin_pwd)
            profile_a = await client.post(
                "/api/v1/profiles",
                json={"name": "epoch_a"},
                headers=auth["auth_headers"],
            )
            assert profile_a.status_code == 201
            profile_a_id = profile_a.json()["id"]

            async with client.stream(
                "GET", "/api/v1/events", headers=auth["sse_headers"]
            ) as response:
                assert response.status_code == 200
                event_lines = response.aiter_lines()
                await _read_event(event_lines)
                patch = await client.patch(
                    f"/api/v1/profiles/{profile_a_id}/runtime/desired-state",
                    json={"desired_state": "running"},
                    headers=auth["auth_headers"],
                )
                assert patch.status_code == 200
                old_event_id, old_event = await _read_event(event_lines)
                assert old_event["profile_id"] == profile_a_id
    finally:
        await _stop_api(first_server, first_task)

    second_server, second_task, second_url = await _start_api(
        db_path, admin_pwd_file, origin
    )
    try:
        async with httpx.AsyncClient(base_url=second_url, trust_env=False) as client:
            auth = await _login(client, origin, admin_pwd)
            profile_b = await client.post(
                "/api/v1/profiles",
                json={"name": "epoch_b"},
                headers=auth["auth_headers"],
            )
            assert profile_b.status_code == 201
            profile_b_id = profile_b.json()["id"]

            app = second_server.config.app
            await app.state.coordinator.broadcaster.publish(
                ProfileRuntimeStatusEvent(
                    profile_id=profile_b_id,
                    desired_state="running",
                    observed_state="starting",
                    updated_at="2026-10-31T00:00:00Z",
                )
            )

            headers = {
                **auth["sse_headers"],
                "Last-Event-ID": old_event_id,
            }
            seen_profile_ids: list[str] = []
            snapshot_event_id = ""
            async with client.stream(
                "GET", "/api/v1/events", headers=headers
            ) as response:
                assert response.status_code == 200
                event_lines = response.aiter_lines()
                for _ in range(4):
                    try:
                        new_event_id, payload = await asyncio.wait_for(
                            _read_event(event_lines), timeout=1.0
                        )
                    except TimeoutError:
                        break
                    seen_profile_ids.append(payload["profile_id"])
                    if payload["profile_id"] == profile_a_id:
                        assert payload["desired_state"] == "running"
                        snapshot_event_id = new_event_id
                        break

            assert profile_a_id in seen_profile_ids
            assert snapshot_event_id.rsplit(":", 1)[0] != old_event_id.rsplit(":", 1)[0]
    finally:
        await _stop_api(second_server, second_task)
