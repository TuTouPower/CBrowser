"""t094 AC-007: environment batch actions are durable server-side jobs.

The client submits one frozen target set + action and gets an immediate 202
receipt; progress is read from the job read model and pushed over SSE. No
client-side serial loop remains.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api_auth import create_auth_context
from cbrowser.api.app import create_app


@pytest.fixture
def app_client(tmp_path: Path):
    ctx = create_auth_context(tmp_path)
    app = create_app(
        db_path=tmp_path / "t094.db",
        admin_password_file=ctx.admin_password_file,
        artifacts_root=tmp_path / "artifacts",
    )
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        login = client.post(
            "/api/v1/auth/login", json={"password": ctx.admin_password}
        )
        assert login.status_code == 200
        headers = {
            "X-CSRF-Token": login.json()["csrf_token"],
            "Origin": ctx.allowed_origin,
        }
        yield client, headers


def _create_profile(client, headers, name):
    resp = client.post(
        "/api/v1/profiles",
        json={"name": name},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _wait_for_job(client, headers, job_id, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(
            f"/api/v1/profile-batch-jobs/{job_id}", headers=headers
        ).json()
        if job["state"] == "done":
            return job
        time.sleep(0.05)
    raise AssertionError(f"batch job {job_id} never completed")


def test_profile_batch_job_freezes_scope_and_converges(app_client):
    client, headers = app_client
    ids = [_create_profile(client, headers, f"env-{i}") for i in range(3)]
    resp = client.post(
        "/api/v1/profile-batch-jobs",
        json={"action": "stop", "profile_ids": ids},
        headers=headers,
    )
    assert resp.status_code == 202, resp.text
    receipt = resp.json()
    assert receipt["state"] == "running"
    assert receipt["total"] == 3
    job = _wait_for_job(client, headers, receipt["job_id"])
    assert {m["proxy_id"] for m in job["members"]} == set(ids)
    assert job["completed"] + job["failed"] == job["total"]


def test_profile_batch_job_partial_failure_is_per_member(app_client):
    client, headers = app_client
    real = _create_profile(client, headers, "real-env")
    resp = client.post(
        "/api/v1/profile-batch-jobs",
        json={"action": "start", "profile_ids": [real, "missing-env"]},
        headers=headers,
    )
    assert resp.status_code == 202
    job = _wait_for_job(client, headers, resp.json()["job_id"])
    assert job["total"] == 2
    states = {m["proxy_id"]: m["state"] for m in job["members"]}
    assert states[real] == "ok"
    assert states["missing-env"] == "failed"


def test_profile_batch_job_rejects_invalid_action_and_empty_scope(app_client):
    client, headers = app_client
    bad = client.post(
        "/api/v1/profile-batch-jobs",
        json={"action": "delete", "profile_ids": ["x"]},
        headers=headers,
    )
    assert bad.status_code == 422
    empty = client.post(
        "/api/v1/profile-batch-jobs",
        json={"action": "stop", "profile_ids": []},
        headers=headers,
    )
    assert empty.status_code == 422
