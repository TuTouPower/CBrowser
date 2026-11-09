from __future__ import annotations

import secrets
from pathlib import Path
from types import SimpleNamespace

import pytest
from cbrowser.api.app import create_app
from cbrowser.api.v1.deps import get_profile_service
from cbrowser.api.v1.router import _apply_preview_policy
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


async def test_apply_preview_policy_uses_fresh_db_state_under_lock(
    tmp_path: Path,
) -> None:
    """Concurrent PATCH: the policy file write holds the per-profile lock
    and re-reads the authoritative DB policy, so a stale `enabled` passed
    by the caller cannot overwrite a newer `disabled` file."""
    from cbrowser.services.profile_service import (
        ProfileLockRegistry,
        ProfileNotFoundError,
    )

    directory = tmp_path / "profiles" / "p-lock" / "preview"

    class _StubService:
        def __init__(self) -> None:
            self._locks = ProfileLockRegistry()
            self.cleared: list[str] = []

        async def get_preview_policy(
            self, _profile_id: str
        ) -> tuple[bool, int] | None:
            return (False, 7)

        async def get_runtime(self, profile_id: str):
            raise ProfileNotFoundError(profile_id)

        def get_preview_dir(self, _profile_id: str) -> Path:
            return directory

        async def clear_preview_capture(self, profile_id: str) -> None:
            self.cleared.append(profile_id)

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(coordinator=None))
    )
    service = _StubService()
    await _apply_preview_policy("p-lock", True, 6, request, service)
    assert read_policy(directory) == PreviewPolicy(
        enabled=False, epoch=7, runtime_instance_id=None
    )
    assert service.cleared == ["p-lock"]


async def test_apply_releases_lock_before_rpc_and_skips_on_concurrent_delete(
    tmp_path: Path,
) -> None:
    """The 10s supervisor RPC must not hold the per-profile lock, and a
    concurrently deleted profile (fresh is None) must not recreate files."""
    from cbrowser.services.profile_service import (
        ProfileLockRegistry,
        ProfileNotFoundError,
    )

    directory = tmp_path / "profiles" / "p-split" / "preview"

    class _StubService:
        def __init__(self) -> None:
            self._locks = ProfileLockRegistry()
            self.cleared: list[str] = []

        async def get_preview_policy(
            self, _profile_id: str
        ) -> tuple[bool, int] | None:
            return (True, 4)

        async def get_runtime(self, profile_id: str):
            return SimpleNamespace(runtime_instance_id="inst-1")

        def get_preview_dir(self, _profile_id: str) -> Path:
            return directory

        async def clear_preview_capture(self, profile_id: str) -> None:
            self.cleared.append(profile_id)

    class _Coordinator:
        def __init__(self, service: _StubService) -> None:
            self.service = service
            self.calls: list = []
            self.lock_held_during_rpc: bool | None = None

        async def request_preview_policy(
            self, profile_id: str, enabled: bool, epoch: int, instance
        ) -> None:
            lock = self.service._locks._locks.get(profile_id)
            self.lock_held_during_rpc = (
                lock.locked() if lock is not None else False
            )
            self.calls.append((profile_id, enabled, epoch, instance))

        def has_pending_preview_policy(self, _profile_id: str) -> bool:
            return False

    service = _StubService()
    coordinator = _Coordinator(service)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(coordinator=coordinator))
    )
    await _apply_preview_policy("p-split", True, 4, request, service)
    assert coordinator.calls == [("p-split", True, 4, "inst-1")]
    assert coordinator.lock_held_during_rpc is False
    assert read_policy(directory) == PreviewPolicy(
        enabled=True, epoch=4, runtime_instance_id="inst-1"
    )

    class _DeletedService(_StubService):
        async def get_preview_policy(
            self, _profile_id: str
        ) -> tuple[bool, int] | None:
            return None

    deleted = _DeletedService()
    deleted_coordinator = _Coordinator(deleted)
    deleted_request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(coordinator=deleted_coordinator))
    )
    deleted_dir = tmp_path / "profiles" / "p-gone" / "preview"
    deleted.get_preview_dir = lambda _pid: deleted_dir  # type: ignore[method-assign]
    await _apply_preview_policy("p-gone", True, 9, deleted_request, deleted)
    assert not (deleted_dir / "policy.json").exists()
    assert deleted_coordinator.calls == []


def test_same_value_retry_converges_after_local_write_failure(
    monkeypatch, ctx
) -> None:
    """Local file-write failure must not gate the next same-value PATCH:
    the epoch-unchanged retry still re-applies and converges."""
    import cbrowser.api.v1.router as router_mod

    _login(ctx)
    profile_id = _create(ctx)
    real_write = router_mod.write_policy
    calls = {"n": 0}

    def _flaky(directory, policy):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("disk full")
        return real_write(directory, policy)

    monkeypatch.setattr(router_mod, "write_policy", _flaky)
    first = ctx.client.patch(
        f"/api/v1/profiles/{profile_id}", json={"capture_preview": False}
    )
    assert first.status_code == 500
    row = ctx.service.get_preview_dir(profile_id)
    # DB already committed the disable; the file layer is still stale.
    import asyncio

    after_first = asyncio.run(ctx.service.get_preview_policy(profile_id))
    assert after_first == (False, 1)

    second = ctx.client.patch(
        f"/api/v1/profiles/{profile_id}", json={"capture_preview": False}
    )
    assert second.status_code == 200, second.text
    assert read_policy(row) == PreviewPolicy(
        enabled=False, epoch=1, runtime_instance_id=None
    )


def test_bind_writes_preview_policy_inside_profile_lock(ctx) -> None:
    """bind_runtime_instance must write the policy file while holding the
    same per-profile lock as PATCH, using fresh DB enabled/epoch."""
    import asyncio

    _login(ctx)
    profile_id = _create(ctx)
    revoke = ctx.client.patch(
        f"/api/v1/profiles/{profile_id}", json={"capture_preview": False}
    )
    assert revoke.status_code == 200, revoke.text
    assert asyncio.run(ctx.service.get_preview_policy(profile_id)) == (False, 1)

    held_during_write = {}

    import cbrowser.services.profile_service as service_mod

    real_write = service_mod.write_policy

    def _checked(directory, policy):
        lock = ctx.service._locks._locks.get(profile_id)
        held_during_write["held"] = lock.locked() if lock is not None else False
        held_during_write["policy"] = policy
        return real_write(directory, policy)

    import unittest.mock as mock

    with mock.patch.object(service_mod, "write_policy", side_effect=_checked):
        bound = asyncio.run(
            ctx.service.bind_runtime_instance(profile_id, "inst-bind-1")
        )
    assert bound.runtime_instance_id == "inst-bind-1"
    assert held_during_write.get("held") is True
    assert held_during_write["policy"].enabled is False
    assert held_during_write["policy"].epoch == 1
    assert held_during_write["policy"].runtime_instance_id == "inst-bind-1"
    directory = ctx.service.get_preview_dir(profile_id)
    assert read_policy(directory) == PreviewPolicy(
        enabled=False, epoch=1, runtime_instance_id="inst-bind-1"
    )
