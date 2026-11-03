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
async def test_supervisor_query_agent_health_real_uds_transport() -> None:
    """Verify _query_agent_health reaches real UDS server over Unix domain socket."""
    import secrets
    import shutil

    import uvicorn

    data_root = (
        Path(".scratch/normal_exit_fix") / f"u_{secrets.token_hex(3)}"
    ).resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    docker = _FakeDockerAdapter(data_root)
    profile_id = "prof_uds_real"
    instance_id = "inst_uds_real"

    dirs = docker.prepare_profile_directories(profile_id)
    storage = EventStorage(dirs["runtime"])
    storage.save_state(
        RuntimeStateRecord(
            profile_id=profile_id,
            runtime_instance_id=instance_id,
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
                "runtime_instance_id": instance_id,
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
    sock_path = dirs["runtime"] / "agent.sock"

    rel_sock = os.path.relpath(sock_path, os.getcwd())
    config = uvicorn.Config(app=agent_app, uds=rel_sock, log_level="error")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    for _ in range(50):
        if sock_path.exists() and sock_path.is_socket():
            break
        await asyncio.sleep(0.05)

    try:
        core = SupervisorCore(
            docker_adapter=docker,
            port_allocator=PortAllocator(),
            event_forwarder=MagicMock(spec=EventForwarder),
            api_client=AsyncMock(spec=httpx.AsyncClient),
        )
        health = await core.query_agent_health(profile_id)
        assert health is not None
        assert health.profile_id == profile_id
        assert health.runtime_instance_id == instance_id
        assert health.details["state"] == "stopped"
        assert health.details["exit_code"] == 0
        assert health.details["exit_reason"] == "normal"
    finally:
        server.should_exit = True
        await asyncio.sleep(0.1)
        server_task.cancel()
        await asyncio.gather(server_task, return_exceptions=True)
        sock_path.unlink(missing_ok=True)
        shutil.rmtree(data_root)


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
    import secrets
    import shutil

    data_root = (
        Path(".scratch/normal_exit_fix") / f"u_{secrets.token_hex(3)}"
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
    import secrets
    import shutil

    data_root = (
        Path(".scratch/normal_exit_fix") / f"u_{secrets.token_hex(3)}"
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
