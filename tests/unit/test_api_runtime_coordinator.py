"""Unit tests for RuntimeCoordinator in cbrowser/api/runtime_coordinator.py."""

import asyncio
from pathlib import Path

import httpx
import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.runtime_coordinator import (
    ReconcileOutcome,
    RuntimeCoordinator,
    RuntimeEventBroadcaster,
)
from cbrowser.domain.models import ProfileConfig
from cbrowser.services.profile_service import ProfileService
from pydantic import SecretStr


async def _wait_until(predicate, timeout: float = 5.0) -> None:
    """Yield to the loop until predicate is true, without fixed sleeps."""

    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0)

    await asyncio.wait_for(poll(), timeout)


class ManualClock:
    """Deterministic sleep seam injected into the coordinator module."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)
        await asyncio.sleep(0)


class _ClockAsyncio:
    def __init__(self, clock: ManualClock) -> None:
        self._clock = clock

    def __getattr__(self, name: str):
        return getattr(asyncio, name)

    async def sleep(self, delay: float) -> None:
        await self._clock.sleep(delay)


def _inject_clock(monkeypatch) -> ManualClock:
    import cbrowser.api.runtime_coordinator as coordinator_module

    clock = ManualClock()
    monkeypatch.setattr(coordinator_module, "asyncio", _ClockAsyncio(clock))
    return clock


class RecordingBroadcaster(RuntimeEventBroadcaster):
    """Signals publish completion through the public broadcaster contract."""

    def __init__(self) -> None:
        super().__init__()
        self.published = asyncio.Event()

    async def publish(self, data):
        try:
            return await super().publish(data)
        finally:
            self.published.set()


@pytest.fixture
async def profile_service(tmp_path: Path):
    db_path = tmp_path / "coord_test.db"
    run_database_migrations(db_path)
    engine, maker = create_engine_and_maker(db_path)
    repo = ProfileRepository(maker)
    svc = ProfileService(repo)
    yield svc
    await engine.dispose()


@pytest.mark.asyncio
async def test_coordinator_disabled_when_unconfigured(profile_service):
    broadcaster = RecordingBroadcaster()
    coord = RuntimeCoordinator(
        supervisor_url=None,
        supervisor_token=None,
        profile_service=profile_service,
        require_supervisor=False,
        event_broadcaster=broadcaster,
    )
    assert not coord.is_enabled()

    p = await profile_service.create_profile(ProfileConfig(name="test_p"))
    coord.trigger_reconcile(p.id)
    assert coord.get_last_error(p.id) == "Supervisor is not configured"
    await asyncio.wait_for(broadcaster.published.wait(), timeout=2.0)


@pytest.mark.asyncio
async def test_coordinator_require_supervisor_raises(profile_service):
    with pytest.raises(
        RuntimeError, match="Supervisor URL and token must be configured"
    ):
        RuntimeCoordinator(
            supervisor_url=None,
            supervisor_token=None,
            profile_service=profile_service,
            require_supervisor=True,
        )


@pytest.mark.asyncio
async def test_coordinator_start_rpc_success(profile_service):
    p = await profile_service.create_profile(ProfileConfig(name="test_p"))
    await profile_service.set_desired_state(p.id, "running")

    recorded_requests = []

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        recorded_requests.append(request)
        if request.url.path == "/supervisor/v1/profiles/start":
            return httpx.Response(
                200,
                json={
                    "profile_id": p.id,
                    "status": "running",
                    "runtime_instance_id": "inst_123",
                    "udp_mux_port": 30005,
                    "browser_container": "c_browser",
                    "stream_container": "c_stream",
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    broadcaster = RuntimeEventBroadcaster()
    coord = RuntimeCoordinator(
        supervisor_url="http://supervisor.internal:8005",
        supervisor_token=SecretStr("A" * 32),
        profile_service=profile_service,
        transport=transport,
        event_broadcaster=broadcaster,
    )
    recorded_requests.clear()
    try:
        success = await coord.reconcile_profile_now(p.id)
        assert success is ReconcileOutcome.CONVERGED
        assert len(recorded_requests) == 1
        assert recorded_requests[0].url.path == "/supervisor/v1/profiles/start"
        assert coord.get_last_error(p.id) is None
    finally:
        await coord.stop()


@pytest.mark.asyncio
async def test_coordinator_unreachable_sets_error_and_recovers(profile_service):
    p = await profile_service.create_profile(ProfileConfig(name="test_p"))
    await profile_service.set_desired_state(p.id, "running")

    should_fail = True

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if should_fail:
            raise httpx.ConnectError("Connection refused by mock")
        return httpx.Response(
            200,
            json={
                "profile_id": p.id,
                "status": "running",
                "runtime_instance_id": "inst_123",
                "udp_mux_port": 30005,
                "browser_container": "c_browser",
                "stream_container": "c_stream",
            },
        )

    transport = httpx.MockTransport(mock_handler)
    broadcaster = RuntimeEventBroadcaster()
    coord = RuntimeCoordinator(
        supervisor_url="http://supervisor.internal:8005",
        supervisor_token=SecretStr("A" * 32),
        profile_service=profile_service,
        transport=transport,
        event_broadcaster=broadcaster,
        initial_backoff=0.05,
        max_backoff=0.1,
    )
    await coord.start()
    try:
        # 1. First attempt fails: error should be recorded
        success = await coord.reconcile_profile_now(p.id)
        assert success is ReconcileOutcome.RETRYABLE
        err = coord.get_last_error(p.id)
        assert "Supervisor unreachable" in err

        # Verify desired state in DB is preserved
        rt = await profile_service.get_runtime(p.id)
        assert rt.desired_state == "running"

        # 2. Supervisor recovers: second attempt succeeds
        should_fail = False
        success2 = await coord.reconcile_profile_now(p.id)
        assert success2 is ReconcileOutcome.CONVERGED
        assert coord.get_last_error(p.id) is None
    finally:
        await coord.stop()


@pytest.mark.asyncio
async def test_coordinator_stop_rpc_success(profile_service):
    p = await profile_service.create_profile(ProfileConfig(name="test_p"))
    await profile_service.set_desired_state(p.id, "running")
    await profile_service.bind_runtime_instance(p.id, "inst_test_99", config_version=1)
    await profile_service.set_desired_state(p.id, "stopped")

    recorded_requests = []

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        recorded_requests.append(request)
        if request.url.path == "/supervisor/v1/profiles/stop":
            return httpx.Response(
                200,
                json={
                    "profile_id": p.id,
                    "runtime_instance_id": "inst_test_99",
                    "status": "stopped",
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    broadcaster = RuntimeEventBroadcaster()
    coord = RuntimeCoordinator(
        supervisor_url="http://supervisor.internal:8005",
        supervisor_token=SecretStr("A" * 32),
        profile_service=profile_service,
        transport=transport,
        event_broadcaster=broadcaster,
    )
    recorded_requests.clear()
    try:
        success = await coord.reconcile_profile_now(p.id)
        assert success is ReconcileOutcome.CONVERGED
        assert len(recorded_requests) == 1
        assert recorded_requests[0].url.path == "/supervisor/v1/profiles/stop"
        assert coord.get_last_error(p.id) is None
    finally:
        await coord.stop()


@pytest.mark.asyncio
async def test_coordinator_startup_reconciliation(profile_service):
    p = await profile_service.create_profile(ProfileConfig(name="p_startup"))
    await profile_service.set_desired_state(p.id, "running")
    # Desired is running, but no instance is bound (e.g. API restarted)

    reconcile_called = asyncio.Event()

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/supervisor/v1/profiles/start":
            reconcile_called.set()
            return httpx.Response(
                200,
                json={
                    "profile_id": p.id,
                    "status": "running",
                    "runtime_instance_id": "inst_recovered",
                    "udp_mux_port": 30005,
                    "browser_container": "c_browser",
                    "stream_container": "c_stream",
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    coord = RuntimeCoordinator(
        supervisor_url="http://supervisor.internal:8005",
        supervisor_token=SecretStr("A" * 32),
        profile_service=profile_service,
        transport=transport,
    )
    # On start, should scan DB and trigger reconcile for p
    await coord.start()
    try:
        await asyncio.wait_for(reconcile_called.wait(), timeout=3.0)
        assert reconcile_called.is_set()
    finally:
        await coord.stop()


@pytest.mark.asyncio
async def test_reconcile_loop_keeps_retrying_until_convergence(
    profile_service, monkeypatch
):
    """With the default (unbounded) retry policy, backoff is bounded but retries
    continue until the Supervisor converges, well past any fixed attempt count."""
    clock = _inject_clock(monkeypatch)
    p = await profile_service.create_profile(ProfileConfig(name="p_unbounded"))
    await profile_service.set_desired_state(p.id, "running")

    attempts = 0
    converged = asyncio.Event()

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 15:
            raise httpx.ConnectError("supervisor down")
        converged.set()
        return httpx.Response(
            200,
            json={
                "profile_id": p.id,
                "status": "running",
                "runtime_instance_id": "inst_late",
                "udp_mux_port": 30005,
                "browser_container": "c_browser",
                "stream_container": "c_stream",
            },
        )

    coord = RuntimeCoordinator(
        supervisor_url="http://supervisor.internal:8005",
        supervisor_token=SecretStr("A" * 32),
        profile_service=profile_service,
        transport=httpx.MockTransport(mock_handler),
        initial_backoff=0.001,
        max_backoff=0.002,
        backoff_factor=1.0,
    )
    assert coord.max_retries is None
    await coord.start()
    try:
        await asyncio.wait_for(converged.wait(), timeout=5.0)
        await _wait_until(lambda: coord.get_last_error(p.id) is None)
        assert attempts >= 15, f"expected continued retries, saw {attempts}"
        assert coord.get_last_error(p.id) is None
        assert clock.delays
    finally:
        await coord.stop()


@pytest.mark.asyncio
async def test_reconcile_loop_respects_explicit_retry_cap(
    profile_service, monkeypatch
):
    """An explicitly configured cap stops retries after that many failures."""
    clock = _inject_clock(monkeypatch)
    p = await profile_service.create_profile(ProfileConfig(name="p_capped"))
    await profile_service.set_desired_state(p.id, "running")

    attempts = 0

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("supervisor down")

    coord = RuntimeCoordinator(
        supervisor_url="http://supervisor.internal:8005",
        supervisor_token=SecretStr("A" * 32),
        profile_service=profile_service,
        transport=httpx.MockTransport(mock_handler),
        max_retries=2,
        initial_backoff=0.001,
        max_backoff=0.002,
        backoff_factor=1.0,
    )
    await coord.start()
    try:
        await _wait_until(
            lambda: "Reconciliation retry limit reached"
            in (coord.get_last_error(p.id) or "")
        )
        error = coord.get_last_error(p.id)
        assert attempts == 2, f"expected exactly 2 attempts, saw {attempts}"
        assert error is not None
        assert "Reconciliation retry limit reached" in error
        assert clock.delays
    finally:
        await coord.stop()
