"""t056 A23 / AC-007: group/proxy create/update/delete implement the same
Idempotency-Key semantics as Profile.

Same key + same params -> the first result, no duplicate record.
Same key + different params -> 409 IdempotencyConflictError.
Delete replay -> the recorded success (204), not 404.
"""

from __future__ import annotations

import pytest
from cbrowser.adapters.database.repository import (
    IdempotencyConflictError,
    ProfileRepository,
)
from cbrowser.domain.models import (
    GroupCreateRequest,
    GroupUpdateRequest,
    ProxyCreateRequest,
    ProxyUpdateRequest,
)
from cbrowser.services.profile_service import ProfileService
from fastapi.testclient import TestClient

from api_auth import create_auth_context
from cbrowser.api.app import create_app


# --------------------------------------------------------------- repo level


def _group_payload(name: str = "Work") -> dict:
    return {"name": name, "color": "blue", "sort_order": 0}


def _proxy_payload(name: str = "px") -> dict:
    return {
        "name": name,
        "scheme": "http",
        "host": "proxy.example.com",
        "port": 8080,
        "username": "user",
        "password": "secret",
    }


@pytest.mark.asyncio
async def test_group_create_replay_returns_first_without_duplicate(db_context) -> None:
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    first = await repo.create_group(
        **_group_payload(), operation_id="op-group-create-1"
    )
    replay = await repo.create_group(
        **_group_payload(), operation_id="op-group-create-1"
    )
    assert replay.id == first.id
    assert len(await repo.list_groups()) == 1


@pytest.mark.asyncio
async def test_group_create_same_key_different_payload_conflicts(db_context) -> None:
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    await repo.create_group(**_group_payload("Work"), operation_id="op-gc-2")
    with pytest.raises(IdempotencyConflictError):
        await repo.create_group(
            **_group_payload("Other"), operation_id="op-gc-2"
        )
    assert len(await repo.list_groups()) == 1


@pytest.mark.asyncio
async def test_group_update_replay_returns_current_without_reapplying(
    db_context,
) -> None:
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    group = await repo.create_group(**_group_payload())
    first = await repo.update_group(
        group.id, {"name": "Renamed"}, operation_id="op-gu-1"
    )
    assert first is not None and first.name == "Renamed"
    replay = await repo.update_group(
        group.id, {"name": "Renamed"}, operation_id="op-gu-1"
    )
    assert replay is not None and replay.id == group.id and replay.name == "Renamed"
    assert len(await repo.list_groups()) == 1


@pytest.mark.asyncio
async def test_group_update_same_key_different_payload_conflicts(db_context) -> None:
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    group = await repo.create_group(**_group_payload())
    await repo.update_group(group.id, {"name": "A"}, operation_id="op-gu-2")
    with pytest.raises(IdempotencyConflictError):
        await repo.update_group(group.id, {"name": "B"}, operation_id="op-gu-2")


@pytest.mark.asyncio
async def test_group_delete_replay_returns_success_not_404(db_context) -> None:
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    group = await repo.create_group(**_group_payload())
    assert await repo.delete_group(group.id, operation_id="op-gd-1") is True
    assert await repo.delete_group(group.id, operation_id="op-gd-1") is True
    assert await repo.delete_group(group.id) is False


@pytest.mark.asyncio
async def test_group_replay_after_delete_with_name_taken_is_409_not_500(
    db_context,
) -> None:
    """A23 / AC-007 (t056_code_f002): replay a recorded group create
    after the group was deleted and another group took the name. The
    rebuild must fail with a clean ValueError ("group name already
    exists", mapped to 409 group_name_in_use by the router), not
    recurse until RecursionError and surface as 500."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    first = await repo.create_group(
        **_group_payload("Taken"), operation_id="op-gc-rebuild-1"
    )
    assert await repo.delete_group(first.id) is True
    # Another group takes the freed name.
    await repo.create_group(**_group_payload("Taken"))
    with pytest.raises(ValueError, match="group name already exists"):
        await repo.create_group(
            **_group_payload("Taken"), operation_id="op-gc-rebuild-1"
        )
    assert len(await repo.list_groups()) == 1


@pytest.mark.asyncio
async def test_proxy_create_replay_returns_first_without_duplicate(db_context) -> None:
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    first = await repo.create_proxy(
        _proxy_payload(), operation_id="op-proxy-create-1"
    )
    replay = await repo.create_proxy(
        _proxy_payload(), operation_id="op-proxy-create-1"
    )
    assert replay.id == first.id
    assert len(await repo.list_proxies()) == 1


@pytest.mark.asyncio
async def test_proxy_create_same_key_different_payload_conflicts(db_context) -> None:
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    await repo.create_proxy(_proxy_payload("px"), operation_id="op-pc-2")
    with pytest.raises(IdempotencyConflictError):
        await repo.create_proxy(_proxy_payload("other"), operation_id="op-pc-2")


@pytest.mark.asyncio
async def test_proxy_update_replay_returns_current_without_new_version(
    db_context,
) -> None:
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    proxy = await repo.create_proxy(_proxy_payload())
    first, versioned, runtime_only = await repo.update_proxy(
        proxy.id, {"name": "renamed"}, False, operation_id="op-pu-1"
    )
    assert first is not None and first.name == "renamed"
    replay, versioned2, runtime_only2 = await repo.update_proxy(
        proxy.id, {"name": "renamed"}, False, operation_id="op-pu-1"
    )
    assert replay is not None and replay.id == proxy.id
    assert replay.name == "renamed"
    assert versioned2 == versioned and runtime_only2 == runtime_only
    assert len(await repo.list_proxies()) == 1


@pytest.mark.asyncio
async def test_proxy_update_same_key_different_payload_conflicts(db_context) -> None:
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    proxy = await repo.create_proxy(_proxy_payload())
    await repo.update_proxy(proxy.id, {"name": "A"}, False, operation_id="op-pu-2")
    with pytest.raises(IdempotencyConflictError):
        await repo.update_proxy(proxy.id, {"name": "B"}, False, operation_id="op-pu-2")


@pytest.mark.asyncio
async def test_proxy_delete_replay_returns_success_not_404(db_context) -> None:
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    proxy = await repo.create_proxy(_proxy_payload())
    assert await repo.delete_proxy(proxy.id, operation_id="op-pd-1") == (True, 0)
    assert await repo.delete_proxy(proxy.id, operation_id="op-pd-1") == (True, 0)
    assert await repo.delete_proxy(proxy.id) == (False, 0)


@pytest.mark.asyncio
async def test_proxy_replay_after_delete_with_name_taken_is_409_not_500(
    db_context,
) -> None:
    """A23 / AC-007 (t056_code_f002): replay a recorded proxy create
    after the proxy was deleted and another proxy took the name. The
    rebuild must fail with a clean ValueError ("proxy name already
    exists", mapped to 409 proxy_name_in_use by the router), not
    recurse until RecursionError and surface as 500."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    first = await repo.create_proxy(
        _proxy_payload("taken"), operation_id="op-pc-rebuild-1"
    )
    assert await repo.delete_proxy(first.id) == (True, 0)
    # Another proxy takes the freed name.
    await repo.create_proxy(_proxy_payload("taken"))
    with pytest.raises(ValueError, match="proxy name already exists"):
        await repo.create_proxy(
            _proxy_payload("taken"), operation_id="op-pc-rebuild-1"
        )
    assert len(await repo.list_proxies()) == 1


# ------------------------------------------------------------ service level


@pytest.mark.asyncio
async def test_service_proxy_create_replay_skips_probe_side_effects(tmp_path) -> None:
    """A replayed proxy create returns the first proxy and records no
    second pending observation (the probe is scheduled once)."""
    from cbrowser.adapters.database.migrations import run_database_migrations
    from cbrowser.adapters.database.session import create_engine_and_maker

    db_path = tmp_path / "idem.db"
    run_database_migrations(db_path)
    engine, maker = create_engine_and_maker(db_path)
    service = ProfileService(ProfileRepository(maker))
    # Neutralize the fire-and-forget auto-probe: it re-records a pending
    # observation of its own, which would mask the replay assertion.
    service._schedule_probe = lambda proxy_id: None
    try:
        req = ProxyCreateRequest(name="px", proxy_url="http://user:secret@proxy.example.com:8080")
        first = await service.create_proxy(req, operation_id="op-spc-1")
        replay = await service.create_proxy(req, operation_id="op-spc-1")
        assert replay.id == first.id
        assert len(await service.list_proxies()) == 1
        # One pending observation, from the first call only: a replay
        # must not insert a second pending row.
        from sqlalchemy import text as _text

        async with maker() as session:
            pending = (
                await session.execute(
                    _text(
                        "SELECT COUNT(*) FROM proxy_egress_observations "
                        "WHERE proxy_id = :pid AND status = 'pending'"
                    ),
                    {"pid": first.id},
                )
            ).scalar_one()
        assert pending == 1
    finally:
        await engine.dispose()


# ------------------------------------------------------------- router level


@pytest.mark.asyncio
async def test_service_proxy_update_replay_skips_probe_and_version(tmp_path) -> None:
    """A replayed proxy update returns the current proxy with recomputed
    impact lists, creates no new config version, and schedules no second
    probe."""
    from cbrowser.adapters.database.migrations import run_database_migrations
    from cbrowser.adapters.database.session import create_engine_and_maker
    from sqlalchemy import text as _text

    db_path = tmp_path / "idem_upd.db"
    run_database_migrations(db_path)
    engine, maker = create_engine_and_maker(db_path)
    service = ProfileService(ProfileRepository(maker))
    service._schedule_probe = lambda proxy_id: None
    try:
        proxy = await service.create_proxy(
            ProxyCreateRequest(name="px", proxy_url="http://user:secret@proxy.example.com:8080"),
            operation_id="op-spu-create",
        )
        req = ProxyUpdateRequest(
            proxy_url="http://user:new-secret@proxy.example.com:8080"
        )
        first, versioned, runtime_only = await service.update_proxy(
            proxy.id, req, operation_id="op-spu-1"
        )
        assert first is not None and first.credential_revision == 2
        assert versioned == [] and runtime_only == []
        replay, versioned2, runtime_only2 = await service.update_proxy(
            proxy.id, req, operation_id="op-spu-1"
        )
        assert replay is not None and replay.id == proxy.id
        assert replay.credential_revision == 2
        assert versioned2 == [] and runtime_only2 == []
        async with maker() as session:
            pending = (
                await session.execute(
                    _text(
                        "SELECT COUNT(*) FROM proxy_egress_observations "
                        "WHERE proxy_id = :pid AND status = 'pending'"
                    ),
                    {"pid": proxy.id},
                )
            ).scalar_one()
        # One pending row from the create, one from the (single) update.
        assert pending == 2
    finally:
        await engine.dispose()


def _app(tmp_path):
    ctx = create_auth_context(tmp_path)
    app = create_app(
        db_path=tmp_path / "idem_router.db",
        admin_password_file=ctx.admin_password_file,
        artifacts_root=tmp_path / "artifacts",
    )
    return app, ctx


def _login(client: TestClient, ctx) -> dict[str, str]:
    login = client.post("/api/v1/auth/login", json={"password": ctx.admin_password})
    assert login.status_code == 200
    return {
        "X-CSRF-Token": login.json()["csrf_token"],
        "Origin": ctx.allowed_origin,
    }


def test_router_group_create_replay_and_conflict(tmp_path) -> None:
    app, ctx = _app(tmp_path)
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        headers = _login(client, ctx)
        key_headers = {**headers, "Idempotency-Key": "router-group-1"}
        first = client.post(
            "/api/v1/groups",
            json={"name": "Work", "color": "blue", "sort_order": 0},
            headers=key_headers,
        )
        assert first.status_code == 201
        replay = client.post(
            "/api/v1/groups",
            json={"name": "Work", "color": "blue", "sort_order": 0},
            headers=key_headers,
        )
        assert replay.status_code == 201
        assert replay.json()["id"] == first.json()["id"]
        conflict = client.post(
            "/api/v1/groups",
            json={"name": "Other", "color": "blue", "sort_order": 0},
            headers=key_headers,
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"] == "idempotency_conflict"
        assert len(client.get("/api/v1/groups", headers=headers).json()) == 1


def test_router_group_delete_replay_is_204_not_404(tmp_path) -> None:
    app, ctx = _app(tmp_path)
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        headers = _login(client, ctx)
        group = client.post(
            "/api/v1/groups",
            json={"name": "Work", "color": "blue", "sort_order": 0},
            headers=headers,
        ).json()
        key_headers = {**headers, "Idempotency-Key": "router-group-del-1"}
        first = client.delete(f"/api/v1/groups/{group['id']}", headers=key_headers)
        assert first.status_code == 204
        replay = client.delete(f"/api/v1/groups/{group['id']}", headers=key_headers)
        assert replay.status_code == 204
        plain = client.delete(f"/api/v1/groups/{group['id']}", headers=headers)
        assert plain.status_code == 404


def test_router_proxy_create_replay_and_conflict(tmp_path) -> None:
    app, ctx = _app(tmp_path)
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        headers = _login(client, ctx)
        key_headers = {**headers, "Idempotency-Key": "router-proxy-1"}
        payload = {
            "name": "px",
            "proxy_url": "http://user:secret@proxy.example.com:8080",
        }
        first = client.post("/api/v1/proxies", json=payload, headers=key_headers)
        assert first.status_code == 201
        replay = client.post("/api/v1/proxies", json=payload, headers=key_headers)
        assert replay.status_code == 201
        assert replay.json()["id"] == first.json()["id"]
        conflict = client.post(
            "/api/v1/proxies",
            json={**payload, "name": "other"},
            headers=key_headers,
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"] == "idempotency_conflict"
        assert len(client.get("/api/v1/proxies", headers=headers).json()) == 1
