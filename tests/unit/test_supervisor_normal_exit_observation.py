"""Unit tests for Supervisor normal exit observation and Agent cross-verification.

Validates that:
1. Agent cross-verifies exit state against live browser process and CDP;
   forged exit files while the process is alive are rejected.
2. Supervisor queries Agent via restricted UDS and validates Profile, instance, and
   config_version identity before acknowledging normal exit.
3. Clean exits transition to observed_state="stopped", reason="normal_exit".
4. Owner-loss abnormal exits (exit code 0 with process_observation_lost) preserve
   error semantics (observed_state="error", reason="process_lost").
5. Both consume_disk_events and scan_and_reconcile_existing observe running Agent
   processes instead of short-circuiting or ignoring running containers.
6. Deduplication prevents re-reporting the same generation, and un-ACKed reports retry.
"""

from __future__ import annotations

import asyncio
import http.server
import json
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from cbrowser.runtime_agent.agent import create_agent_app
from cbrowser.runtime_agent.event_storage import EventStorage
from cbrowser.runtime_agent.protocol import (
    HealthResponse,
    RuntimeEventRecord,
    RuntimeStateRecord,
)
from cbrowser.supervisor.core import ActiveSession, SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator
from docker.errors import NotFound


class _FakeContainer:
    def __init__(self, instance_id: str, status: str, config_version: int = 1) -> None:
        self.labels = {
            "com.cbrowser.instance-id": instance_id,
            "com.cbrowser.config-version": str(config_version),
        }
        self.status = status
        self.id = f"c_{instance_id}"


class _FakeContainers:
    def __init__(self) -> None:
        self._containers: dict[str, _FakeContainer] = {}

    def set(self, name: str, container: _FakeContainer | None) -> None:
        if container is None:
            self._containers.pop(name, None)
        else:
            self._containers[name] = container

    def get(self, name: str) -> _FakeContainer:
        if name not in self._containers:
            raise NotFound(f"container {name} not found")
        return self._containers[name]


class _FakeDockerAdapter:
    def __init__(self, data_root: Path) -> None:
        self.validator = PathValidator(data_root)
        self.containers = _FakeContainers()
        self.client = SimpleNamespace(
            containers=self.containers,
            api=SimpleNamespace(
                inspect_container=lambda cid: {
                    "HostConfig": {
                        "PortBindings": {"30000/udp": [{"HostPort": "30001"}]}
                    }
                }
            ),
        )
        self.resource_prefix = "test"
        self._active_containers: list[dict] = []

    def get_browser_container_name(self, profile_id: str) -> str:
        return f"cbrowser-browser-{profile_id}"

    def get_stream_container_name(self, profile_id: str) -> str:
        return f"cbrowser-stream-{profile_id}"

    def scan_active_containers(self) -> list[dict]:
        return list(self._active_containers)

    def prepare_profile_directories(self, profile_id: str) -> dict[str, Path]:
        runtime_dir = self.validator.get_runtime_dir(profile_id)
        profile_dir = self.validator.get_profile_data_dir(profile_id)
        events_dir = self.validator.get_events_dir(profile_id)
        exchange_dir = self.validator.get_exchange_dir(profile_id)
        for d in (runtime_dir, profile_dir, events_dir, exchange_dir):
            d.mkdir(parents=True, exist_ok=True)
        return {
            "runtime": runtime_dir,
            "profile": profile_dir,
            "events": events_dir,
            "exchange": exchange_dir,
        }


class _CDPVersionHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/json/version":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"Browser": "Chrome/146.0"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.mark.asyncio
async def test_agent_health_clean_exit_when_browser_dead(tmp_path: Path) -> None:
    """Agent /health returns clean stopped state when process is truly dead."""
    run_dir = tmp_path / "runtime"
    run_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir = tmp_path / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    storage = EventStorage(run_dir)
    dead_pid = 999999
    storage.save_state(
        RuntimeStateRecord(
            profile_id="prof_1",
            runtime_instance_id="inst_1",
            config_version=1,
            state="stopped",
            exit_code=0,
            exit_reason="normal",
            browser_pid=dead_pid,
        )
    )
    runner_info = {
        "profile_id": "prof_1",
        "runtime_instance_id": "inst_1",
        "config_version": 1,
        "browser_pid": dead_pid,
        "cdp_port": 9222,
        "runner_pid": 100,
    }
    (run_dir / "runner_info.json").write_text(json.dumps(runner_info), encoding="utf-8")

    app = create_agent_app(run_dir=run_dir, default_download_dir=downloads_dir)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://uds") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["details"]["state"] == "stopped"
        assert data["details"]["exit_code"] == 0
        assert data["details"]["exit_reason"] == "normal"


@pytest.mark.asyncio
async def test_agent_health_cross_verification_rejects_forged_exit_when_browser_alive(
    tmp_path: Path,
) -> None:
    """Agent /health must not return state='stopped' if the browser process is
    actually alive.
    """
    run_dir = tmp_path / "runtime"
    run_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir = tmp_path / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    live_proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(30)"
    )
    try:
        storage = EventStorage(run_dir)
        storage.save_state(
            RuntimeStateRecord(
                profile_id="prof_1",
                runtime_instance_id="inst_1",
                config_version=1,
                state="stopped",
                exit_code=0,
                exit_reason="normal",
                browser_pid=live_proc.pid,
            )
        )
        runner_info = {
            "profile_id": "prof_1",
            "runtime_instance_id": "inst_1",
            "config_version": 1,
            "browser_pid": live_proc.pid,
            "cdp_port": 9222,
            "runner_pid": 100,
        }
        (run_dir / "runner_info.json").write_text(
            json.dumps(runner_info), encoding="utf-8"
        )

        app = create_agent_app(run_dir=run_dir, default_download_dir=downloads_dir)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://uds"
        ) as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["details"].get("state") != "stopped"
    finally:
        live_proc.terminate()
        await live_proc.wait()


@pytest.mark.asyncio
async def test_agent_health_cross_verification_rejects_forged_exit_when_cdp_alive(
    tmp_path: Path,
) -> None:
    """If browser_pid is dead but CDP endpoint responds, terminal exit must be
    rejected.
    """
    run_dir = tmp_path / "runtime"
    run_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir = tmp_path / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    # Start dummy CDP HTTP server on an ephemeral port
    cdp_server = http.server.HTTPServer(("127.0.0.1", 0), _CDPVersionHandler)
    cdp_port = cdp_server.server_address[1]
    cdp_thread = threading.Thread(target=cdp_server.serve_forever, daemon=True)
    cdp_thread.start()

    try:
        storage = EventStorage(run_dir)
        dead_pid = 999999
        storage.save_state(
            RuntimeStateRecord(
                profile_id="prof_cdp",
                runtime_instance_id="inst_cdp",
                config_version=1,
                state="stopped",
                exit_code=0,
                exit_reason="normal",
                browser_pid=dead_pid,
            )
        )
        runner_info = {
            "profile_id": "prof_cdp",
            "runtime_instance_id": "inst_cdp",
            "config_version": 1,
            "browser_pid": dead_pid,
            "cdp_port": cdp_port,
            "runner_pid": 100,
        }
        (run_dir / "runner_info.json").write_text(
            json.dumps(runner_info), encoding="utf-8"
        )

        app = create_agent_app(run_dir=run_dir, default_download_dir=downloads_dir)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://uds"
        ) as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            # CDP was alive, so stopped must not be accepted
            assert data["details"].get("state") != "stopped"
    finally:
        cdp_server.shutdown()
        cdp_server.server_close()


@pytest.mark.asyncio
async def test_supervisor_reconcile_normal_exit_via_uds(tmp_path: Path) -> None:
    """_reconcile_instance_observation queries Agent UDS, verifies identity
    and reports normal_exit.
    """
    data_root = tmp_path / "data"
    docker = _FakeDockerAdapter(data_root)
    profile_id = "prof_test"
    instance_id = "inst_clean_1"
    config_version = 1

    dirs = docker.prepare_profile_directories(profile_id)
    b_c = _FakeContainer(instance_id, "running", config_version)
    docker.containers.set(docker.get_browser_container_name(profile_id), b_c)

    # Setup Agent state as stopped clean
    storage = EventStorage(dirs["runtime"])
    storage.save_state(
        RuntimeStateRecord(
            profile_id=profile_id,
            runtime_instance_id=instance_id,
            config_version=config_version,
            state="stopped",
            exit_code=0,
            exit_reason="normal",
            browser_pid=999999,
        )
    )
    (dirs["runtime"] / "runner_info.json").write_text(
        json.dumps(
            {
                "profile_id": profile_id,
                "runtime_instance_id": instance_id,
                "config_version": config_version,
                "browser_pid": 999999,
                "cdp_port": 9222,
                "runner_pid": 100,
            }
        ),
        encoding="utf-8",
    )

    agent_app = create_agent_app(
        run_dir=dirs["runtime"], default_download_dir=dirs["exchange"]
    )
    server_transport = httpx.ASGITransport(app=agent_app)

    api_client = AsyncMock(spec=httpx.AsyncClient)
    api_post_resp = MagicMock(status_code=200)
    api_client.post = AsyncMock(return_value=api_post_resp)

    core = SupervisorCore(
        docker_adapter=docker,
        port_allocator=PortAllocator(),
        event_forwarder=MagicMock(spec=EventForwarder),
        api_client=api_client,
    )

    async def _mock_query(pid: str) -> HealthResponse | None:
        async with httpx.AsyncClient(
            transport=server_transport, base_url="http://uds"
        ) as c:
            r = await c.get("/health")
            if r.status_code == 200:
                return HealthResponse.model_validate(r.json())
            return None

    core._query_agent_health = _mock_query

    # Track active session
    core._sessions[profile_id] = ActiveSession(
        profile_id=profile_id,
        runtime_instance_id=instance_id,
        config_version=config_version,
        udp_mux_port=30001,
        browser_container_id=b_c.id,
        stream_container_id="s_1",
        desired_state="running",
        observed_state="running",
    )

    obs = await core._reconcile_instance_observation(
        profile_id, instance_id, config_version, container_status="running"
    )
    assert obs == "stopped"

    # Verify session and API call
    assert core.get_session(profile_id).observed_state == "stopped"
    assert core.get_session(profile_id).desired_state == "stopped"
    api_client.post.assert_called_once()
    assert api_client.post.call_args.kwargs["json"]["observed_state"] == "stopped"
    assert api_client.post.call_args.kwargs["json"]["reason"] == "normal_exit"


@pytest.mark.asyncio
async def test_supervisor_reconcile_owner_loss_reports_error(tmp_path: Path) -> None:
    """_reconcile_instance_observation on owner-loss reports error
    (reason='process_lost').
    """
    data_root = tmp_path / "data"
    docker = _FakeDockerAdapter(data_root)
    profile_id = "prof_loss"
    instance_id = "inst_loss_1"
    config_version = 1

    dirs = docker.prepare_profile_directories(profile_id)
    storage = EventStorage(dirs["runtime"])
    storage.save_state(
        RuntimeStateRecord(
            profile_id=profile_id,
            runtime_instance_id=instance_id,
            config_version=config_version,
            state="error",
            exit_code=0,
            exit_reason="process_observation_lost",
            browser_pid=999999,
        )
    )
    (dirs["runtime"] / "runner_info.json").write_text(
        json.dumps(
            {
                "profile_id": profile_id,
                "runtime_instance_id": instance_id,
                "config_version": config_version,
                "browser_pid": 999999,
                "cdp_port": 9222,
                "runner_pid": 100,
            }
        ),
        encoding="utf-8",
    )

    agent_app = create_agent_app(
        run_dir=dirs["runtime"], default_download_dir=dirs["exchange"]
    )
    server_transport = httpx.ASGITransport(app=agent_app)

    api_client = AsyncMock(spec=httpx.AsyncClient)
    api_client.post = AsyncMock(return_value=MagicMock(status_code=200))

    core = SupervisorCore(
        docker_adapter=docker,
        port_allocator=PortAllocator(),
        event_forwarder=MagicMock(spec=EventForwarder),
        api_client=api_client,
    )

    async def _mock_query(pid: str) -> HealthResponse | None:
        async with httpx.AsyncClient(
            transport=server_transport, base_url="http://uds"
        ) as c:
            r = await c.get("/health")
            if r.status_code == 200:
                return HealthResponse.model_validate(r.json())
            return None

    core._query_agent_health = _mock_query

    core._sessions[profile_id] = ActiveSession(
        profile_id=profile_id,
        runtime_instance_id=instance_id,
        config_version=config_version,
        udp_mux_port=30001,
        browser_container_id="b_1",
        stream_container_id="s_1",
        desired_state="running",
        observed_state="running",
    )

    obs = await core._reconcile_instance_observation(
        profile_id, instance_id, config_version, container_status="running"
    )
    assert obs == "error"
    assert core.get_session(profile_id).observed_state == "error"
    assert (
        core.get_session(profile_id).desired_state == "running"
    )  # running intent preserved!
    assert api_client.post.call_args.kwargs["json"]["observed_state"] == "error"
    assert api_client.post.call_args.kwargs["json"]["reason"] == "process_lost"


@pytest.mark.asyncio
async def test_supervisor_reconcile_identity_mismatch_rejected(tmp_path: Path) -> None:
    """Agent health with mismatched profile, instance, or config_version must
    not report stopped.
    """
    data_root = tmp_path / "data"
    docker = _FakeDockerAdapter(data_root)
    profile_id = "prof_a"

    dirs = docker.prepare_profile_directories(profile_id)
    storage = EventStorage(dirs["runtime"])
    storage.save_state(
        RuntimeStateRecord(
            profile_id=profile_id,
            runtime_instance_id="inst_old",  # older instance
            config_version=1,
            state="stopped",
            exit_code=0,
            exit_reason="normal",
            browser_pid=999999,
        )
    )
    (dirs["runtime"] / "runner_info.json").write_text(
        json.dumps(
            {
                "profile_id": profile_id,
                "runtime_instance_id": "inst_old",
                "config_version": 1,
                "browser_pid": 999999,
                "cdp_port": 9222,
                "runner_pid": 100,
            }
        ),
        encoding="utf-8",
    )

    agent_app = create_agent_app(
        run_dir=dirs["runtime"], default_download_dir=dirs["exchange"]
    )
    server_transport = httpx.ASGITransport(app=agent_app)

    api_client = AsyncMock(spec=httpx.AsyncClient)
    core = SupervisorCore(
        docker_adapter=docker,
        port_allocator=PortAllocator(),
        event_forwarder=MagicMock(spec=EventForwarder),
        api_client=api_client,
    )

    async def _mock_query(pid: str) -> HealthResponse | None:
        async with httpx.AsyncClient(
            transport=server_transport, base_url="http://uds"
        ) as c:
            r = await c.get("/health")
            if r.status_code == 200:
                return HealthResponse.model_validate(r.json())
            return None

    core._query_agent_health = _mock_query

    # Query with expected instance 'inst_new'
    obs = await core._reconcile_instance_observation(
        profile_id, "inst_new", 1, container_status="running"
    )
    assert obs is None
    api_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_supervisor_reconcile_container_dead_reports_error(
    tmp_path: Path,
) -> None:
    """Docker container dead/exited reports error (reason='container_exit')."""
    data_root = tmp_path / "data"
    docker = _FakeDockerAdapter(data_root)
    profile_id = "prof_dead"
    instance_id = "inst_dead"

    api_client = AsyncMock(spec=httpx.AsyncClient)
    api_client.post = AsyncMock(return_value=MagicMock(status_code=200))
    core = SupervisorCore(
        docker_adapter=docker,
        port_allocator=PortAllocator(),
        event_forwarder=MagicMock(spec=EventForwarder),
        api_client=api_client,
    )

    obs = await core._reconcile_instance_observation(
        profile_id, instance_id, 1, container_status="exited"
    )
    assert obs == "error"
    api_client.post.assert_called_once()
    assert api_client.post.call_args.kwargs["json"]["observed_state"] == "error"
    assert api_client.post.call_args.kwargs["json"]["reason"] == "container_exit"


@pytest.mark.asyncio
async def test_supervisor_reconcile_container_instance_mismatch_rejected(
    tmp_path: Path,
) -> None:
    """Container label instance mismatch must return None, NOT report
    container error.
    """
    data_root = tmp_path / "data"
    docker = _FakeDockerAdapter(data_root)
    profile_id = "prof_mismatch"
    instance_old = "inst_old_journal"
    instance_new = "inst_new_healthy"

    # Docker has a new healthy instance container
    b_c = _FakeContainer(instance_new, "running", 1)
    docker.containers.set(docker.get_browser_container_name(profile_id), b_c)

    api_client = AsyncMock(spec=httpx.AsyncClient)
    core = SupervisorCore(
        docker_adapter=docker,
        port_allocator=PortAllocator(),
        event_forwarder=MagicMock(spec=EventForwarder),
        api_client=api_client,
    )

    # Calling with old instance must NOT report error on the container!
    obs = await core._reconcile_instance_observation(
        profile_id, instance_old, 1, container_status=None
    )
    assert obs is None
    api_client.post.assert_not_called()



@pytest.mark.asyncio
async def test_report_terminal_unacknowledged_does_not_dedup_or_modify_desired(
    tmp_path: Path,
) -> None:
    """When API delivery fails (offline / non-200), do not dedup or set
    desired to stopped.
    """
    data_root = tmp_path / "data"
    docker = _FakeDockerAdapter(data_root)
    profile_id = "prof_offline"
    instance_id = "inst_offline_1"
    config_version = 1

    api_client = AsyncMock(spec=httpx.AsyncClient)
    # Simulate API offline: post raises ConnectError
    api_client.post = AsyncMock(side_effect=httpx.ConnectError("API offline"))

    core = SupervisorCore(
        docker_adapter=docker,
        port_allocator=PortAllocator(),
        event_forwarder=MagicMock(spec=EventForwarder),
        api_client=api_client,
    )
    core._sessions[profile_id] = ActiveSession(
        profile_id=profile_id,
        runtime_instance_id=instance_id,
        config_version=config_version,
        udp_mux_port=30001,
        browser_container_id="b_1",
        stream_container_id="s_1",
        desired_state="running",
        observed_state="running",
    )

    # First attempt: fails because API is offline
    delivered = await core.report_terminal_observation(
        profile_id,
        instance_id,
        config_version,
        observed_state="stopped",
        reason="normal_exit",
    )
    assert delivered is False
    # Must NOT have changed desired_state
    assert core.get_session(profile_id).desired_state == "running"
    # Must NOT have acknowledged the terminal observation
    assert not core.terminal_observation_acknowledged(profile_id, instance_id, config_version)

    # Second attempt: API is back online (returns 200)
    api_client.post = AsyncMock(return_value=MagicMock(status_code=200))
    delivered2 = await core.report_terminal_observation(
        profile_id,
        instance_id,
        config_version,
        observed_state="stopped",
        reason="normal_exit",
    )
    assert delivered2 is True
    assert core.get_session(profile_id).desired_state == "stopped"
    assert core.get_session(profile_id).observed_state == "stopped"
    assert core.terminal_observation_acknowledged(profile_id, instance_id, config_version)

    # Third attempt: already ACKed, deduplication returns False
    api_client.post.reset_mock()
    assert (
        await core.report_terminal_observation(
            profile_id,
            instance_id,
            config_version,
            observed_state="stopped",
            reason="normal_exit",
        )
        is False
    )
    api_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_agent_health_owner_loss_with_live_process_still_reports_error(
    tmp_path: Path,
) -> None:
    """Owner-loss must not penetrate to running even if orphan Chrome process
    is alive.
    """
    run_dir = tmp_path / "runtime"
    run_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir = tmp_path / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    live_proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(30)"
    )
    try:
        storage = EventStorage(run_dir)
        storage.save_state(
            RuntimeStateRecord(
                profile_id="prof_loss_alive",
                runtime_instance_id="inst_loss_alive",
                config_version=1,
                state="error",
                exit_code=0,
                exit_reason="process_observation_lost",
                browser_pid=live_proc.pid,
            )
        )
        runner_info = {
            "profile_id": "prof_loss_alive",
            "runtime_instance_id": "inst_loss_alive",
            "config_version": 1,
            "browser_pid": live_proc.pid,
            "cdp_port": 9222,
            "runner_pid": 100,
        }
        (run_dir / "runner_info.json").write_text(
            json.dumps(runner_info), encoding="utf-8"
        )

        app = create_agent_app(run_dir=run_dir, default_download_dir=downloads_dir)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://uds"
        ) as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            # Must strictly preserve error details, never penetrated to running!
            assert data["details"]["state"] == "error"
            assert data["details"]["exit_reason"] == "process_observation_lost"

        # Verify Supervisor _reconcile_instance_observation receives error
        docker = _FakeDockerAdapter(tmp_path / "data")
        api_client = AsyncMock(spec=httpx.AsyncClient)
        api_client.post = AsyncMock(return_value=MagicMock(status_code=200))
        core = SupervisorCore(
            docker_adapter=docker,
            port_allocator=PortAllocator(),
            event_forwarder=MagicMock(spec=EventForwarder),
            api_client=api_client,
        )

        async def _mock_query(pid: str) -> HealthResponse | None:
            return HealthResponse.model_validate(data)

        core._query_agent_health = _mock_query
        obs = await core._reconcile_instance_observation(
            "prof_loss_alive", "inst_loss_alive", 1, container_status="running"
        )
        assert obs == "error"
        api_client.post.assert_called_once()
        assert api_client.post.call_args.kwargs["json"]["observed_state"] == "error"
        assert api_client.post.call_args.kwargs["json"]["reason"] == "process_lost"
    finally:
        live_proc.terminate()
        await live_proc.wait()


@pytest.mark.asyncio
async def test_agent_health_owner_loss_with_responsive_cdp_still_reports_error(
    tmp_path: Path,
) -> None:
    """Owner-loss must not penetrate to running even if CDP port is responsive."""
    run_dir = tmp_path / "runtime"
    run_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir = tmp_path / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    cdp_server = http.server.HTTPServer(("127.0.0.1", 0), _CDPVersionHandler)
    cdp_port = cdp_server.server_address[1]
    cdp_thread = threading.Thread(target=cdp_server.serve_forever, daemon=True)
    cdp_thread.start()

    try:
        storage = EventStorage(run_dir)
        dead_pid = 999999
        storage.save_state(
            RuntimeStateRecord(
                profile_id="prof_loss_cdp",
                runtime_instance_id="inst_loss_cdp",
                config_version=1,
                state="error",
                exit_code=0,
                exit_reason="process_observation_lost",
                browser_pid=dead_pid,
            )
        )
        runner_info = {
            "profile_id": "prof_loss_cdp",
            "runtime_instance_id": "inst_loss_cdp",
            "config_version": 1,
            "browser_pid": dead_pid,
            "cdp_port": cdp_port,
            "runner_pid": 100,
        }
        (run_dir / "runner_info.json").write_text(
            json.dumps(runner_info), encoding="utf-8"
        )

        app = create_agent_app(run_dir=run_dir, default_download_dir=downloads_dir)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://uds"
        ) as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["details"]["state"] == "error"
            assert data["details"]["exit_reason"] == "process_observation_lost"

        docker = _FakeDockerAdapter(tmp_path / "data")
        api_client = AsyncMock(spec=httpx.AsyncClient)
        api_client.post = AsyncMock(return_value=MagicMock(status_code=200))
        core = SupervisorCore(
            docker_adapter=docker,
            port_allocator=PortAllocator(),
            event_forwarder=MagicMock(spec=EventForwarder),
            api_client=api_client,
        )

        async def _mock_query(pid: str) -> HealthResponse | None:
            return HealthResponse.model_validate(data)

        core._query_agent_health = _mock_query
        obs = await core._reconcile_instance_observation(
            "prof_loss_cdp", "inst_loss_cdp", 1, container_status="running"
        )
        assert obs == "error"
        api_client.post.assert_called_once()
        assert api_client.post.call_args.kwargs["json"]["observed_state"] == "error"
        assert api_client.post.call_args.kwargs["json"]["reason"] == "process_lost"
    finally:
        cdp_server.shutdown()
        cdp_server.server_close()


@pytest.mark.asyncio
async def test_agent_health_config_version_mismatch_raises_storage_error() -> None:
    """When runner_info version (1) conflicts with state.json version (2),

    /health must reject with 503 StorageError and not masquerade as version 1.
    """
    import shutil
    import tempfile

    data_root = (
        Path(tempfile.mkdtemp(prefix="cbrowser-normal-exit-", dir="/tmp"))
    ).resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    docker = _FakeDockerAdapter(data_root)
    profile_id = "prof_ver_mismatch"
    instance_id = "inst_ver_mismatch"

    dirs = docker.prepare_profile_directories(profile_id)
    storage = EventStorage(dirs["runtime"])
    dead_pid = 999999
    # state.json has config_version = 2
    storage.save_state(
        RuntimeStateRecord(
            profile_id=profile_id,
            runtime_instance_id=instance_id,
            config_version=2,
            state="stopped",
            exit_code=0,
            exit_reason="normal",
            browser_pid=dead_pid,
        )
    )
    # runner_info.json has config_version = 1
    (dirs["runtime"] / "runner_info.json").write_text(
        json.dumps(
            {
                "profile_id": profile_id,
                "runtime_instance_id": instance_id,
                "config_version": 1,
                "browser_pid": dead_pid,
                "cdp_port": 9222,
                "runner_pid": 100,
            }
        ),
        encoding="utf-8",
    )

    try:
        app = create_agent_app(
            run_dir=dirs["runtime"], default_download_dir=dirs["exchange"]
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://uds"
        ) as client:
            resp = await client.get("/health")
            # Must reject with 503 (StorageError) due to version conflict!
            assert resp.status_code == 503

        # Verify Supervisor rejects observation and does not clear intent
        api_client = AsyncMock(spec=httpx.AsyncClient)
        core = SupervisorCore(
            docker_adapter=docker,
            port_allocator=PortAllocator(),
            event_forwarder=MagicMock(spec=EventForwarder),
            api_client=api_client,
        )

        async def _mock_query(pid: str) -> HealthResponse | None:
            # Querying health on mismatched state yields 503 / None
            return None

        core._query_agent_health = _mock_query
        obs = await core._reconcile_instance_observation(
            profile_id, instance_id, 1, container_status="running"
        )
        assert obs is None
        api_client.post.assert_not_called()
    finally:
        shutil.rmtree(data_root)


@pytest.mark.asyncio
async def test_agent_health_missing_state_does_not_manufacture_stopped() -> None:
    """When native state.json is missing, exit diagnostic event must not

    manufacture stopped state when recover_terminal=False.
    """
    import shutil
    import tempfile

    data_root = (
        Path(tempfile.mkdtemp(prefix="cbrowser-normal-exit-", dir="/tmp"))
    ).resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    docker = _FakeDockerAdapter(data_root)
    profile_id = "prof_no_state"
    instance_id = "inst_no_state"

    dirs = docker.prepare_profile_directories(profile_id)
    storage = EventStorage(dirs["runtime"])
    dead_pid = 999999

    # Save only diagnostic exit event, but NO state.json record!
    storage.save_runtime_event(
        RuntimeEventRecord(
            event_id="diag_exit_01",
            profile_id=profile_id,
            runtime_instance_id=instance_id,
            config_version=1,
            event_type="exit",
            exit_code=0,
            exit_reason="normal",
        )
    )
    # Ensure state.json is removed if any was created
    (dirs["runtime"] / "instances" / instance_id / "state.json").unlink(
        missing_ok=True
    )
    (dirs["runtime"] / "state.json").unlink(missing_ok=True)

    # runner_info with dead PID and dead CDP
    (dirs["runtime"] / "runner_info.json").write_text(
        json.dumps(
            {
                "profile_id": profile_id,
                "runtime_instance_id": instance_id,
                "config_version": 1,
                "browser_pid": dead_pid,
                "cdp_port": 9222,
                "runner_pid": 100,
            }
        ),
        encoding="utf-8",
    )

    try:
        app = create_agent_app(
            run_dir=dirs["runtime"], default_download_dir=dirs["exchange"]
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://uds"
        ) as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            # Diagnostic exit event must NOT manufacture a stopped state!
            assert data["details"].get("state") != "stopped"

        # Supervisor must not report stopped
        api_client = AsyncMock(spec=httpx.AsyncClient)
        core = SupervisorCore(
            docker_adapter=docker,
            port_allocator=PortAllocator(),
            event_forwarder=MagicMock(spec=EventForwarder),
            api_client=api_client,
        )

        async def _mock_query(pid: str) -> HealthResponse | None:
            return HealthResponse.model_validate(data)

        core._query_agent_health = _mock_query
        obs = await core._reconcile_instance_observation(
            profile_id, instance_id, 1, container_status="running"
        )
        assert obs != "stopped"
        api_client.post.assert_not_called()
    finally:
        shutil.rmtree(data_root)


@pytest.mark.asyncio
async def test_normal_exit_session_allows_immediate_start_without_409_conflict(
    tmp_path: Path,
) -> None:
    """When a cleanly stopped normal-exit session still sits in _sessions awaiting
    scan cleanup, starting a new running intent tears down the old stopped sandbox
    instead of failing with LifecycleConflictError (409).
    """
    data_root = tmp_path / "data"
    validator = PathValidator(data_root)
    for sub in (
        "profiles/p1/profile",
        "profiles/p1/preview",
        "runtime/p1/x11",
        "runtime/p1/pulse",
        "runtime-events/p1",
        "artifacts/p1/downloads",
        "artifacts/p1/uploads",
    ):
        (data_root / sub).mkdir(parents=True, exist_ok=True)
    dirs = {
        "profile": data_root / "profiles/p1/profile",
        "preview": data_root / "profiles/p1/preview",
        "runtime": data_root / "runtime/p1",
        "events": data_root / "runtime-events/p1",
        "exchange": data_root / "artifacts/p1/downloads",
        "uploads": data_root / "artifacts/p1/uploads",
        "x11": data_root / "runtime/p1/x11",
        "pulse": data_root / "runtime/p1/pulse",
    }
    torn_down: list[str] = []
    active_containers = True

    async def _teardown(pid: str) -> None:
        nonlocal active_containers
        torn_down.append(pid)
        active_containers = False

    async def _start_browser(**_kw):
        return MagicMock(id="b-new", name="cbrowser-0001-browser")

    async def _start_stream(**_kw):
        s = MagicMock(id="s-new", status="running")
        s.reload = lambda: None
        return s

    docker = MagicMock()
    docker.validator = validator
    docker.manage_ownership = False
    docker.prepare_profile_directories = lambda _pid: dirs
    docker.teardown_profile = AsyncMock(side_effect=_teardown)
    docker.scan_active_containers = lambda: (
        [{"profile_id": "p1", "role": "browser", "instance_id": "inst_old"}]
        if active_containers
        else []
    )
    docker.create_profile_network = AsyncMock()
    docker.attach_profile_infrastructure = lambda *_a, **_kw: {
        "gateway_ip": "10.0.0.1",
        "gateway_url": "ws://gateway:18080",
    }
    docker.start_browser_container = AsyncMock(side_effect=_start_browser)
    docker.start_stream_container = AsyncMock(side_effect=_start_stream)

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/runtime"):
            return httpx.Response(
                200,
                json={
                    "desired_state": "running",
                    "observed_state": "stopped",
                    "runtime_instance_id": None,
                    "restart_blocked": False,
                },
            )
        return httpx.Response(200, json={})

    api = httpx.AsyncClient(transport=httpx.MockTransport(_handler), base_url="http://api")
    key_file = tmp_path / "agent_key"
    key_file.write_text("agent-master-key-" + "x" * 32, encoding="utf-8")
    key_file.chmod(0o600)
    gw = MagicMock()
    gw.disconnect_viewers = AsyncMock()
    gw.has_foreground_viewers = AsyncMock(return_value=False)

    ports = PortAllocator()
    old_port = await ports.allocate("p1")
    core = SupervisorCore(
        docker_adapter=docker,
        port_allocator=ports,
        event_forwarder=MagicMock(spec=EventForwarder),
        api_client=api,
        agent_key_file=key_file,
        gateway_control=gw,
    )
    core._resolve_gateway_id = lambda: "gw-1"  # type: ignore[method-assign]
    core._sessions["p1"] = ActiveSession(
        profile_id="p1",
        runtime_instance_id="inst_old",
        config_version=1,
        udp_mux_port=old_port,
        browser_container_id="b-old",
        stream_container_id="s-old",
        desired_state="stopped",
        observed_state="stopped",
    )
    from cbrowser.domain.models import ProfileConfig
    import cbrowser.supervisor.core as sup_core

    orig_ready = sup_core.browser_runtime_ready
    sup_core.browser_runtime_ready = lambda *_a, **_kw: True
    try:
        new_session = await core.start_profile("p1", ProfileConfig(name="p1"), 1, profile_number=1)
        assert torn_down == ["p1"]
        assert new_session.runtime_instance_id != "inst_old"
        assert new_session.observed_state == "running"
    finally:
        sup_core.browser_runtime_ready = orig_ready
        await api.aclose()


@pytest.mark.asyncio
async def test_scan_cleans_up_normal_exit_residual_when_desired_running_and_api_unbound(
    tmp_path: Path,
) -> None:
    """When API already moved to desired=running, api_inst=None, a residual stopped
    normal-exit container must be cleaned up by scan instead of logging fence mismatch forever."""
    data_root = tmp_path / "data"
    validator = PathValidator(data_root)
    active = True

    async def _teardown(_pid: str) -> None:
        nonlocal active
        active = False

    docker = MagicMock()
    docker.validator = validator
    docker.teardown_profile = AsyncMock(side_effect=_teardown)
    docker.scan_active_containers = lambda: (
        [
            {
                "profile_id": "p1",
                "role": "browser",
                "instance_id": "inst_old",
                "status": "running",
                "id": "b-old",
                "config_version": 1,
                "policy_ready": True,
            },
            {
                "profile_id": "p1",
                "role": "stream",
                "instance_id": "inst_old",
                "status": "running",
                "id": "s-old",
                "config_version": 1,
                "policy_ready": True,
            },
        ]
        if active
        else []
    )

    api = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _r: httpx.Response(
                200,
                json={
                    "desired_state": "running",
                    "observed_state": "stopped",
                    "runtime_instance_id": None,
                    "config_version": 1,
                },
            )
        ),
        base_url="http://api",
    )
    gw = MagicMock()
    gw.disconnect_viewers = AsyncMock()
    ports = PortAllocator()
    port = await ports.allocate("p1")
    core = SupervisorCore(
        docker_adapter=docker,
        port_allocator=ports,
        event_forwarder=MagicMock(spec=EventForwarder),
        api_client=api,
        gateway_control=gw,
    )
    core._sessions["p1"] = ActiveSession(
        profile_id="p1",
        runtime_instance_id="inst_old",
        config_version=1,
        udp_mux_port=port,
        browser_container_id="b-old",
        stream_container_id="s-old",
        desired_state="stopped",
        observed_state="stopped",
    )
    try:
        await core.scan_and_reconcile_existing()
        assert docker.teardown_profile.called
        assert core.get_session("p1") is None
        assert "p1" not in ports._allocated
    finally:
        await api.aclose()


@pytest.mark.asyncio
async def test_classify_abnormal_exits_skips_uds_poll_once_terminal_acknowledged(
    tmp_path: Path,
) -> None:
    """Once terminal observation is acknowledged, recovery must not re-poll Agent UDS every second."""
    from cbrowser.supervisor.recovery_coordinator import RecoveryCoordinator

    core = SupervisorCore(
        docker_adapter=MagicMock(validator=PathValidator(tmp_path / "data")),
        port_allocator=PortAllocator(),
        event_forwarder=MagicMock(spec=EventForwarder),
        api_client=AsyncMock(spec=httpx.AsyncClient),
    )
    core._terminal_observations.add(("p1", "inst_1", 1))
    reconcile_mock = AsyncMock(return_value=None)
    core._reconcile_instance_observation = reconcile_mock  # type: ignore[method-assign]

    recovery = RecoveryCoordinator(core)
    docker_by_profile = {
        "p1": {
            "browser": {
                "profile_id": "p1",
                "role": "browser",
                "instance_id": "inst_1",
                "status": "running",
                "id": "b1",
                "config_version": 1,
            }
        }
    }
    await recovery._classify_abnormal_exits(docker_by_profile)
    reconcile_mock.assert_not_called()
    assert "inst_1" in recovery._reported_dead_instances


@pytest.mark.asyncio
async def test_report_terminal_stopped_requests_scan_wakeup(tmp_path: Path) -> None:
    api_client = AsyncMock(spec=httpx.AsyncClient)
    api_client.post = AsyncMock(return_value=MagicMock(status_code=200))
    core = SupervisorCore(
        docker_adapter=MagicMock(validator=PathValidator(tmp_path / "data")),
        port_allocator=PortAllocator(),
        event_forwarder=MagicMock(spec=EventForwarder),
        api_client=api_client,
    )
    assert core.pop_scan_requested() is False
    ok = await core.report_terminal_observation(
        "p1", "inst_1", 1, observed_state="stopped", reason="normal_exit"
    )
    assert ok is True
    assert core.pop_scan_requested() is True
    assert core.pop_scan_requested() is False
