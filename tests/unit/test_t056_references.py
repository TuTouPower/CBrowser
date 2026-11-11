"""t056 A28 / AC-010: referencing a nonexistent group/proxy returns a
field-level 422; reorder requires the full set, otherwise 422."""

from __future__ import annotations

import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.domain.models import ProfileConfig
from cbrowser.services.profile_service import (
    ProfileService,
    ReferenceValidationError,
)
from types import SimpleNamespace as _NS
from fastapi.testclient import TestClient

from api_auth import create_auth_context
from cbrowser.api.app import create_app


async def _make_service(tmp_path):
    db_path = tmp_path / "a28.db"
    run_database_migrations(db_path)
    engine, maker = create_engine_and_maker(db_path)
    return engine, ProfileService(ProfileRepository(maker))


@pytest.mark.asyncio
async def test_create_with_missing_group_is_field_422(tmp_path) -> None:
    engine, service = await _make_service(tmp_path)
    try:
        with pytest.raises(ReferenceValidationError) as excinfo:
            await service.create_profile(
                ProfileConfig(name="p", group_id="no-such-group")
            )
        assert excinfo.value.details[0]["loc"] == ["body", "group_id"]
        assert "no-such-group" in excinfo.value.details[0]["msg"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_with_missing_proxy_is_field_422(tmp_path) -> None:
    engine, service = await _make_service(tmp_path)
    try:
        with pytest.raises(ReferenceValidationError) as excinfo:
            await service.create_profile(
                ProfileConfig(name="p", proxy_id="no-such-proxy")
            )
        assert excinfo.value.details[0]["loc"] == ["body", "proxy_id"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_with_both_missing_reports_both_fields(tmp_path) -> None:
    engine, service = await _make_service(tmp_path)
    try:
        with pytest.raises(ReferenceValidationError) as excinfo:
            await service.create_profile(
                ProfileConfig(
                    name="p", group_id="no-group", proxy_id="no-proxy"
                )
            )
        locs = [d["loc"] for d in excinfo.value.details]
        assert ["body", "group_id"] in locs
        assert ["body", "proxy_id"] in locs
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_update_with_missing_group_is_field_422(tmp_path) -> None:
    engine, service = await _make_service(tmp_path)
    try:
        profile = await service.create_profile(ProfileConfig(name="p"))
        with pytest.raises(ReferenceValidationError) as excinfo:
            await service.update_profile(profile.id, {"group_id": "no-group"})
        assert excinfo.value.details[0]["loc"] == ["body", "group_id"]
        # The profile is untouched by the rejected update.
        assert (await service.get_profile(profile.id)).config.group_id is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_update_clearing_group_to_null_is_allowed(tmp_path) -> None:
    engine, service = await _make_service(tmp_path)
    try:
        group = await service.create_group(
            _NS(name="Work", color="blue", sort_order=0)
        )
        profile = await service.create_profile(
            ProfileConfig(name="p", group_id=group.id)
        )
        updated = await service.update_profile(profile.id, {"group_id": None})
        assert updated.config.group_id is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reorder_partial_set_is_422(tmp_path) -> None:
    engine, service = await _make_service(tmp_path)
    try:
        g1 = await service.create_group(
            _NS(name="A", color="blue", sort_order=0)
        )
        g2 = await service.create_group(
            _NS(name="B", color="green", sort_order=1)
        )
        with pytest.raises(ReferenceValidationError) as excinfo:
            await service.reorder_groups(
                _NS(ordered_ids=[g1.id])
            )
        assert excinfo.value.details[0]["loc"] == ["body", "ordered_ids"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reorder_unknown_or_duplicate_is_422(tmp_path) -> None:
    engine, service = await _make_service(tmp_path)
    try:
        g1 = await service.create_group(
            _NS(name="A", color="blue", sort_order=0)
        )
        with pytest.raises(ReferenceValidationError):
            await service.reorder_groups(
                _NS(ordered_ids=[g1.id, "no-such"])
            )
        with pytest.raises(ReferenceValidationError):
            await service.reorder_groups(
                _NS(ordered_ids=[g1.id, g1.id])
            )
    finally:
        await engine.dispose()


# ------------------------------------------------------------- router level


def _app(tmp_path):
    ctx = create_auth_context(tmp_path)
    app = create_app(
        db_path=tmp_path / "a28_router.db",
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


def test_router_create_with_missing_group_is_422(tmp_path) -> None:
    app, ctx = _app(tmp_path)
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        resp = client.post(
            "/api/v1/profiles",
            json={"name": "p", "group_id": "no-such-group"},
            headers=_login(client, ctx),
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "validation_error"
        assert body["details"][0]["loc"] == ["body", "group_id"]
        assert "detail" not in body


def test_router_reorder_partial_set_is_422(tmp_path) -> None:
    app, ctx = _app(tmp_path)
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        headers = _login(client, ctx)
        g1 = client.post(
            "/api/v1/groups",
            json={"name": "A", "color": "blue", "sort_order": 0},
            headers=headers,
        ).json()
        client.post(
            "/api/v1/groups",
            json={"name": "B", "color": "green", "sort_order": 1},
            headers=headers,
        )
        resp = client.post(
            "/api/v1/groups/reorder",
            json={"ordered_ids": [g1["id"]]},
            headers=headers,
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "validation_error"
        assert body["details"][0]["loc"] == ["body", "ordered_ids"]
        assert "detail" not in body
