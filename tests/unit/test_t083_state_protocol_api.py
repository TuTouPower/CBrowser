"""t083: API side of the minimal batch state protocol.

Covers the snapshot endpoint (auth, keyset batching, minimal DTO
shape), the deletion of the old internal rich routes, the
state_revision fence increments on every runtime write path, the
coordinator's pushed change notices, and runtime GET purity.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.app import create_app
from cbrowser.api.runtime_coordinator import RuntimeCoordinator
from cbrowser.api.v1.router import get_profile_runtime
from cbrowser.domain.models import ProfileConfig
from cbrowser.services.profile_service import ProfileService
from cbrowser.shared.state_protocol import API_EPOCH
from fastapi.testclient import TestClient

ORIGIN = "https://127.0.0.1:56661"
MINIMAL_KEYS = {
    "profile_id",
    "display_number",
    "desired_state",
    "observed_state",
    "runtime_instance_id",
    "config_version",
    "failure_count",
    "restart_blocked",
    "last_exit_event_id",
    "backoff_started_at",
    "next_retry_at",
    "updated_at",
    "state_revision",
}


async def _make_service(tmp_path: Path) -> tuple[ProfileService, object]:
    db_path = tmp_path / "t083.db"
    run_database_migrations(db_path)
    engine, maker = create_engine_and_maker(db_path)
    return ProfileService(ProfileRepository(maker)), engine


@pytest.fixture
async def service(tmp_path: Path):
    svc, engine = await _make_service(tmp_path)
    yield svc
    await engine.dispose()


@pytest.mark.asyncio
async def test_state_revision_increments_on_every_write_path(service):
    profile = await service.create_profile(ProfileConfig(name="rev"))
    rt = await service.get_runtime(profile.id)
    assert rt.state_revision == 0

    await service.set_desired_state(profile.id, "running")
    rt = await service.get_runtime(profile.id)
    assert rt.state_revision == 1

    await service.bind_runtime_instance(
        profile.id, "inst_rev", config_version=1
    )
    rt = await service.get_runtime(profile.id)
    assert rt.state_revision == 2

    await service.report_observed_state(profile.id, "inst_rev", "running")
    rt = await service.get_runtime(profile.id)
    assert rt.state_revision == 3


def _make_app(tmp_path: Path):
    admin_file = tmp_path / "admin.pwd"
    admin_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    admin_file.chmod(0o600)
    token = secrets.token_urlsafe(32)
    token_file = tmp_path / "supervisor.token"
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)
    app = create_app(
        db_path=tmp_path / "svc.db",
        admin_password_file=admin_file,
        supervisor_token_file=token_file,
        include_internal_schema=True,
    )
    return app, token


@pytest.mark.asyncio
async def test_snapshot_endpoint_batches_and_old_routes_are_gone(
    tmp_path: Path,
):
    db_path = tmp_path / "svc.db"
    run_database_migrations(db_path)
    engine, maker = create_engine_and_maker(db_path)
    svc = ProfileService(ProfileRepository(maker))
    ids = []
    for name in ("s1", "s2", "s3"):
        created = await svc.create_profile(ProfileConfig(name=name))
        ids.append(created.id)
    await engine.dispose()

    app, token = _make_app(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app, base_url=ORIGIN) as client:
        # Service auth is mandatory.
        assert (
            client.get("/api/v1/internal/supervisor/state/snapshot").status_code
            == 401
        )
        # First batch: declared limit 2, keyset cursor follows.
        first = client.get(
            "/api/v1/internal/supervisor/state/snapshot",
            headers=headers,
            params={"limit": 2},
        )
        assert first.status_code == 200
        body = first.json()
        assert body["api_epoch"] == API_EPOCH
        # Keyset order is profile_id ascending (the pagination key), not
        # creation order.
        ordered = sorted(ids)
        assert [p["profile_id"] for p in body["profiles"]] == ordered[:2]
        assert body["next_cursor"] == ordered[1]
        for entry in body["profiles"]:
            assert set(entry.keys()) == MINIMAL_KEYS
        second = client.get(
            "/api/v1/internal/supervisor/state/snapshot",
            headers=headers,
            params={"limit": 2, "cursor": body["next_cursor"]},
        )
        assert second.status_code == 200
        body2 = second.json()
        assert [p["profile_id"] for p in body2["profiles"]] == ordered[2:]
        assert body2["next_cursor"] is None

        # The old internal rich routes no longer exist.
        assert (
            client.get(
                "/api/v1/internal/supervisor/profiles", headers=headers
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/v1/internal/supervisor/profiles/{ids[0]}/runtime",
                headers=headers,
            ).status_code
            == 404
        )


@pytest.mark.asyncio
async def test_publish_pushes_minimal_notice_and_removal(service):
    profile = await service.create_profile(ProfileConfig(name="push"))
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"status": "ok"})

    coord = RuntimeCoordinator(
        supervisor_url="http://supervisor.internal:8005",
        supervisor_token="".join(["supervisor", "-token"]),
        profile_service=service,
        transport=httpx.MockTransport(handler),
    )
    try:
        await coord.publish_profile_change(profile.id)
        notices = [
            r for r in captured if r.url.path == "/supervisor/v1/state-changes"
        ]
        assert len(notices) == 1
        payload = json.loads(notices[0].content)
        assert payload["api_epoch"] == API_EPOCH
        assert payload["removed"] == []
        assert len(payload["states"]) == 1
        state = payload["states"][0]
        assert set(state.keys()) == MINIMAL_KEYS
        assert state["profile_id"] == profile.id

        captured.clear()
        await coord.publish_profile_change("missing-profile")
        notices = [
            r for r in captured if r.url.path == "/supervisor/v1/state-changes"
        ]
        assert len(notices) == 1
        payload = json.loads(notices[0].content)
        assert payload["states"] == []
        assert payload["removed"] == ["missing-profile"]
    finally:
        await coord.stop()


@pytest.mark.asyncio
async def test_runtime_get_never_refreshes_downstream(service):
    """AC-004: the runtime GET projects maintained observations only."""
    profile = await service.create_profile(ProfileConfig(name="pure"))

    class SpyCoordinator:
        def get_last_error(self, profile_id, runtime=None):
            return None

        def get_search_defaults(self, profile_id):
            return None

        def get_transport(self, profile_id):
            return None

        async def get_font_runtime(self, profile_id, runtime=None):
            return None, []

        async def refresh_transport(self, profile_id):
            raise AssertionError("GET must not refresh transport")

        async def refresh_search_defaults(self, profile_id):
            raise AssertionError("GET must not refresh search defaults")

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(coordinator=SpyCoordinator())
        )
    )
    response = await get_profile_runtime(profile.id, request, service)
    assert response.profile_id == profile.id
    assert response.transport is None
    assert response.search_defaults is None
