"""Recovery must retain authority and path boundaries on failure paths."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from cbrowser.domain.models import ProfileConfig
from cbrowser.shared.state_protocol import StateSnapshot
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.recovery_coordinator import RecoveryCoordinator
from cbrowser.supervisor.state_cache import _entry_dict


def response(code, data):
    return httpx.Response(code, json=data, request=httpx.Request("GET", "http://api"))


def core_for(tmp_path, api_get, containers=()):
    locks = {}

    # t083: recovery reads the core's state cache view; derive it from
    # the snapshot the fake API serves, through the real snapshot
    # validation and entry projection — the same shapes production
    # hands the coordinator (including the "id" alias), and None when
    # the snapshot is unavailable, which is the pause semantic.
    async def _entries():
        resp = await api_get("/api/v1/internal/supervisor/state/snapshot")
        if resp.status_code != 200:
            return None
        snapshot = StateSnapshot.model_validate(resp.json())
        return [_entry_dict(state) for state in snapshot.profiles]

    async def _entry(pid):
        entries = await _entries()
        if entries is None:
            return None
        for entry in entries:
            if entry["profile_id"] == pid:
                return entry
        return None

    return SimpleNamespace(
        is_profile_locked=lambda pid: locks.setdefault(pid, asyncio.Lock()).locked(),
        has_native_exit=lambda *_: False,
        api=SimpleNamespace(get=api_get),
        _state_entries=_entries,
        _state_entry=_entry,
        _auth_headers=dict,
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


def _snapshot_response(state: dict) -> dict:
    return {
        "api_epoch": "test-epoch",
        "profiles": [state],
        "next_cursor": None,
    }


def _full_state(pid: str, **overrides) -> dict:
    state = {
        "profile_id": pid,
        "display_number": 1,
        "desired_state": "running",
        "observed_state": "running",
        "runtime_instance_id": None,
        "config_version": 1,
        "failure_count": 0,
        "restart_blocked": False,
        "last_exit_event_id": None,
        "backoff_started_at": None,
        "next_retry_at": None,
        "updated_at": datetime.now(UTC).isoformat(),
        "state_revision": 1,
    }
    state.update(overrides)
    return state


@pytest.mark.asyncio
async def test_unavailable_runtime_authority_prevents_synthetic_exit(tmp_path):
    async def get(path, **kwargs):
        return response(503, {})

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
    state = _full_state("p1", failure_count=1, last_exit_event_id="e1")

    async def get(path, **kwargs):
        if path.endswith("/state/snapshot"):
            return response(200, _snapshot_response(state))
        return response(200, state)

    core = core_for(tmp_path, get)
    recovery = RecoveryCoordinator(core)
    recovery._cleanup_failures["p1"] = 3
    try:
        await recovery.tick()
        assert recovery.has_in_flight_task("p1") is False
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
        if path.endswith("/state/snapshot"):
            return response(
                200,
                _snapshot_response(
                    _full_state("p1", last_exit_event_id="manual")
                ),
            )
        return response(200, rt)

    core = core_for(tmp_path, get)
    await RecoveryCoordinator(core)._execute_retry(
        "p1", 0, rt, {"current_config_version": 1}
    )
    assert victim.read_text() == "foreign"
    core.start_profile.assert_not_awaited()
