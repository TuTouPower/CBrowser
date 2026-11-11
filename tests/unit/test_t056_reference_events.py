"""t056 A31 / AC-012: group/proxy writes publish SSE change events.

Backend: after a successful group/proxy create/update/delete/reorder the
coordinator publishes a ``groups_changed`` / ``proxies_changed`` transient
frame; a subscribed SSE client receives it.  A probe does not change
reference data and publishes nothing.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from cbrowser.api.runtime_coordinator import RuntimeCoordinator


def _coordinator() -> RuntimeCoordinator:
    return RuntimeCoordinator(
        supervisor_url=None,
        supervisor_token="x" * 32,
        profile_service=object(),
    )


@pytest.mark.asyncio
async def test_reference_change_reaches_subscriber() -> None:
    coordinator = _coordinator()
    seen: list[str] = []

    async def drain():
        async for frame in coordinator.broadcaster.subscribe():
            seen.append(frame)
            if len(seen) >= 2:
                return

    task = asyncio.create_task(drain())
    try:
        await asyncio.sleep(0.05)
        coordinator.publish_reference_change_later("groups_changed", "g1")
        coordinator.publish_reference_change_later("proxies_changed", None)
        await asyncio.wait_for(task, timeout=5)
    finally:
        if not task.done():
            task.cancel()
        await coordinator.stop()
    assert len(seen) == 2
    assert seen[0].startswith("event: groups_changed\n")
    assert '"entity_id":"g1"' in seen[0]
    assert seen[1].startswith("event: proxies_changed\n")
    assert '"entity_id":null' in seen[1]


# ------------------------------------------------------------- router level


def _app_with_recorder(tmp_path):
    from fastapi.testclient import TestClient

    from api_auth import create_auth_context
    from cbrowser.api.app import create_app

    ctx = create_auth_context(tmp_path)
    app = create_app(
        db_path=tmp_path / "ref_events.db",
        admin_password_file=ctx.admin_password_file,
        artifacts_root=tmp_path / "artifacts",
    )
    calls: list[tuple[str, str | None]] = []
    recorder = SimpleNamespace(
        publish_profile_change_later=lambda pid: None,
        publish_reference_change_later=lambda name, entity_id=None: calls.append(
            (name, entity_id)
        ),
        trigger_reconcile=lambda pid: None,
    )
    # The app's lifespan installs its own coordinator on startup, so the
    # recorder is attached after entering the TestClient context (see the
    # per-test attach() call below), not here.
    return app, ctx, calls, recorder


def _login(client, ctx) -> dict[str, str]:
    login = client.post("/api/v1/auth/login", json={"password": ctx.admin_password})
    assert login.status_code == 200
    return {
        "X-CSRF-Token": login.json()["csrf_token"],
        "Origin": ctx.allowed_origin,
    }


def test_group_writes_publish_groups_changed(tmp_path) -> None:
    from fastapi.testclient import TestClient

    app, ctx, calls, recorder = _app_with_recorder(tmp_path)
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        app.state.coordinator = recorder
        headers = _login(client, ctx)
        group = client.post(
            "/api/v1/groups",
            json={"name": "Work", "color": "blue", "sort_order": 0},
            headers=headers,
        ).json()
        assert ("groups_changed", group["id"]) in calls
        calls.clear()
        client.patch(
            f"/api/v1/groups/{group['id']}",
            json={"name": "Renamed"},
            headers=headers,
        )
        assert ("groups_changed", group["id"]) in calls
        calls.clear()
        client.post(
            "/api/v1/groups/reorder",
            json={"ordered_ids": [group["id"]]},
            headers=headers,
        )
        assert ("groups_changed", None) in calls
        calls.clear()
        assert (
            client.delete(f"/api/v1/groups/{group['id']}", headers=headers).status_code
            == 204
        )
        assert ("groups_changed", group["id"]) in calls


def test_proxy_writes_publish_proxies_changed(tmp_path) -> None:
    from fastapi.testclient import TestClient

    app, ctx, calls, recorder = _app_with_recorder(tmp_path)
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        app.state.coordinator = recorder
        headers = _login(client, ctx)
        proxy = client.post(
            "/api/v1/proxies",
            json={
                "name": "px",
                "proxy_url": "http://user:secret@proxy.example.com:8080",
            },
            headers=headers,
        ).json()
        assert ("proxies_changed", proxy["id"]) in calls
        calls.clear()
        client.patch(
            f"/api/v1/proxies/{proxy['id']}",
            json={"name": "renamed"},
            headers=headers,
        )
        assert ("proxies_changed", proxy["id"]) in calls
        calls.clear()
        assert (
            client.delete(f"/api/v1/proxies/{proxy['id']}", headers=headers).status_code
            == 204
        )
        assert ("proxies_changed", proxy["id"]) in calls


def test_proxy_probe_publishes_nothing(tmp_path) -> None:
    from fastapi.testclient import TestClient

    app, ctx, calls, recorder = _app_with_recorder(tmp_path)
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        app.state.coordinator = recorder
        headers = _login(client, ctx)
        proxy = client.post(
            "/api/v1/proxies",
            json={
                "name": "px",
                "proxy_url": "http://user:secret@proxy.example.com:8080",
            },
            headers=headers,
        ).json()
        calls.clear()
        client.post(f"/api/v1/proxies/{proxy['id']}/probe", headers=headers)
        assert calls == []
