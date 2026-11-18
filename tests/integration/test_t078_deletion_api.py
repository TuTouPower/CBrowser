"""t078: HTTP layer for the profile deletion lifecycle.

Real app + real SQLite DB via TestClient. POST /profile-deletions
accepts an explicit target set and returns durable per-target
operations; GET batch/operation exposes stage progress; retry resumes
a failed intent; DELETE /profiles/{id} drives the same lifecycle
synchronously (AC-003/AC-004/AC-005).
"""

from __future__ import annotations

import asyncio
import secrets
import time
from pathlib import Path

import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.app import create_app
from cbrowser.domain.models import ProfileConfig
from cbrowser.services.profile_service import ProfileService
from fastapi.testclient import TestClient

ORIGIN = "https://127.0.0.1:56661"


@pytest.fixture
def api_env(tmp_path: Path):
    db_file = tmp_path / "t078_api.db"
    run_database_migrations(db_file)
    admin_pwd_file = tmp_path / "admin_pwd.txt"
    admin_pwd = secrets.token_urlsafe(32)
    admin_pwd_file.write_text(admin_pwd, encoding="utf-8")

    engine, session_maker = create_engine_and_maker(db_file)
    service = ProfileService(
        ProfileRepository(session_maker), data_root=tmp_path / "data"
    )
    service.deletion_poll_interval_seconds = 0.02
    service.deletion_stop_timeout_seconds = 1.0
    app = create_app(
        db_path=db_file, admin_password_file=admin_pwd_file, service=service
    )

    async def _seed() -> dict:
        repo = ProfileRepository(session_maker)
        stopped = await repo.create_profile(ProfileConfig(name="env-stopped"))
        running = await repo.create_profile(ProfileConfig(name="env-running"))
        await repo.set_desired_state(running.id, "running")
        await repo.bind_runtime_instance(running.id, "inst-run")
        await repo.report_observed_state(running.id, "inst-run", "running")
        return {"stopped": stopped.id, "running": running.id}

    seeded = asyncio.run(_seed())
    with TestClient(app, base_url=ORIGIN) as client:
        login = client.post(
            "/api/v1/auth/login", json={"password": admin_pwd}
        )
        assert login.status_code == 200
        headers = {
            "X-CSRF-Token": login.json()["csrf_token"],
            "Origin": ORIGIN,
        }
        yield {
            "client": client,
            "headers": headers,
            "db_file": db_file,
            "session_maker": session_maker,
            **seeded,
        }
    asyncio.run(engine.dispose())


def _wait_batch(client, headers, batch_id: str, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(
            f"/api/v1/profile-deletions/batches/{batch_id}", headers=headers
        )
        assert resp.status_code == 200
        operations = resp.json()["operations"]
        if all(op["stage"] in ("done", "failed") for op in operations):
            return operations
        time.sleep(0.05)
    raise AssertionError(f"batch {batch_id} did not settle: {operations}")


def test_batch_deletion_of_stopped_profile(api_env):
    client, headers = api_env["client"], api_env["headers"]
    resp = client.post(
        "/api/v1/profile-deletions",
        json={"profile_ids": [api_env["stopped"]]},
        headers=headers,
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["operations"][0]["profile_id"] == api_env["stopped"]
    assert body["operations"][0]["profile_name"] == "env-stopped"

    operations = _wait_batch(client, headers, body["batch_id"])
    assert operations[0]["stage"] == "done"
    assert operations[0]["detail"]["steps"]["database"] == "ok"

    resp = client.get(
        f"/api/v1/profiles/{api_env['stopped']}", headers=headers
    )
    assert resp.status_code == 404


def test_batch_deletion_running_profile_times_out_and_retries(api_env):
    client, headers = api_env["client"], api_env["headers"]
    resp = client.post(
        "/api/v1/profile-deletions",
        json={"profile_ids": [api_env["running"]]},
        headers=headers,
    )
    assert resp.status_code == 202
    batch_id = resp.json()["batch_id"]
    operations = _wait_batch(client, headers, batch_id)
    assert operations[0]["stage"] == "failed"
    assert operations[0]["failed_stage"] == "stopping"
    # The profile survives a failed stop.
    resp = client.get(
        f"/api/v1/profiles/{api_env['running']}", headers=headers
    )
    assert resp.status_code == 200

    # Simulate the supervisor converging the stop, then retry.
    async def _converge() -> None:
        repo = ProfileRepository(api_env["session_maker"])
        await repo.report_observed_state(
            api_env["running"], "inst-run", "stopped"
        )

    asyncio.run(_converge())
    op_id = operations[0]["id"]
    resp = client.post(
        f"/api/v1/profile-deletions/{op_id}/retry", headers=headers
    )
    assert resp.status_code == 200
    operations = _wait_batch(client, headers, batch_id)
    assert operations[0]["stage"] == "done"
    resp = client.get(
        f"/api/v1/profiles/{api_env['running']}", headers=headers
    )
    assert resp.status_code == 404


def test_reconfirm_after_failure_surfaces_in_new_batch(api_env):
    """Review f001 regression: after a deletion fails and the dialog
    is closed, confirming the same target again must return a batch
    whose query contains the intent (200, not an empty 404) and the
    re-confirmed intent must converge instead of stranding."""
    client, headers = api_env["client"], api_env["headers"]
    first = client.post(
        "/api/v1/profile-deletions",
        json={"profile_ids": [api_env["running"]]},
        headers=headers,
    ).json()
    operations = _wait_batch(client, headers, first["batch_id"])
    assert operations[0]["stage"] == "failed"
    assert operations[0]["failed_stage"] == "stopping"
    op_id = operations[0]["id"]

    async def _converge() -> None:
        repo = ProfileRepository(api_env["session_maker"])
        await repo.report_observed_state(
            api_env["running"], "inst-run", "stopped"
        )

    asyncio.run(_converge())
    second = client.post(
        "/api/v1/profile-deletions",
        json={"profile_ids": [api_env["running"]]},
        headers=headers,
    ).json()
    assert second["batch_id"] != first["batch_id"]
    assert second["operations"][0]["id"] == op_id
    operations = _wait_batch(client, headers, second["batch_id"])
    assert [op["id"] for op in operations] == [op_id]
    assert operations[0]["stage"] == "done"
    resp = client.get(
        f"/api/v1/profiles/{api_env['running']}", headers=headers
    )
    assert resp.status_code == 404


def test_repeat_batch_post_joins_existing_intent(api_env):
    client, headers = api_env["client"], api_env["headers"]
    first = client.post(
        "/api/v1/profile-deletions",
        json={"profile_ids": [api_env["running"]]},
        headers=headers,
    ).json()
    second = client.post(
        "/api/v1/profile-deletions",
        json={"profile_ids": [api_env["running"]]},
        headers=headers,
    ).json()
    assert second["operations"][0]["id"] == first["operations"][0]["id"]


def test_delete_endpoint_drives_same_lifecycle(api_env):
    client, headers = api_env["client"], api_env["headers"]
    resp = client.delete(
        f"/api/v1/profiles/{api_env['stopped']}", headers=headers
    )
    assert resp.status_code == 204
    resp = client.get(
        f"/api/v1/profiles/{api_env['stopped']}", headers=headers
    )
    assert resp.status_code == 404


def test_delete_endpoint_running_profile_reports_stage(api_env):
    client, headers = api_env["client"], api_env["headers"]
    resp = client.delete(
        f"/api/v1/profiles/{api_env['running']}", headers=headers
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "profile_deletion_failed"
    assert body["details"]["stage"] == "stopping"
    # Data kept.
    resp = client.get(
        f"/api/v1/profiles/{api_env['running']}", headers=headers
    )
    assert resp.status_code == 200


def test_unknown_batch_and_operation_are_404(api_env):
    client, headers = api_env["client"], api_env["headers"]
    resp = client.get(
        "/api/v1/profile-deletions/batches/nope", headers=headers
    )
    assert resp.status_code == 404
    resp = client.get("/api/v1/profile-deletions/nope", headers=headers)
    assert resp.status_code == 404
