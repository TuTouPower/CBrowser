"""t056 coordinator error tests: A26 (version-bound last errors) and
A15 (downstream ErrorResponse preserved in the Profile error_reason).

Replaces test_runtime_coordinator_error_settle.py wholesale: that file
asserted the old semantics (a read of a converged runtime *cleared* the
stored error).  Under A26 a read never clears; an error settles only
when an instance of its target version reaches running, on a write
path.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.runtime_coordinator import (
    ReconcileOutcome,
    RuntimeCoordinator,
)
from cbrowser.api.v1.runtime_views import make_runtime_response
from cbrowser.domain.models import ProfileConfig
from cbrowser.services.profile_service import ProfileService
from pydantic import SecretStr


def _coordinator(profile_service=None) -> RuntimeCoordinator:
    return RuntimeCoordinator(
        supervisor_url=None,
        supervisor_token=SecretStr("test-token-1234567890abcdef"),
        profile_service=profile_service or object(),
    )


def _running_runtime(config_version: int, instance_id: str = "inst-1"):
    return SimpleNamespace(
        desired_state="running",
        observed_state="running",
        runtime_instance_id=instance_id,
        config_version=config_version,
    )


# ---------------------------------------------------------------- A26: pure reads


def test_read_does_not_clear_error() -> None:
    coordinator = _coordinator()
    coordinator.set_last_error("p1", "Supervisor start failed (503)")
    for _ in range(3):
        assert coordinator.get_last_error("p1") == "Supervisor start failed (503)"
    # A read with a merely pending runtime also leaves the error alone.
    pending = SimpleNamespace(
        desired_state="running",
        observed_state="stopped",
        runtime_instance_id=None,
        config_version=1,
    )
    assert coordinator.get_last_error("p1", runtime=pending) is not None
    assert coordinator.get_last_error("p1") == "Supervisor start failed (503)"


def test_old_version_running_keeps_new_version_error() -> None:
    """AC-009 (unit core): an old version running does not settle a new
    version's failure.  Repeated reads keep returning the error."""
    coordinator = _coordinator()
    coordinator.set_last_error(
        "p1", "Supervisor start failed (502)", config_version=2
    )
    old_running = _running_runtime(config_version=1)
    for _ in range(3):
        assert coordinator.get_last_error("p1", runtime=old_running) is not None
        assert coordinator.get_last_error("p1") is not None
    # The new version running settles the read...
    new_running = _running_runtime(config_version=2)
    assert coordinator.get_last_error("p1", runtime=new_running) is None
    # ...but only the write path clears the stored entry.
    assert coordinator.get_last_error("p1") is not None
    coordinator.clear_last_error_if_converged("p1", new_running)
    assert coordinator.get_last_error("p1") is None


def test_versionless_error_clears_on_any_running() -> None:
    """An error recorded without a target version (e.g. Supervisor not
    configured) settles on any running instance, as before."""
    coordinator = _coordinator()
    coordinator.set_last_error("p1", "Supervisor is not configured")
    converged = SimpleNamespace(
        desired_state="running",
        observed_state="running",
        runtime_instance_id="inst-1",
    )
    assert coordinator.get_last_error("p1", runtime=converged) is None
    coordinator.clear_last_error_if_converged("p1", converged)
    assert coordinator.get_last_error("p1") is None


def test_clear_with_older_version_keeps_newer_error() -> None:
    """A clear bound to an older version must not erase a newer
    version's failure (supersession only flows forward)."""
    coordinator = _coordinator()
    coordinator.set_last_error("p1", "boom", config_version=3)
    coordinator.clear_last_error("p1", config_version=2)
    assert coordinator.get_last_error("p1") == "boom"
    coordinator.clear_last_error("p1", config_version=3)
    assert coordinator.get_last_error("p1") is None


def test_set_preserves_target_version_on_follow_up() -> None:
    """A follow-up message about the same failure (no version passed)
    keeps the original target version."""
    coordinator = _coordinator()
    coordinator.set_last_error("p1", "boom", config_version=2)
    coordinator.set_last_error("p1", "boom; retry limit reached")
    old_running = _running_runtime(config_version=1)
    assert coordinator.get_last_error("p1", runtime=old_running) is not None
    new_running = _running_runtime(config_version=2)
    assert coordinator.get_last_error("p1", runtime=new_running) is None


# ------------------------------------------------- A26 + A15 end to end


async def _make_service(tmp_path):
    db_path = tmp_path / "coord_t056.db"
    run_database_migrations(db_path)
    engine, maker = create_engine_and_maker(db_path)
    service = ProfileService(ProfileRepository(maker))
    return db_path, engine, service


def _make_coordinator(service, handler) -> RuntimeCoordinator:
    return RuntimeCoordinator(
        supervisor_url="http://supervisor.internal:8005",
        supervisor_token=SecretStr("test-token-1234567890abcdef"),
        profile_service=service,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_old_running_new_failed_keeps_error_until_new_running(tmp_path):
    """AC-009: V1 running + V2 start fails -> repeated REST/SSE reads
    return the error; it clears only when V2 reaches running."""
    _, engine, service = await _make_service(tmp_path)
    try:
        profile = await service.create_profile(ProfileConfig(name="p_ac009"))
        await service.set_desired_state(profile.id, "running")
        await service.bind_runtime_instance(profile.id, "inst-1", config_version=1)
        await service.report_observed_state(
            profile.id, "inst-1", "running", config_version=1
        )
        # A config change creates V2 while V1 still runs.
        await service.update_profile(profile.id, {"timezone": "UTC"})
        prof = await service.get_profile(profile.id)
        assert prof.current_config_version == 2

        mode = {"fail": True}

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/start"):
                if mode["fail"]:
                    return httpx.Response(
                        502,
                        json={
                            "error": "supervisor_unavailable",
                            "message": "no slots left",
                            "retryable": True,
                        },
                    )
                return httpx.Response(
                    200,
                    json={
                        "profile_id": profile.id,
                        "status": "running",
                        "runtime_instance_id": "inst-2",
                    },
                )
            return httpx.Response(404)

        coordinator = _make_coordinator(service, handler)
        try:
            # V2 start fails: downstream error+message preserved.
            outcome = await coordinator.reconcile_profile_now(profile.id)
            assert outcome is ReconcileOutcome.RETRYABLE
            error = coordinator.get_last_error(profile.id)
            assert error is not None
            assert "supervisor_unavailable: no slots left" in error

            # Repeated reads (REST-style bare read and SSE-style read
            # with the V1 runtime) keep returning the error.
            for _ in range(3):
                assert coordinator.get_last_error(profile.id) == error
                rt_now = await service.get_runtime(profile.id)
                assert coordinator.get_last_error(profile.id, runtime=rt_now) == error
                view = await make_runtime_response(rt_now, coordinator=coordinator)
                assert view.last_coordinator_error == error

            # V2 start succeeds: the error clears.
            mode["fail"] = False
            outcome = await coordinator.reconcile_profile_now(profile.id)
            assert outcome is ReconcileOutcome.CONVERGED
            assert coordinator.get_last_error(profile.id) is None
        finally:
            await coordinator.stop()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_supervisor_error_response_preserves_error_and_message(tmp_path):
    """AC-004: the Supervisor's failure reason (error + message) appears
    in the Profile's error_reason (last_coordinator_error)."""
    _, engine, service = await _make_service(tmp_path)
    try:
        profile = await service.create_profile(ProfileConfig(name="p_ac004"))
        await service.set_desired_state(profile.id, "running")

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/start"):
                return httpx.Response(
                    503,
                    json={
                        "error": "runtime_unavailable",
                        "message": "pool exhausted",
                        "retryable": True,
                    },
                )
            return httpx.Response(404)

        coordinator = _make_coordinator(service, handler)
        try:
            outcome = await coordinator.reconcile_profile_now(profile.id)
            assert outcome is ReconcileOutcome.RETRYABLE
            assert coordinator.get_last_error(profile.id) == (
                "Supervisor start failed (503): "
                "runtime_unavailable: pool exhausted"
            )
        finally:
            await coordinator.stop()
    finally:
        await engine.dispose()
