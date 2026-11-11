"""t056 A17 / AC-005: proxy password change impact set.

A password change regenerates a config version ONLY for Profiles whose
CURRENT config references that proxy.  A Profile whose only reference is
in a running bound revision gets a runtime event only (no new version),
and a snapshot's frozen ``proxy_credential_revision`` is always the
revision of the proxy that snapshot's config actually references.

Replaces the invalidated
``test_proxy_connection_change_regenerates_versions_for_referencing_profiles``
in test_t035_profile_domain.py (deleted wholesale: it asserted the old
union semantics — every referencing profile, current or bound, got a new
version).
"""

from __future__ import annotations

import httpx
import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.runtime_coordinator import ReconcileOutcome, RuntimeCoordinator
from cbrowser.domain.models import ProfileConfig, ProxyCreateRequest
from cbrowser.services.profile_service import ProfileService


def _proxy_payload(name: str, host: str = "proxy.example.com") -> dict:
    return {
        "name": name,
        "scheme": "http",
        "host": host,
        "port": 8080,
        "username": "user",
        "password": "secret",
    }


def _proxy_link(name: str, host: str = "proxy.example.com") -> ProxyCreateRequest:
    return ProxyCreateRequest(
        name=name,
        proxy_url=f"http://user:secret@{host}:8080",
    )


async def _frozen_revision(repo: ProfileRepository, profile_id: str, version: int):
    snapshot = await repo.get_config_version(profile_id, version)
    assert snapshot is not None
    return snapshot.proxy_credential_revision


@pytest.mark.asyncio
async def test_password_change_versions_only_current_refs(db_context) -> None:
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    proxy_a = await repo.create_proxy(_proxy_payload("A", "a.example.com"))
    proxy_b = await repo.create_proxy(_proxy_payload("B", "b.example.com"))

    # P1: current config references A.
    p1 = await repo.create_profile(ProfileConfig(name="P1", proxy_id=proxy_a.id))
    # P2: bound V1 references A, current config references B.
    p2 = await repo.create_profile(ProfileConfig(name="P2", proxy_id=proxy_a.id))
    await repo.bind_runtime_instance(p2.id, "inst-p2", config_version=1)
    await repo.update_profile(p2.id, {"proxy_id": proxy_b.id})
    assert (await repo.get_profile(p2.id)).current_config_version == 2
    # P3: current config references A.
    p3 = await repo.create_profile(ProfileConfig(name="P3", proxy_id=proxy_a.id))

    old_a_revision = proxy_a.credential_revision
    updated, versioned, runtime_only = await repo.update_proxy(
        proxy_a.id, {"password": "rotated"}, True
    )
    assert updated is not None
    assert updated.credential_revision == old_a_revision + 1
    assert versioned == sorted([p1.id, p3.id])
    assert runtime_only == [p2.id]

    # Current refs advanced; the bound-only profile did not.
    assert (await repo.get_profile(p1.id)).current_config_version == 2
    assert (await repo.get_profile(p3.id)).current_config_version == 2
    assert (await repo.get_profile(p2.id)).current_config_version == 2
    assert len(await repo.list_config_versions(p1.id)) == 2
    assert len(await repo.list_config_versions(p3.id)) == 2
    assert len(await repo.list_config_versions(p2.id)) == 2

    # Frozen revisions follow the snapshot's own proxy, not the updated one.
    assert await _frozen_revision(repo, p1.id, 2) == old_a_revision + 1
    assert await _frozen_revision(repo, p3.id, 2) == old_a_revision + 1
    assert await _frozen_revision(repo, p2.id, 1) == old_a_revision
    assert await _frozen_revision(repo, p2.id, 2) == proxy_b.credential_revision


@pytest.mark.asyncio
async def test_non_connection_change_versions_nobody(db_context) -> None:
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    proxy_a = await repo.create_proxy(_proxy_payload("A", "a.example.com"))
    p1 = await repo.create_profile(ProfileConfig(name="P1", proxy_id=proxy_a.id))
    await repo.bind_runtime_instance(p1.id, "inst-p1", config_version=1)

    updated, versioned, runtime_only = await repo.update_proxy(
        proxy_a.id, {"name": "renamed"}, False
    )
    assert updated is not None and updated.name == "renamed"
    assert versioned == [] and runtime_only == []
    assert (await repo.get_profile(p1.id)).current_config_version == 1


@pytest.mark.asyncio
async def test_delete_proxy_still_refuses_bound_only_reference(db_context) -> None:
    """Delete-refusal and the used_by count keep the union semantics:
    a bound-only reference still blocks deletion."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    proxy_a = await repo.create_proxy(_proxy_payload("A", "a.example.com"))
    proxy_b = await repo.create_proxy(_proxy_payload("B", "b.example.com"))
    p2 = await repo.create_profile(ProfileConfig(name="P2", proxy_id=proxy_a.id))
    await repo.bind_runtime_instance(p2.id, "inst-p2", config_version=1)
    await repo.update_profile(p2.id, {"proxy_id": proxy_b.id})

    assert await repo.delete_proxy(proxy_a.id) == (False, 1)
    assert (await repo.get_proxy(proxy_a.id)) is not None
    assert (await repo.get_proxy(proxy_a.id)).used_by_count == 1


@pytest.mark.asyncio
async def test_ac005_bound_profile_starts_after_password_change(tmp_path) -> None:
    """AC-005: bound V1 references A, current config uses B; changing A's
    password does not advance the Profile's version, and the Profile can
    still start (on its latest version, B)."""
    db_path = tmp_path / "ac005.db"
    run_database_migrations(db_path)
    engine, maker = create_engine_and_maker(db_path)
    service = ProfileService(ProfileRepository(maker))
    try:
        proxy_a = await service.create_proxy(_proxy_link("A", "a.example.com"))
        proxy_b = await service.create_proxy(_proxy_link("B", "b.example.com"))
        profile = await service.create_profile(
            ProfileConfig(name="P-ac005", proxy_id=proxy_a.id)
        )
        await service.bind_runtime_instance(profile.id, "inst-1", config_version=1)
        await service.report_observed_state(
            profile.id, "inst-1", "running", config_version=1
        )
        await service.update_profile(profile.id, {"proxy_id": proxy_b.id})
        assert (await service.get_profile(profile.id)).current_config_version == 2

        from cbrowser.domain.models import ProxyUpdateRequest

        updated, versioned, runtime_only = await service.update_proxy(
            proxy_a.id,
            ProxyUpdateRequest(proxy_url="http://user:new-secret@a.example.com:8080"),
        )
        assert updated is not None
        assert versioned == [] and runtime_only == [profile.id]
        assert (await service.get_profile(profile.id)).current_config_version == 2

        # The profile still starts: reconcile converges on the latest
        # version (V2, proxy B) via a 200 /start.
        await service.set_desired_state(profile.id, "running")

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/start"):
                return httpx.Response(
                    200,
                    json={
                        "profile_id": profile.id,
                        "status": "running",
                        "runtime_instance_id": "inst-2",
                    },
                )
            return httpx.Response(404)

        coordinator = RuntimeCoordinator(
            supervisor_url="http://supervisor.internal:8005",
            supervisor_token="x" * 32,
            profile_service=service,
            transport=httpx.MockTransport(handler),
        )
        try:
            outcome = await coordinator.reconcile_profile_now(profile.id)
            assert outcome is ReconcileOutcome.CONVERGED
        finally:
            await coordinator.stop()
        assert (await service.get_profile(profile.id)).current_config_version == 2
    finally:
        await engine.dispose()
