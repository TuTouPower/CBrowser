"""Recovery must retain authority and path boundaries on failure paths."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from cbrowser.domain.models import ProfileConfig
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.recovery_coordinator import RecoveryCoordinator


def response(code, data):
    return httpx.Response(code, json=data, request=httpx.Request("GET", "http://api"))


def core_for(tmp_path, api_get, containers=()):
    locks = {}
    return SimpleNamespace(
        _get_profile_lock=lambda pid: locks.setdefault(pid, asyncio.Lock()),
        has_native_exit=lambda *_: False,
        api=SimpleNamespace(get=api_get),
        _auth_headers=lambda: {},
        docker=SimpleNamespace(
            validator=PathValidator(tmp_path),
            scan_active_containers=lambda: list(containers),
            client=SimpleNamespace(
                containers=SimpleNamespace(
                    get=lambda _: SimpleNamespace(attrs={"State": {"ExitCode": 137}})
                )
            ),
        ),
        events=SimpleNamespace(emit_event=AsyncMock(return_value=True)),
        start_profile=AsyncMock(),
        stop_profile=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_unavailable_runtime_authority_prevents_synthetic_exit(tmp_path):
    async def get(path, **kwargs):
        return response(200, []) if path.endswith("/profiles") else response(503, {})

    core = core_for(
        tmp_path,
        get,
        [
            {
                "profile_id": "p1",
                "role": "browser",
                "id": "dead",
                "instance_id": "i1",
                "status": "exited",
                "config_version": 1,
            }
        ],
    )
    await RecoveryCoordinator(core).tick()
    core.events.emit_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_exhausted_cleanup_does_not_schedule_another_attempt(tmp_path):
    rt = {
        "desired_state": "running",
        "runtime_instance_id": None,
        "failure_count": 1,
        "last_exit_event_id": "e1",
        "updated_at": datetime.now(UTC).isoformat(),
        "restart_blocked": False,
    }

    async def get(path, **kwargs):
        return (
            response(200, [{"id": "p1"}])
            if path.endswith("/profiles")
            else response(200, rt)
        )

    core = core_for(tmp_path, get)
    recovery = RecoveryCoordinator(core)
    recovery._cleanup_failures["p1"] = 3
    try:
        await recovery.tick()
        assert "p1" not in recovery._in_flight_tasks
    finally:
        await recovery.close()


@pytest.mark.asyncio
async def test_singleton_cleanup_cannot_follow_another_profiles_directory(tmp_path):
    own = tmp_path / "profiles" / "p1"
    foreign = tmp_path / "profiles" / "p2" / "profile"
    own.mkdir(parents=True)
    foreign.mkdir(parents=True)
    victim = foreign / "SingletonLock"
    victim.write_text("foreign")
    (own / "profile").symlink_to(foreign, target_is_directory=True)
    rt = {
        "desired_state": "running",
        "runtime_instance_id": None,
        "restart_blocked": False,
        "failure_count": 0,
        "last_exit_event_id": "manual",
    }

    async def get(path, **kwargs):
        if "/versions/" in path:
            return response(
                200,
                {
                    "profile_id": "p1",
                    "version": 1,
                    "config": ProfileConfig(name="p1").model_dump(),
                },
            )
        return response(200, rt)

    core = core_for(tmp_path, get)
    await RecoveryCoordinator(core)._execute_retry(
        "p1", 0, rt, {"current_config_version": 1}
    )
    assert victim.read_text() == "foreign"
    core.start_profile.assert_not_awaited()
