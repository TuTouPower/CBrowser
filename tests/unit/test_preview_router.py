from __future__ import annotations

import secrets
from pathlib import Path
from types import SimpleNamespace

import pytest
from cbrowser.api.app import create_app
from cbrowser.api.v1.deps import get_profile_service
from cbrowser.preview import (
    PreviewMeta,
    PreviewPolicy,
    commit_preview,
    read_policy,
    write_policy,
)
from fastapi.testclient import TestClient

ORIGIN = "https://127.0.0.1:56661"
CAPTURED_AT = "2026-11-07T12:00:00+00:00"
JPEG_MARKER = b"SECRET_IMAGE_MARKER_XYZ"
JPEG_BYTES = b"\xff\xd8\xff\xe0" + JPEG_MARKER + b"\xff\xd9"


@pytest.fixture
def ctx(tmp_path: Path):
    admin_pass = secrets.token_urlsafe(32)
    admin_file = tmp_path / "admin.pwd"
    admin_file.write_text(admin_pass, encoding="utf-8")
    admin_file.chmod(0o600)
    app = create_app(
        db_path=tmp_path / "preview.db",
        admin_password_file=admin_file,
    )
    with TestClient(app, base_url=ORIGIN) as client:
        service = app.dependency_overrides[get_profile_service]()
        yield SimpleNamespace(
            client=client,
            app=app,
            service=service,
            admin_pass=admin_pass,
            tmp_path=tmp_path,
        )


def _login(ctx) -> None:
    response = ctx.client.post(
        "/api/v1/auth/login", json={"password": ctx.admin_pass}
    )
    assert response.status_code == 200, response.text
    ctx.client.headers.update(
        {
            "X-CSRF-Token": response.json()["csrf_token"],
            "Origin": ORIGIN,
        }
    )


def _create(ctx) -> str:
    response = ctx.client.post("/api/v1/profiles", json={"name": "preview_profile"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _write_valid_preview(
    service,
    profile_id: str,
    *,
    captured_at: str = CAPTURED_AT,
    instance: str = "inst-1",
) -> Path:
    directory = service.get_preview_dir(profile_id)
    policy = PreviewPolicy(enabled=True, epoch=0, runtime_instance_id=instance)
    write_policy(directory, policy)
    meta = PreviewMeta(
        captured_at=captured_at,
        runtime_instance_id=instance,
        policy_epoch=0,
    )
    assert commit_preview(directory, JPEG_BYTES, meta, policy) is True
    return directory


def test_preview_requires_authentication(ctx) -> None:
    response = ctx.client.get("/api/v1/profiles/any/preview")
    assert response.status_code in (401, 403)


def test_no_preview_returns_404(ctx) -> None:
    _login(ctx)
    profile_id = _create(ctx)
    response = ctx.client.get(f"/api/v1/profiles/{profile_id}/preview")
    assert response.status_code == 404
    assert str(ctx.tmp_path) not in response.text


def test_revoked_policy_returns_404_and_clears_frame(ctx) -> None:
    _login(ctx)
    profile_id = _create(ctx)
    directory = _write_valid_preview(ctx.service, profile_id)
    assert ctx.client.get(f"/api/v1/profiles/{profile_id}/preview").status_code == 200

    revoke = ctx.client.patch(
        f"/api/v1/profiles/{profile_id}", json={"capture_preview": False}
    )
    assert revoke.status_code == 200, revoke.text

    response = ctx.client.get(f"/api/v1/profiles/{profile_id}/preview")
    assert response.status_code == 404
    assert not (directory / "latest.jpg").exists()


def test_valid_preview_returns_jpeg_headers_and_304(ctx) -> None:
    _login(ctx)
    profile_id = _create(ctx)
    _write_valid_preview(ctx.service, profile_id)

    response = ctx.client.get(f"/api/v1/profiles/{profile_id}/preview")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    etag = response.headers["etag"]
    assert CAPTURED_AT in etag
    assert response.content == JPEG_BYTES

    not_modified = ctx.client.get(
        f"/api/v1/profiles/{profile_id}/preview",
        headers={"If-None-Match": etag},
    )
    assert not_modified.status_code == 304


def test_error_body_never_leaks_path_or_image_content(ctx) -> None:
    _login(ctx)
    profile_id = _create(ctx)
    directory = _write_valid_preview(ctx.service, profile_id)
    write_policy(
        directory,
        PreviewPolicy(enabled=True, epoch=99, runtime_instance_id="inst-1"),
    )
    response = ctx.client.get(f"/api/v1/profiles/{profile_id}/preview")
    assert response.status_code == 404
    body = response.text
    assert str(ctx.tmp_path) not in body
    assert "latest.jpg" not in body
    assert JPEG_MARKER.decode() not in body


def test_preview_policy_local_failure_fails_the_patch(monkeypatch, ctx) -> None:
    _login(ctx)
    profile_id = _create(ctx)
    monkeypatch.setattr(ctx.service, "get_preview_dir", lambda _pid: None)
    response = ctx.client.patch(
        f"/api/v1/profiles/{profile_id}", json={"capture_preview": False}
    )
    assert response.status_code == 500


def test_db_disabled_is_authoritative_over_enabled_file(ctx) -> None:
    _login(ctx)
    profile_id = _create(ctx)
    _write_valid_preview(ctx.service, profile_id)
    assert ctx.client.get(f"/api/v1/profiles/{profile_id}/preview").status_code == 200

    revoke = ctx.client.patch(
        f"/api/v1/profiles/{profile_id}", json={"capture_preview": False}
    )
    assert revoke.status_code == 200, revoke.text

    # DB now disables previews but the file layer still holds an enabled
    # policy with a fresh frame (stale supervisor sync): the read end must
    # still answer 404 because the DB row is authoritative.
    directory = ctx.service.get_preview_dir(profile_id)
    db_epoch = read_policy(directory).epoch
    enabled = PreviewPolicy(
        enabled=True, epoch=db_epoch, runtime_instance_id="inst-1"
    )
    write_policy(directory, enabled)
    assert (
        commit_preview(
            directory,
            JPEG_BYTES,
            PreviewMeta(
                captured_at=CAPTURED_AT,
                runtime_instance_id="inst-1",
                policy_epoch=db_epoch,
            ),
            enabled,
        )
        is True
    )

    response = ctx.client.get(f"/api/v1/profiles/{profile_id}/preview")
    assert response.status_code == 404
