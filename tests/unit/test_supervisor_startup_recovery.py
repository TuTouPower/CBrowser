"""Startup recovery and false-exit guards."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from cbrowser.supervisor.recovery_coordinator import RecoveryCoordinator


class DummyResponse:
    def __init__(self, status_code: int, data: Any):
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
    # Provide concrete lock and native exit tracker
    core._locks = {}

    def get_lock(pid: str):
        if pid not in core._locks:
            core._locks[pid] = asyncio.Lock()
        return core._locks[pid]

    core._get_profile_lock = get_lock
    core.is_profile_locked = lambda pid: get_lock(pid).locked()
    core._native_exits = set()
    core.has_native_exit = lambda pid, inst, ver: (pid, inst, ver) in core._native_exits
    return core


@pytest.mark.asyncio
async def test_missing_runtime_reports_error_observation_once(mock_core):
    """Missing runtime reports one authoritative error observation with 2s backoff."""
    pid = "p_startup_1"
    inst = "inst_killed_before_create"
    mock_core.docker.scan_active_containers.return_value = []

    mock_core.api.get.side_effect = [
        DummyResponse(
            200, [{"id": pid, "name": "Profile 1", "current_config_version": 1}]
        ),
        # 1st get in tick() profile loop
        DummyResponse(
            200,
            {
                "profile_id": pid,
                "desired_state": "running",
                "observed_state": "starting",
                "runtime_instance_id": inst,
                "config_version": 1,
                "failure_count": 0,
                "restart_blocked": False,
                "last_exit_event_id": None,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ),
        # 2nd get after the observation report
        DummyResponse(
            200,
            {
                "profile_id": pid,
                "desired_state": "running",
                "observed_state": "error",
                "runtime_instance_id": None,
                "config_version": 1,
                "failure_count": 1,
                "restart_blocked": False,
                "last_exit_event_id": f"observed_error:{inst}",
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ),
    ]

    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()

    mock_core.report_terminal_observation.assert_awaited_once_with(
        pid, inst, 1, observed_state="error", reason="missing_runtime"
    )
    assert mock_core.events.emit_event.call_count == 0
    assert coordinator.has_reported_dead_instance(inst)
    await coordinator.close()


@pytest.mark.asyncio
async def test_core_profile_lock_held_skips_exit_synthesis(mock_core):
    """When the profile lock is held, synthetic exits must be skipped."""
    pid = "p_locked"
    inst = "inst_active_launching"

    lock = mock_core._get_profile_lock(pid)
    await lock.acquire()
    try:
        mock_core.docker.scan_active_containers.return_value = [
            {
                "id": "container_b_locked",
                "name": "browser_locked",
                "status": "exited",
                "profile_id": pid,
                "instance_id": inst,
                "role": "browser",
                "config_version": 1,
            }
        ]
        mock_core.api.get.side_effect = [
            DummyResponse(
                200,
                [{"id": pid, "name": "Profile Locked", "current_config_version": 1}],
            ),
        ]
        coordinator = RecoveryCoordinator(mock_core)
        await coordinator.tick()

        assert mock_core.events.emit_event.call_count == 0
        mock_core.report_terminal_observation.assert_not_awaited()
    finally:
        lock.release()


@pytest.mark.asyncio
async def test_native_exit_priority_prevents_synthetic_docker_exit(mock_core):
    """Pending native exit in Core takes priority over dead Docker container scan."""
    pid = "p_native_prio"
    inst = "inst_native_normal"
    cfg_ver = 1
    mock_core._native_exits.add((pid, inst, cfg_ver))

    mock_core.docker.scan_active_containers.return_value = [
        {
            "id": "container_b_dead",
            "name": "browser_dead",
            "status": "exited",
            "profile_id": pid,
            "instance_id": inst,
            "role": "browser",
            "config_version": cfg_ver,
        }
    ]
    mock_core.api.get.side_effect = [
        DummyResponse(
            200,
            [{"id": pid, "name": "Profile Native", "current_config_version": cfg_ver}],
        ),
        DummyResponse(
            200,
            {
                "profile_id": pid,
                "desired_state": "running",
                "runtime_instance_id": inst,
                "config_version": cfg_ver,
            },
        ),
        DummyResponse(
            200,
            {
                "profile_id": pid,
                "desired_state": "running",
                "observed_state": "running",
                "runtime_instance_id": inst,
                "config_version": cfg_ver,
                "failure_count": 0,
                "restart_blocked": False,
                "last_exit_event_id": None,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ),
    ]

    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()

    assert mock_core.events.emit_event.call_count == 0
    mock_core.report_terminal_observation.assert_not_awaited()


@pytest.mark.asyncio
async def test_native_exit_priority_prevents_synthetic_missing_exit(mock_core):
    """Pending native exit in Core takes priority over missing container scan."""
    pid = "p_native_missing"
    inst = "inst_native_missing"
    cfg_ver = 2
    mock_core._native_exits.add((pid, inst, cfg_ver))

    mock_core.docker.scan_active_containers.return_value = []
    mock_core.api.get.side_effect = [
        DummyResponse(
            200,
            [
                {
                    "id": pid,
                    "name": "Profile Missing Native",
                    "current_config_version": cfg_ver,
                }
            ],
        ),
        DummyResponse(
            200,
            {
                "profile_id": pid,
                "desired_state": "running",
                "observed_state": "running",
                "runtime_instance_id": inst,
                "config_version": cfg_ver,
                "failure_count": 0,
                "restart_blocked": False,
                "last_exit_event_id": None,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ),
    ]

    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()

    assert mock_core.events.emit_event.call_count == 0
    mock_core.report_terminal_observation.assert_not_awaited()


@pytest.mark.asyncio
async def test_docker_created_status_does_not_synthesize_exit(mock_core):
    """A created container has not exited."""
    pid = "p_created"
    inst = "inst_creating"
    mock_core.docker.scan_active_containers.return_value = [
        {
            "id": "container_b_creating",
            "name": "browser_creating",
            "status": "created",
            "profile_id": pid,
            "instance_id": inst,
            "role": "browser",
            "config_version": 1,
        }
    ]
    mock_core.api.get.side_effect = [
        DummyResponse(
            200, [{"id": pid, "name": "Profile Creating", "current_config_version": 1}]
        ),
        DummyResponse(
            200,
            {
                "profile_id": pid,
                "desired_state": "running",
                "observed_state": "starting",
                "runtime_instance_id": inst,
                "config_version": 1,
                "failure_count": 0,
                "restart_blocked": False,
                "last_exit_event_id": None,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ),
    ]

    coordinator = RecoveryCoordinator(mock_core)
    await coordinator.tick()

    assert mock_core.events.emit_event.call_count == 0
    mock_core.report_terminal_observation.assert_not_awaited()


@pytest.mark.asyncio
async def test_control_plane_created_before_initial_scan(tmp_path, monkeypatch):
    """t027 startup order: the control plane is created before the initial
    reconciliation scan runs, so supervisor liveness is never blocked by
    the scan.  This replaces the pre-t027 test that asserted the scan ran
    first and a scan failure still reached control-plane creation; the
    semantics are inverted on purpose (health must not wait for the scan).
    """
    from types import SimpleNamespace

    from cbrowser.supervisor import runner as runner_module
    from cbrowser.supervisor.path_validator import PathValidator

    class ControlPlaneReached(Exception):
        pass

    core = SimpleNamespace(
        events=SimpleNamespace(replay_spooled_events=AsyncMock(return_value=0)),
        consume_disk_events=AsyncMock(return_value=0),
        scan_and_reconcile_existing=AsyncMock(return_value=[]),
        docker=SimpleNamespace(
            validator=PathValidator(tmp_path), resource_prefix="cb"
        ),
        api=SimpleNamespace(),
        _token_file=tmp_path / "token",
    )

    def create_control_app(**_kwargs):
        raise ControlPlaneReached

    monkeypatch.setattr(runner_module, "create_control_app", create_control_app)
    with pytest.raises(ControlPlaneReached):
        await runner_module.serve_supervisor(core, "127.0.0.1", 0)
    core.scan_and_reconcile_existing.assert_not_awaited()


@pytest.mark.asyncio
async def test_initial_scan_failure_after_control_plane_started(
    tmp_path, monkeypatch
):
    """A failing initial scan must not prevent the control server from
    starting: the server serve() is entered before the scan is awaited,
    and the scan failure is logged, not raised (t027)."""
    import asyncio
    from types import SimpleNamespace

    from cbrowser.supervisor import runner as runner_module
    from cbrowser.supervisor.path_validator import PathValidator

    order: list[str] = []

    class FakeConfig:
        def __init__(self, **_kwargs):
            pass

    class FakeServer:
        def __init__(self, _config):
            self.should_exit = False

        async def serve(self):
            order.append("server_serve")
            # Exit immediately: serve_supervisor then surfaces the
            # unexpected-exit error, which is how this test terminates.
            return None

    async def failing_scan():
        # Wait until the server task has actually been scheduled before
        # recording the scan.  Under the pre-t027 order (scan awaited
        # before the control server existed) "server_serve" can never
        # appear here, so the order assertion below fails there; under
        # the t027 order the already-created server task runs first.
        for _ in range(1000):
            if "server_serve" in order:
                break
            await asyncio.sleep(0)
        order.append("scan")
        raise RuntimeError("docker unavailable")

    core = SimpleNamespace(
        events=SimpleNamespace(replay_spooled_events=AsyncMock(return_value=0)),
        consume_disk_events=AsyncMock(return_value=0),
        scan_and_reconcile_existing=AsyncMock(side_effect=failing_scan),
        docker=SimpleNamespace(
            validator=PathValidator(tmp_path), resource_prefix="cb"
        ),
        api=SimpleNamespace(),
        _token_file=tmp_path / "token",
    )

    def create_control_app(**_kwargs):
        order.append("create_app")
        return object()

    monkeypatch.setattr(runner_module, "create_control_app", create_control_app)
    monkeypatch.setattr(
        runner_module,
        "uvicorn",
        SimpleNamespace(Config=FakeConfig, Server=FakeServer),
    )
    with pytest.raises(RuntimeError, match="exited unexpectedly"):
        await asyncio.wait_for(
            runner_module.serve_supervisor(core, "127.0.0.1", 0), timeout=30
        )
    assert order[:3] == ["create_app", "server_serve", "scan"]
