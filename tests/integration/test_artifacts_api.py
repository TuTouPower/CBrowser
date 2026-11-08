"""HTTP integration for Artifact upload/list/download/delete and isolation."""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path

import pytest
from cbrowser.api.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def artifact_env(tmp_path: Path):
    db_file = tmp_path / "artifacts_api.db"
    admin_password = secrets.token_urlsafe(32)
    password_file = tmp_path / "admin.txt"
    password_file.write_text(admin_password, encoding="utf-8")
    password_file.chmod(0o600)
    origin = "https://127.0.0.1:56661"
    supervisor_token = secrets.token_urlsafe(32)
    supervisor_token_file = tmp_path / "supervisor.token"
    supervisor_token_file.write_text(supervisor_token, encoding="utf-8")
    supervisor_token_file.chmod(0o600)
    app = create_app(
        db_path=db_file,
        admin_password_file=password_file,
        supervisor_token_file=supervisor_token_file,
                artifacts_root=tmp_path / "artifacts",
        max_artifact_bytes=1024 * 1024,
    )
    with TestClient(app, base_url=origin) as client:
        store = app.state.artifact_service.store
        store.runtime_uid = os.getuid()
        store.runtime_gid = os.getgid()
        login = client.post("/api/v1/auth/login", json={"password": admin_password})
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Origin": origin}
        created = client.post(
            "/api/v1/profiles", json={"name": "Files"}, headers=headers
        )
        assert created.status_code == 201
        yield {
            "client": client,
            "headers": headers,
            "profile_id": created.json()["id"],
            "root": tmp_path / "artifacts",
            "supervisor_token": supervisor_token,
        }


def _upload(env, profile_id: str, name: str, payload: bytes, content_type="text/csv"):
    return env["client"].post(
        f"/api/v1/profiles/{profile_id}/artifacts",
        params={"filename": name},
        content=payload,
        headers={**env["headers"], "Content-Type": content_type},
    )


def test_upload_list_download_delete_round_trip(artifact_env) -> None:
    env = artifact_env
    pid = env["profile_id"]
    payload = b"store_id,orders\n1,2\n"
    uploaded = _upload(env, pid, "weekly report.csv", payload)
    assert uploaded.status_code == 201
    artifact = uploaded.json()
    assert artifact["name"] == "weekly report.csv"
    assert artifact["size"] == len(payload)
    assert artifact["kind"] == "upload"
    assert artifact["state"] == "ready"
    assert artifact["sha256"]
    assert artifact["container_path"] == (
        f"/exchange/uploads/{artifact['id']}/weekly report.csv"
    )

    listed = env["client"].get(f"/api/v1/profiles/{pid}/artifacts")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [artifact["id"]]

    downloaded = env["client"].get(f"/api/v1/profiles/{pid}/artifacts/{artifact['id']}")
    assert downloaded.status_code == 200
    assert downloaded.content == payload
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert downloaded.headers["cache-control"] == "no-store"
    assert downloaded.headers["content-type"] == "application/octet-stream"
    assert "attachment" in downloaded.headers["content-disposition"]

    deleted = env["client"].delete(
        f"/api/v1/profiles/{pid}/artifacts/{artifact['id']}",
        headers=env["headers"],
    )
    assert deleted.status_code == 204
    assert env["client"].get(f"/api/v1/profiles/{pid}/artifacts").json() == []
    assert not (env["root"] / pid / "uploads" / artifact["id"]).exists()


def test_upload_rejects_oversize_without_partial_files(artifact_env) -> None:
    # The previous combined test also asserted application/x-sh uploads
    # are rejected with 400; that MIME rejection policy was removed by
    # A54 (user decision D2=A), so only the oversize case remains here.
    env = artifact_env
    pid = env["profile_id"]
    env["client"].app.state.artifact_service.max_artifact_bytes = 8
    too_large = _upload(env, pid, "big.csv", b"x" * 9)
    assert too_large.status_code == 413
    assert env["client"].get(f"/api/v1/profiles/{pid}/artifacts").json() == []
    leftovers = list(Path(env["root"], pid).rglob("*"))
    assert [item for item in leftovers if item.is_file()] == []


def test_executable_upload_round_trip_uses_attachment_download(
    artifact_env,
) -> None:
    """AC-012 (A54): executable content uploads and downloads back with
    its declared type recorded, while the user-facing download stays an
    attachment with nosniff and an octet-stream media type."""
    env = artifact_env
    pid = env["profile_id"]
    payload = b"#!/bin/sh\necho owned\n"
    uploaded = _upload(env, pid, "bad.sh", payload, "application/x-sh")
    assert uploaded.status_code == 201
    artifact = uploaded.json()
    assert artifact["content_type"] == "application/x-sh"

    downloaded = env["client"].get(
        f"/api/v1/profiles/{pid}/artifacts/{artifact['id']}"
    )
    assert downloaded.status_code == 200
    assert downloaded.content == payload
    assert downloaded.headers["content-type"] == "application/octet-stream"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in downloaded.headers["content-disposition"]


def test_path_traversal_is_sanitised_inside_profile_storage(artifact_env) -> None:
    env = artifact_env
    pid = env["profile_id"]
    artifact = _upload(env, pid, "../../../../etc/passwd", b"nope").json()
    stored = env["root"] / pid / "uploads" / artifact["id"] / "passwd"
    assert stored.read_bytes() == b"nope"
    assert artifact["container_path"].endswith("/passwd")


def test_artifacts_are_not_reachable_from_another_profile(artifact_env) -> None:
    env = artifact_env
    owner = env["profile_id"]
    artifact = _upload(env, owner, "owner.csv", b"secret").json()
    other = (
        env["client"]
        .post("/api/v1/profiles", json={"name": "Other"}, headers=env["headers"])
        .json()["id"]
    )

    assert (
        env["client"]
        .get(f"/api/v1/profiles/{other}/artifacts/{artifact['id']}")
        .status_code
        == 404
    )
    assert (
        env["client"]
        .delete(
            f"/api/v1/profiles/{other}/artifacts/{artifact['id']}",
            headers=env["headers"],
        )
        .status_code
        == 404
    )


def test_internal_supervisor_ingest_is_authenticated_and_deduplicated(
    artifact_env,
) -> None:
    env = artifact_env
    pid = env["profile_id"]
    # A40: download reports are only accepted from instances trusted for
    # the profile, so bind instance "i1" before reporting as it.
    bound = env["client"].post(
        "/api/v1/internal/supervisor/runtimes/bind",
        params={"profile_id": pid},
        headers={"Authorization": f"Bearer {env['supervisor_token']}"},
        json={"runtime_instance_id": "i1", "config_version": 1},
    )
    assert bound.status_code == 200
    payload = b"downloaded-by-browser"
    digest = hashlib.sha256(payload).hexdigest()
    downloads = env["root"] / pid / "downloads"
    downloads.mkdir(parents=True)
    source = downloads / "guid"
    source.write_bytes(payload)
    body = {
        "event_id": "dl_completed_1",
        "profile_id": pid,
        "runtime_instance_id": "i1",
        "path": "/exchange/downloads/guid",
        "name": "downloaded.csv",
        "size": len(payload),
        "sha256": digest,
        "content_type": "text/csv",
    }
    endpoint = "/api/v1/internal/supervisor/artifacts/downloads"

    unauthorized = env["client"].post(
        endpoint, json=body, headers={"Authorization": "Bearer wrong"}
    )
    assert unauthorized.status_code == 401

    headers = {"Authorization": f"Bearer {env['supervisor_token']}"}
    created = env["client"].post(endpoint, json=body, headers=headers)
    assert created.status_code == 200
    assert created.json()["outcome"] == "created"
    assert not source.exists()

    artifacts = env["client"].get(f"/api/v1/profiles/{pid}/artifacts").json()
    assert len(artifacts) == 1
    assert artifacts[0]["kind"] == "download"
    assert artifacts[0]["sha256"] == digest

    canonical = dict(
        body, event_id="dl_completed_dup", path=artifacts[0]["container_path"]
    )
    duplicate = env["client"].post(endpoint, json=canonical, headers=headers)
    assert duplicate.status_code == 200
    assert duplicate.json()["outcome"] == "duplicate"

    traversal = dict(
        body, event_id="dl_completed_2", path="/exchange/downloads/../../evil"
    )
    rejected = env["client"].post(endpoint, json=traversal, headers=headers)
    assert rejected.status_code == 200
    assert rejected.json()["outcome"] == "rejected"

    # A report from an instance that was never bound or recorded for the
    # profile is rejected as forged, without registering an artifact.
    forged = dict(body, event_id="dl_forged", runtime_instance_id="ghost")
    forged_response = env["client"].post(endpoint, json=forged, headers=headers)
    assert forged_response.status_code == 200
    assert forged_response.json()["outcome"] == "rejected"
    assert (
        len(env["client"].get(f"/api/v1/profiles/{pid}/artifacts").json()) == 1
    )


def test_upload_requires_authentication_and_csrf(artifact_env) -> None:
    env = artifact_env
    pid = env["profile_id"]
    no_csrf = env["client"].post(
        f"/api/v1/profiles/{pid}/artifacts",
        params={"filename": "x.csv"},
        content=b"x",
        headers={"Origin": env["headers"]["Origin"]},
    )
    assert no_csrf.status_code == 403

    env["client"].cookies.clear()
    anonymous = env["client"].post(
        f"/api/v1/profiles/{pid}/artifacts",
        params={"filename": "x.csv"},
        content=b"x",
    )
    assert anonymous.status_code == 401


def test_artifact_read_and_delete_require_authentication(artifact_env) -> None:
    env = artifact_env
    pid = env["profile_id"]
    artifact = _upload(env, pid, "secret.csv", b"secret").json()

    missing_csrf = env["client"].delete(
        f"/api/v1/profiles/{pid}/artifacts/{artifact['id']}",
        headers={"Origin": env["headers"]["Origin"]},
    )
    assert missing_csrf.status_code == 403

    env["client"].cookies.clear()
    assert env["client"].get(f"/api/v1/profiles/{pid}/artifacts").status_code == 401
    assert (
        env["client"]
        .get(f"/api/v1/profiles/{pid}/artifacts/{artifact['id']}")
        .status_code
        == 401
    )
    assert (
        env["client"]
        .delete(f"/api/v1/profiles/{pid}/artifacts/{artifact['id']}")
        .status_code
        == 401
    )
