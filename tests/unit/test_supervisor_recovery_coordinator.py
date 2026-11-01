"""Unit tests for RecoveryCoordinator logic and contracts."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from cbrowser.domain.models import ProfileConfig
from cbrowser.supervisor.recovery_coordinator import RecoveryCoordinator


class DummyResponse:
    def __init__(self, status_code: int, data: any):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            request = httpx.Request("GET", "http://test")
            response = httpx.Response(status_code=self.status_code, request=request)
            raise httpx.HTTPStatusError(
                "HTTP Error", request=request, response=response
            )


@pytest.fixture
def mock_core():
    core = MagicMock()
    locks = {}
    core._get_profile_lock.side_effect = lambda pid: locks.setdefault(
        pid, asyncio.Lock()
    )
    core.has_native_exit.return_value = False
    core._auth_headers.return_value = {"Authorization": "Bearer test-token"}
    core.api = MagicMock()
    core.api.get = AsyncMock()
    core.api.post = AsyncMock()
    core.docker = MagicMock()
    core.docker.scan_active_containers.return_value = []
    core.docker.client = MagicMock()
    core.events = MagicMock()
    core.events.emit_event = AsyncMock(return_value=True)
    core.report_terminal_observation = AsyncMock(return_value=True)
    core.stop_profile = AsyncMock()
    core.start_profile = AsyncMock()
    return core


@pytest.mark.asyncio
async def test_api_unreachable_or_error_safely_ignored(mock_core):
    mock_core.api.get.side_effect = Exception("Network connection refused")
    coordinator = RecoveryCoordinator(mock_core)

    await coordinator.tick()
    assert mock_core.stop_profile.call_count == 0
    assert mock_core.start_profile.call_count == 0


@pytest.mark.asyncio
async def test_brand_new_profile_not_auto_started(mock_core):
    mock_core.api.get.side_effect = [
        DummyResponse(
            200, [{"id": "p1", "name": "New Profile", "current_config_version": 1}]
        ),
        DummyResponse(
            200,
            {
                "profile_id": "p1",
                "desired_state": "running",
                "observed_state": "stopped",
                "runtime_instance_id": None,
                "failure_count": 0,
                "restart_blocked": False,
                "last_exit_event_id": None,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ),
    ]
    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()

    assert mock_core.start_profile.call_count == 0
    assert len(coordinator._in_flight_tasks) == 0


@pytest.mark.asyncio
async def test_manual_unblock_triggers_immediate_recovery(mock_core):
    cfg_data = ProfileConfig(name="Profile 1").model_dump()
    mock_core.api.get.side_effect = [
        DummyResponse(
            200, [{"id": "p1", "name": "Profile 1", "current_config_version": 1}]
        ),
        DummyResponse(
            200,
            {
                "profile_id": "p1",
                "desired_state": "running",
                "observed_state": "stopped",
                "runtime_instance_id": None,
                "failure_count": 0,
                "restart_blocked": False,
                "last_exit_event_id": "manual_prev_exit",
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ),
        DummyResponse(
            200,
            {
                "profile_id": "p1",
                "desired_state": "running",
                "observed_state": "stopped",
                "runtime_instance_id": None,
                "failure_count": 0,
                "restart_blocked": False,
                "last_exit_event_id": "manual_prev_exit",
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ),
        DummyResponse(
            200,
            {
                "profile_id": "p1",
                "version": 1,
                "config": cfg_data,
            },
        ),
    ]
    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()

    if "p1" in coordinator._in_flight_tasks:
        await coordinator._in_flight_tasks["p1"]

    assert mock_core.start_profile.call_count == 1
    _args, kwargs = mock_core.start_profile.call_args
    assert kwargs["profile_id"] == "p1"
    assert isinstance(kwargs["config"], ProfileConfig)


@pytest.mark.asyncio
async def test_restart_blocked_profile_is_not_retried(mock_core):
    mock_core.api.get.side_effect = [
        DummyResponse(
            200, [{"id": "p1", "name": "Blocked Profile", "current_config_version": 1}]
        ),
        DummyResponse(
            200,
            {
                "profile_id": "p1",
                "desired_state": "running",
                "observed_state": "stopped",
                "runtime_instance_id": None,
                "failure_count": 4,
                "restart_blocked": True,
                "last_exit_event_id": "exit_4",
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ),
    ]
    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()

    assert mock_core.start_profile.call_count == 0
    assert len(coordinator._in_flight_tasks) == 0


@pytest.mark.asyncio
async def test_desired_stopped_does_not_retry(mock_core):
    mock_core.api.get.side_effect = [
        DummyResponse(
            200, [{"id": "p1", "name": "Stopped Profile", "current_config_version": 1}]
        ),
        DummyResponse(
            200,
            {
                "profile_id": "p1",
                "desired_state": "stopped",
                "observed_state": "stopped",
                "runtime_instance_id": None,
                "failure_count": 1,
                "restart_blocked": False,
                "last_exit_event_id": "exit_1",
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ),
    ]
    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()

    assert mock_core.start_profile.call_count == 0
    assert len(coordinator._in_flight_tasks) == 0


@pytest.mark.asyncio
async def test_browser_exit_reports_error_observation_with_api_fencing(mock_core):
    mock_core.docker.scan_active_containers.return_value = [
        {
            "id": "container_b_1234567890ab",
            "name": "browser_test",
            "status": "exited",
            "profile_id": "p1",
            "instance_id": "inst_xyz",
            "role": "browser",
            "config_version": 1,
        }
    ]
    mock_container = MagicMock()
    mock_container.attrs = {"State": {"ExitCode": 137}}
    mock_core.docker.client.containers.get.return_value = mock_container

    mock_core.api.get.side_effect = [
        DummyResponse(200, []),  # /profiles
        DummyResponse(
            200,
            {  # /profiles/p1/runtime
                "profile_id": "p1",
                "desired_state": "running",
                "runtime_instance_id": "inst_xyz",
            },
        ),
    ]

    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()

    mock_core.report_terminal_observation.assert_awaited_once_with(
        "p1", "inst_xyz", 1, observed_state="error", reason="container_exit"
    )
    assert mock_core.events.emit_event.call_count == 0
    assert "inst_xyz" in coordinator._reported_dead_instances


@pytest.mark.asyncio
async def test_browser_exit_fencing_ignores_already_stopped_or_exited(mock_core):
    mock_core.docker.scan_active_containers.return_value = [
        {
            "id": "container_b_1234567890ab",
            "name": "browser_test",
            "status": "exited",
            "profile_id": "p1",
            "instance_id": "inst_old",
            "role": "browser",
            "config_version": 1,
        }
    ]
    # API says profile is already stopped
    mock_core.api.get.side_effect = [
        DummyResponse(200, []),
        DummyResponse(
            200,
            {
                "profile_id": "p1",
                "desired_state": "stopped",
                "runtime_instance_id": None,
            },
        ),
    ]
    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()

    # Must NOT report or emit anything
    assert mock_core.report_terminal_observation.call_count == 0
    assert mock_core.events.emit_event.call_count == 0


@pytest.mark.asyncio
async def test_cleanup_failure_cooldown_prevents_busy_loop(mock_core):
    cfg_data = ProfileConfig(name="Profile 1").model_dump()
    mock_core.docker.scan_active_containers.return_value = [
        {
            "id": "c1",
            "name": "old_container",
            "status": "exited",
            "profile_id": "p1",
            "instance_id": "inst_old",
            "role": "browser",
            "config_version": 1,
        }
    ]
    mock_core.stop_profile.side_effect = Exception("Docker stop failed")

    mock_core.api.get.side_effect = [
        DummyResponse(
            200, [{"id": "p1", "name": "Profile 1", "current_config_version": 1}]
        ),
        DummyResponse(
            200,
            {
                "profile_id": "p1",
                "desired_state": "running",
                "observed_state": "stopped",
                "runtime_instance_id": None,
                "failure_count": 1,
                "restart_blocked": False,
                "last_exit_event_id": "prev_exit",
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ),
        # second fetch in _execute_retry
        DummyResponse(
            200,
            {
                "profile_id": "p1",
                "desired_state": "running",
                "observed_state": "stopped",
                "runtime_instance_id": None,
                "failure_count": 1,
                "restart_blocked": False,
                "last_exit_event_id": "prev_exit",
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ),
        DummyResponse(
            200,
            {
                "profile_id": "p1",
                "version": 1,
                "config": cfg_data,
            },
        ),
    ]

    coordinator = RecoveryCoordinator(mock_core)
    coordinator._reported_dead_instances.add("inst_old")
    await coordinator.tick()

    if "p1" in coordinator._in_flight_tasks:
        await coordinator._in_flight_tasks["p1"]

    assert (
        mock_core.start_profile.call_count == 0
    )  # Did not start because cleanup failed!
    assert coordinator._cleanup_failures["p1"] == 1
    assert coordinator._cleanup_cooldown_until["p1"] > time.monotonic()

    # Second tick must be skipped due to cooldown
    async def persisted_state(path, **kwargs):
        if path.endswith("/profiles"):
            return DummyResponse(200, [{"id": "p1"}])
        return DummyResponse(
            200,
            {
                "desired_state": "running",
                "runtime_instance_id": None,
                "failure_count": 1,
                "last_exit_event_id": "prev_exit",
                "restart_blocked": False,
            },
        )

    mock_core.api.get.side_effect = persisted_state
    await coordinator.tick()
    # Persisted intent is still queried so a manual reset can cancel cooldown.
    assert (
        mock_core.stop_profile.call_count == 1
    )  # Still 1, didn't repeat stop_profile!


@pytest.mark.asyncio
async def test_close_cancels_in_flight_tasks_without_killing_runtime(mock_core):
    coordinator = RecoveryCoordinator(mock_core)

    async def long_retry():
        await asyncio.sleep(100.0)

    task = asyncio.create_task(long_retry())
    coordinator._in_flight_tasks["p1"] = task

    await coordinator.close()
    assert task.cancelled()
    assert len(coordinator._in_flight_tasks) == 0
    assert mock_core.stop_profile.call_count == 0


@pytest.mark.asyncio
async def test_error_observation_with_live_containers_schedules_retry(mock_core):
    """Chrome died inside a still-running container -> error observation retries."""
    mock_core.docker.scan_active_containers.return_value = [
        {
            "id": "container_b_live",
            "name": "browser_live",
            "status": "running",
            "profile_id": "p1",
            "instance_id": "inst_dead_browser",
            "role": "browser",
            "config_version": 1,
        },
        {
            "id": "container_s_live",
            "name": "stream_live",
            "status": "running",
            "profile_id": "p1",
            "instance_id": "inst_dead_browser",
            "role": "stream",
            "config_version": 1,
        },
    ]
    mock_core.api.get.side_effect = [
        DummyResponse(
            200, [{"id": "p1", "name": "Profile 1", "current_config_version": 1}]
        ),
        DummyResponse(
            200,
            {
                "profile_id": "p1",
                "desired_state": "running",
                "observed_state": "error",
                "runtime_instance_id": None,
                "config_version": 1,
                "failure_count": 1,
                "restart_blocked": False,
                "last_exit_event_id": "observed_error:inst_dead_browser",
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ),
    ]

    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()

    assert "p1" in coordinator._in_flight_tasks
    await coordinator.close()


@pytest.mark.asyncio
async def test_dead_instance_tracking_is_pruned_after_generation_ends(mock_core):
    mock_core.api.get.side_effect = [
        DummyResponse(200, [{"id": "p1", "name": "Profile 1"}]),
        DummyResponse(
            200,
            {
                "profile_id": "p1",
                "desired_state": "stopped",
                "observed_state": "stopped",
                "runtime_instance_id": None,
                "config_version": 1,
                "failure_count": 0,
                "restart_blocked": False,
                "last_exit_event_id": None,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ),
    ]
    mock_core.docker.scan_active_containers.return_value = []
    coordinator = RecoveryCoordinator(mock_core)
    coordinator._reported_dead_instances.update({"old_instance", "live_instance"})

    await coordinator.tick()

    assert coordinator._reported_dead_instances == set()


@pytest.mark.asyncio
async def test_recovery_uses_failed_instance_bound_config_version(mock_core):
    runtime_state = {
        "profile_id": "p1",
        "desired_state": "running",
        "observed_state": "error",
        "runtime_instance_id": None,
        "config_version": 1,
        "failure_count": 1,
        "restart_blocked": False,
        "last_exit_event_id": "observed_error:inst_failed",
        "updated_at": datetime.now(UTC).isoformat(),
    }
    mock_core.api.get.return_value = DummyResponse(200, runtime_state)
    mock_core.docker.scan_active_containers.return_value = []
    coordinator = RecoveryCoordinator(mock_core)
    coordinator._load_profile_config = AsyncMock(
        return_value=ProfileConfig(name="recovery")
    )

    await coordinator._execute_retry(
        "p1",
        0.0,
        runtime_state,
        {"id": "p1", "name": "Profile", "current_config_version": 2},
    )

    coordinator._load_profile_config.assert_awaited_once_with("p1", 1)
    assert mock_core.start_profile.await_args.kwargs["config_version"] == 1
