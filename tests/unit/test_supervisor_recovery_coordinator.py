"""Unit tests for RecoveryCoordinator logic and contracts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
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
    core.is_profile_locked.side_effect = lambda pid: locks.setdefault(
        pid, asyncio.Lock()
    ).locked()
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
    core._reconcile_instance_observation = AsyncMock(return_value=None)
    # t083: recovery reads the core's minimal state cache view; the
    # default is unauthoritative (None), tests install state below.
    core._state_entries = AsyncMock(return_value=None)
    core._state_entry = AsyncMock(return_value=None)
    return core


def _install_state(mock_core, profiles, runtime, version=None):
    """Install cached state on the mock core (t083).

    ``profiles`` are the profile list entries and ``runtime`` the
    single runtime dict for the (one) profile under test; entries in
    the batch view merge both, mirroring the state cache's dicts.
    ``api.get`` keeps serving only config-version snapshots.
    """
    entries = [{**p, **runtime} for p in profiles]

    async def _entry(profile_id):
        return runtime if runtime.get("profile_id") == profile_id else None

    mock_core._state_entries = AsyncMock(return_value=entries)
    mock_core._state_entry = AsyncMock(side_effect=_entry)
    if version is not None:
        mock_core.api.get.side_effect = _api_handler(
            profiles, runtime, version
        )


async def _wait_until(predicate, timeout: float = 3.0) -> None:
    """Yield to the loop until predicate is true, without fixed sleeps."""

    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0)

    await asyncio.wait_for(poll(), timeout)


class ManualClock:
    """Deterministic monotonic clock and sleep seam for the coordinator."""

    def __init__(self) -> None:
        self.now = 10_000.0
        self.delays: list[float] = []
        self.block_sleeps = False
        self.sleep_started = asyncio.Event()
        self.sleep_cancelled = False
        self._release = asyncio.Event()

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)
        self.sleep_started.set()
        if not self.block_sleeps:
            await asyncio.sleep(0)
            return
        try:
            await self._release.wait()
        except asyncio.CancelledError:
            self.sleep_cancelled = True
            raise
        self._release.clear()

    def release_one(self) -> None:
        self._release.set()


class _ClockAsyncio:
    def __init__(self, clock: ManualClock) -> None:
        self._clock = clock

    def __getattr__(self, name: str):
        return getattr(asyncio, name)

    async def sleep(self, delay: float) -> None:
        await self._clock.sleep(delay)


@pytest.fixture
def fake_clock(monkeypatch):
    import cbrowser.supervisor.recovery_coordinator as recovery_module

    clock = ManualClock()
    monkeypatch.setattr(
        recovery_module, "time", SimpleNamespace(monotonic=clock.monotonic)
    )
    monkeypatch.setattr(recovery_module, "asyncio", _ClockAsyncio(clock))
    return clock


def _profile(profile_id: str = "p1", current_config_version: int = 1) -> dict:
    return {
        "id": profile_id,
        "display_number": 1,
        "name": "Profile 1",
        "current_config_version": current_config_version,
    }


def _runtime(**overrides) -> dict:
    data = {
        "profile_id": "p1",
        "desired_state": "running",
        "observed_state": "stopped",
        "runtime_instance_id": None,
        "config_version": 1,
        "failure_count": 0,
        "restart_blocked": False,
        "last_exit_event_id": None,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    data.update(overrides)
    return data


def _version(profile_id: str = "p1", version: int = 1) -> dict:
    return {
        "profile_id": profile_id,
        "version": version,
        "config": ProfileConfig(name="recovery").model_dump(),
    }


def _api_handler(profiles, runtime, version=None):
    async def handler(path: str, **kwargs):
        if path.endswith("/profiles"):
            return DummyResponse(200, profiles)
        if "/versions/" in path:
            return DummyResponse(200, version or _version())
        return DummyResponse(200, runtime)

    return handler


@pytest.mark.asyncio
async def test_api_unreachable_or_error_safely_ignored(mock_core):
    """An unreachable API pauses recovery without starting or stopping work."""
    # t083: an unreachable API leaves the state cache unauthoritative.
    mock_core._state_entries = AsyncMock(return_value=None)
    coordinator = RecoveryCoordinator(mock_core)

    await coordinator.tick()
    assert mock_core.stop_profile.call_count == 0
    assert mock_core.start_profile.call_count == 0
    mock_core.report_terminal_observation.assert_not_awaited()
    mock_core.events.emit_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_brand_new_profile_not_auto_started(mock_core):
    """A running desire with no prior failure is handled without auto-starting."""
    _install_state(mock_core, [_profile()], _runtime())
    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()

    assert mock_core.start_profile.call_count == 0
    assert mock_core.stop_profile.call_count == 0
    mock_core.report_terminal_observation.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_unblock_triggers_immediate_recovery(mock_core):
    """A prior manual exit event triggers exactly one immediate recovery start."""
    cfg_data = ProfileConfig(name="Profile 1").model_dump()
    _install_state(
        mock_core,
        [_profile()],
        _runtime(last_exit_event_id="manual_prev_exit"),
        {"profile_id": "p1", "version": 1, "config": cfg_data},
    )
    started = asyncio.Event()

    async def on_start(**kwargs):
        started.set()

    mock_core.start_profile.side_effect = on_start
    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()
    await asyncio.wait_for(started.wait(), timeout=3.0)

    assert mock_core.start_profile.call_count == 1
    _args, kwargs = mock_core.start_profile.call_args
    assert kwargs["profile_id"] == "p1"
    assert isinstance(kwargs["config"], ProfileConfig)
    assert kwargs["config_version"] == 1
    assert cfg_data["name"] == kwargs["config"].name


@pytest.mark.asyncio
async def test_restart_blocked_profile_is_not_retried(mock_core):
    """Restart-blocked intent is handled by leaving recovery idle."""
    _install_state(
        mock_core,
        [_profile()],
        _runtime(
            runtime_instance_id=None,
            failure_count=4,
            restart_blocked=True,
            last_exit_event_id="exit_4",
        ),
    )
    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()

    assert mock_core.start_profile.call_count == 0
    assert mock_core.stop_profile.call_count == 0


@pytest.mark.asyncio
async def test_desired_stopped_does_not_retry(mock_core):
    """Stopped intent is handled by not scheduling any retry."""
    _install_state(
        mock_core,
        [_profile()],
        _runtime(
            desired_state="stopped",
            failure_count=1,
            last_exit_event_id="exit_1",
        ),
    )
    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()

    assert mock_core.start_profile.call_count == 0
    assert mock_core.stop_profile.call_count == 0


@pytest.mark.asyncio
async def test_browser_exit_reports_error_observation_with_api_fencing(mock_core):
    """A dead browser instance is reported once; later ticks do not duplicate it."""
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

    fence_runtime = {
        "profile_id": "p1",
        "desired_state": "running",
        "runtime_instance_id": "inst_xyz",
    }
    _install_state(mock_core, [], fence_runtime)

    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()

    mock_core.report_terminal_observation.assert_awaited_once_with(
        "p1", "inst_xyz", 1, observed_state="error", reason="container_exit"
    )
    assert mock_core.events.emit_event.call_count == 0

    await coordinator.tick()
    assert mock_core.report_terminal_observation.await_count == 1


@pytest.mark.asyncio
async def test_browser_exit_fencing_ignores_already_stopped_or_exited(mock_core):
    """Stopped intent is handled without reporting or emitting an exit."""
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
    _install_state(
        mock_core,
        [],
        {
            "profile_id": "p1",
            "desired_state": "stopped",
            "runtime_instance_id": None,
        },
    )
    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()

    mock_core.report_terminal_observation.assert_not_awaited()
    mock_core.events.emit_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_failure_cooldown_prevents_busy_loop(mock_core, fake_clock):
    """Cleanup failure backs off, then retries once the cooldown expires."""
    containers = [
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
    cleanup_calls = 0
    cleanup_attempted = asyncio.Event()

    async def failing_stop(*args, **kwargs):
        nonlocal cleanup_calls
        cleanup_calls += 1
        cleanup_attempted.set()
        raise Exception("Docker stop failed")

    mock_core.stop_profile.side_effect = failing_stop
    runtime = _runtime(
        failure_count=1,
        last_exit_event_id="prev_exit",
        updated_at="2020-01-01T00:00:00+00:00",
    )
    _install_state(mock_core, [_profile()], runtime, _version())
    mock_core.docker.scan_active_containers.return_value = containers

    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()
    await asyncio.wait_for(cleanup_attempted.wait(), timeout=3.0)

    assert mock_core.start_profile.call_count == 0
    assert cleanup_calls == 1

    # Second tick is inside the cooldown: no repeated stop attempt.
    await coordinator.tick()
    assert cleanup_calls == 1
    assert mock_core.stop_profile.call_count == 1

    # After the cooldown the retry is allowed again.
    fake_clock.advance(6.0)
    cleanup_attempted.clear()
    await coordinator.tick()
    await asyncio.wait_for(cleanup_attempted.wait(), timeout=3.0)
    assert cleanup_calls == 2
    assert mock_core.start_profile.call_count == 0


@pytest.mark.asyncio
async def test_close_cancels_in_flight_tasks_without_killing_runtime(
    mock_core, fake_clock
):
    """close() cancels a waiting retry without stopping containers."""
    fake_clock.block_sleeps = True
    _install_state(
        mock_core,
        [_profile()],
        _runtime(
            failure_count=1,
            last_exit_event_id="prev_exit",
            updated_at=datetime.now(UTC).isoformat(),
        ),
        _version(),
    )
    mock_core.docker.scan_active_containers.return_value = []
    coordinator = RecoveryCoordinator(mock_core)

    await coordinator.tick()
    await asyncio.wait_for(fake_clock.sleep_started.wait(), timeout=3.0)
    assert fake_clock.delays

    await coordinator.close()
    assert fake_clock.sleep_cancelled is True
    assert mock_core.stop_profile.call_count == 0
    assert mock_core.start_profile.call_count == 0


@pytest.mark.asyncio
async def test_error_observation_with_live_containers_schedules_retry(
    mock_core, fake_clock
):
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
    runtime = _runtime(
        observed_state="error",
        runtime_instance_id=None,
        config_version=1,
        failure_count=1,
        last_exit_event_id="observed_error:inst_dead_browser",
        updated_at="2020-01-01T00:00:00+00:00",
    )
    _install_state(mock_core, [_profile()], runtime, _version())
    started = asyncio.Event()

    async def on_start(**kwargs):
        started.set()

    mock_core.start_profile.side_effect = on_start
    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()
    await asyncio.wait_for(started.wait(), timeout=3.0)

    _args, kwargs = mock_core.start_profile.call_args
    assert kwargs["profile_id"] == "p1"
    assert kwargs["config_version"] == 1
    assert isinstance(kwargs["config"], ProfileConfig)


@pytest.mark.asyncio
async def test_dead_instance_tracking_is_pruned_after_generation_ends(mock_core):
    """Tracking is cleared when the generation disappears, so a later one reports again."""
    dead = {
        "id": "container_b_dead",
        "name": "browser_dead",
        "status": "exited",
        "profile_id": "p1",
        "instance_id": "inst_old",
        "role": "browser",
        "config_version": 1,
    }
    mock_container = MagicMock()
    mock_container.attrs = {"State": {"ExitCode": 137}}
    mock_core.docker.client.containers.get.return_value = mock_container
    runtime = _runtime(runtime_instance_id="inst_old", failure_count=0)
    _install_state(mock_core, [_profile()], runtime, _version())
    coordinator = RecoveryCoordinator(mock_core)

    await coordinator.tick(containers=[dead])
    assert mock_core.report_terminal_observation.await_count == 1

    runtime["runtime_instance_id"] = None
    await coordinator.tick(containers=[])
    assert mock_core.report_terminal_observation.await_count == 1

    runtime["runtime_instance_id"] = "inst_old"
    await coordinator.tick(containers=[dead])
    assert mock_core.report_terminal_observation.await_count == 2


@pytest.mark.asyncio
async def test_recovery_uses_failed_instance_bound_config_version(
    mock_core, fake_clock
):
    """Recovery starts the config version the failed instance was bound to."""
    runtime_state = _runtime(
        observed_state="error",
        runtime_instance_id=None,
        config_version=1,
        failure_count=1,
        last_exit_event_id="observed_error:inst_failed",
        updated_at="2020-01-01T00:00:00+00:00",
    )
    _install_state(
        mock_core,
        [_profile(current_config_version=2)],
        runtime_state,
        _version(version=1),
    )
    mock_core.docker.scan_active_containers.return_value = []
    started = asyncio.Event()

    async def on_start(**kwargs):
        started.set()

    mock_core.start_profile.side_effect = on_start
    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()
    await asyncio.wait_for(started.wait(), timeout=3.0)

    _args, kwargs = mock_core.start_profile.call_args
    assert kwargs["config_version"] == 1
    assert _version()["config"]["name"] == kwargs["config"].name
