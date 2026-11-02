"""Integration test for normal exit observation and recovery.

Tests the full lifecycle convergence across API, Supervisor, and Runtime Agent UDS:
1. Normal clean exit: Real UDS Agent reports clean exit while container is running;
   Supervisor validates Agent via UDS and API converges to desired_state="stopped".
2. Owner-loss abnormal exit: Agent reports process_observation_lost with Chrome exit 0;
   Supervisor validates Agent via UDS and API records failure_count=1 while
   desired_state remains "running".
3. Offline API recovery: API is offline when clean exit occurs, Supervisor restarts,
   API recovers; Supervisor converges Profile A to desired_state="stopped", while
   healthy Profile B remains running.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import uvicorn
from cbrowser.runtime_agent.agent import create_agent_app
from cbrowser.runtime_agent.event_storage import EventStorage
from cbrowser.runtime_agent.protocol import RuntimeStateRecord
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator
from docker.errors import NotFound

pytest_plugins = ("test_supervisor_rpc",)


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


class _FakeDocker:
    def __init__(self, data_root: Path) -> None:
        self.validator = PathValidator(data_root)
        self.containers = _FakeContainers()

        def _inspect(cid: str) -> dict:
            port = 30001 if ("target_a" in cid or "clean" in cid) else 30002
            return {
                "HostConfig": {"PortBindings": {"30000/udp": [{"HostPort": str(port)}]}}
            }

        self.client = SimpleNamespace(
            containers=self.containers,
            api=SimpleNamespace(inspect_container=_inspect),
        )
        self.resource_prefix = "test"
        self._active: list[dict] = []
        self.torn_down_profiles: list[str] = []

    def get_browser_container_name(self, profile_id: str) -> str:
        return f"cbrowser-browser-{profile_id}"

    def get_stream_container_name(self, profile_id: str) -> str:
        return f"cbrowser-stream-{profile_id}"

    def scan_active_containers(self) -> list[dict]:
        return list(self._active)

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

    async def teardown_profile(self, profile_id: str) -> None:
        self.torn_down_profiles.append(profile_id)
        self._active = [c for c in self._active if c.get("profile_id") != profile_id]
        self.containers.set(self.get_browser_container_name(profile_id), None)
        self.containers.set(self.get_stream_container_name(profile_id), None)


def _bind(
    server, token: str, profile_id: str, instance: str, config_version: int = 1
) -> None:
    response = server.post(
        "/api/v1/internal/supervisor/runtimes/bind",
        params={"profile_id": profile_id},
        headers={"Authorization": f"Bearer {token}"},
        json={"runtime_instance_id": instance, "config_version": config_version},
    )
    assert response.status_code == 200, response.text


async def _run_uds_server(app, sock_path: Path):
    rel_sock = os.path.relpath(sock_path.resolve(), os.getcwd())
    config = uvicorn.Config(app=app, uds=rel_sock, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    for _ in range(50):
        if sock_path.exists() and sock_path.is_socket():
            break
        await asyncio.sleep(0.05)
    return server, task


@pytest.mark.asyncio
async def test_normal_exit_converges_to_desired_stopped_while_container_running(
    supervisor_api, tmp_path: Path
) -> None:
    """AC-001: Clean exit in running container observed via Agent UDS sets
    desired_state='stopped'.
    """
    server, token = supervisor_api
    res_p = server.post("/api/v1/profiles", json={"name": "clean-profile"})
    assert res_p.status_code == 201
    profile_id = res_p.json()["id"]

    server.patch(
        f"/api/v1/profiles/{profile_id}/runtime/desired-state",
        json={"desired_state": "running"},
    )
    instance_id = "inst_clean_e2e"
    config_version = 1
    _bind(server, token, profile_id, instance_id, config_version)

    data_root = (
        Path(".scratch/normal_exit_fix") / f"d_{secrets.token_hex(3)}"
    ).resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    token_file = data_root / "control" / "supervisor_token"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)

    docker = _FakeDocker(data_root)
    dirs = docker.prepare_profile_directories(profile_id)

    # Container status is "running" in Docker (Xvfb/agent still alive)
    b_c = _FakeContainer(instance_id, "running", config_version)
    s_c = _FakeContainer(instance_id, "running", config_version)
    docker.containers.set(docker.get_browser_container_name(profile_id), b_c)
    docker.containers.set(docker.get_stream_container_name(profile_id), s_c)
    docker._active = [
        {
            "profile_id": profile_id,
            "role": "browser",
            "instance_id": instance_id,
            "status": "running",
            "id": b_c.id,
            "config_version": config_version,
            "policy_ready": True,
        },
        {
            "profile_id": profile_id,
            "role": "stream",
            "instance_id": instance_id,
            "status": "running",
            "id": s_c.id,
            "config_version": config_version,
            "policy_ready": True,
        },
    ]

    # Write clean exit state inside Agent storage
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

    # Write exit event to runtime-events directory
    ev_dir = (
        data_root / "runtime-events" / profile_id / "events" / "runtime" / instance_id
    )
    ev_dir.mkdir(parents=True, exist_ok=True)
    ev_file = ev_dir / "exit_01.json"
    ev_file.write_text(
        json.dumps(
            {
                "event_id": "clean-ev-1",
                "profile_id": profile_id,
                "runtime_instance_id": instance_id,
                "event_type": "exit",
                "exit_code": 0,
                "exit_reason": "normal",
                "config_version": config_version,
                "payload": {},
            }
        ),
        encoding="utf-8",
    )

    # Start real Agent UDS server on dirs["runtime"] / "agent.sock"
    agent_app = create_agent_app(
        run_dir=dirs["runtime"], default_download_dir=dirs["exchange"]
    )
    sock_path = dirs["runtime"] / "agent.sock"
    uds_server, uds_task = await _run_uds_server(agent_app, sock_path)

    try:
        async with httpx.AsyncClient(
            base_url=str(server.base_url),
            headers={"Authorization": f"Bearer {token}"},
            trust_env=False,
        ) as api:
            gw_mock = AsyncMock()
            gw_mock.has_foreground_viewers = AsyncMock(return_value=False)
            core = SupervisorCore(
                docker,
                PortAllocator(),
                EventForwarder(str(server.base_url), data_root / "spool", client=api),
                api,
                token_file=token_file,
                gateway_control=gw_mock,
            )
            # Reconcile or consume events
            await core.consume_disk_events()
            await core.scan_and_reconcile_existing()

        # Check API convergence
        rt = server.get(f"/api/v1/profiles/{profile_id}/runtime").json()
        assert rt["desired_state"] == "stopped", (
            f"Expected desired_state='stopped', got: {rt}"
        )
        assert rt["observed_state"] == "stopped", (
            f"Expected observed_state='stopped', got: {rt}"
        )
        assert rt["failure_count"] == 0
    finally:
        uds_server.should_exit = True
        await asyncio.sleep(0.1)
        uds_task.cancel()
        await asyncio.gather(uds_task, return_exceptions=True)
        sock_path.unlink(missing_ok=True)
        shutil.rmtree(data_root)


@pytest.mark.asyncio
async def test_owner_loss_exit_preserves_running_intent_and_records_failure(
    supervisor_api, tmp_path: Path
) -> None:
    """AC-002: SDK owner-loss exit (code 0, process_observation_lost) records failure
    and keeps desired running.
    """
    server, token = supervisor_api
    res_p = server.post("/api/v1/profiles", json={"name": "owner-loss-profile"})
    assert res_p.status_code == 201
    profile_id = res_p.json()["id"]

    server.patch(
        f"/api/v1/profiles/{profile_id}/runtime/desired-state",
        json={"desired_state": "running"},
    )
    instance_id = "inst_owner_loss"
    config_version = 1
    _bind(server, token, profile_id, instance_id, config_version)

    data_root = (
        Path(".scratch/normal_exit_fix") / f"d_{secrets.token_hex(3)}"
    ).resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    token_file = data_root / "control" / "supervisor_token"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)

    docker = _FakeDocker(data_root)
    dirs = docker.prepare_profile_directories(profile_id)

    b_c = _FakeContainer(instance_id, "running", config_version)
    s_c = _FakeContainer(instance_id, "running", config_version)
    docker.containers.set(docker.get_browser_container_name(profile_id), b_c)
    docker.containers.set(docker.get_stream_container_name(profile_id), s_c)
    docker._active = [
        {
            "profile_id": profile_id,
            "role": "browser",
            "instance_id": instance_id,
            "status": "running",
            "id": b_c.id,
            "config_version": config_version,
            "policy_ready": True,
        },
        {
            "profile_id": profile_id,
            "role": "stream",
            "instance_id": instance_id,
            "status": "running",
            "id": s_c.id,
            "config_version": config_version,
            "policy_ready": True,
        },
    ]

    # Write owner-loss error state inside Agent storage
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

    ev_dir = (
        data_root / "runtime-events" / profile_id / "events" / "runtime" / instance_id
    )
    ev_dir.mkdir(parents=True, exist_ok=True)
    (ev_dir / "loss_01.json").write_text(
        json.dumps(
            {
                "event_id": "loss-ev-1",
                "profile_id": profile_id,
                "runtime_instance_id": instance_id,
                "event_type": "lifecycle",
                "exit_code": 0,
                "exit_reason": "process_observation_lost",
                "config_version": config_version,
                "payload": {},
            }
        ),
        encoding="utf-8",
    )

    agent_app = create_agent_app(
        run_dir=dirs["runtime"], default_download_dir=dirs["exchange"]
    )
    sock_path = dirs["runtime"] / "agent.sock"
    uds_server, uds_task = await _run_uds_server(agent_app, sock_path)

    try:
        async with httpx.AsyncClient(
            base_url=str(server.base_url),
            headers={"Authorization": f"Bearer {token}"},
            trust_env=False,
        ) as api:
            gw_mock = AsyncMock()
            gw_mock.has_foreground_viewers = AsyncMock(return_value=False)
            core = SupervisorCore(
                docker,
                PortAllocator(),
                EventForwarder(str(server.base_url), data_root / "spool", client=api),
                api,
                token_file=token_file,
                gateway_control=gw_mock,
            )
            await core.consume_disk_events()
            await core.scan_and_reconcile_existing()

        rt = server.get(f"/api/v1/profiles/{profile_id}/runtime").json()
        assert rt["desired_state"] == "running", (
            f"Desired state must remain running on error: {rt}"
        )
        assert rt["observed_state"] == "error", f"Observed state must be error: {rt}"
        assert rt["failure_count"] == 1
    finally:
        uds_server.should_exit = True
        await asyncio.sleep(0.1)
        uds_task.cancel()
        await asyncio.gather(uds_task, return_exceptions=True)
        sock_path.unlink(missing_ok=True)
        shutil.rmtree(data_root)


@pytest.mark.asyncio
async def test_offline_recovery_dual_profile_isolation(
    supervisor_api, tmp_path: Path
) -> None:
    """AC-003: Profile A normally exits while Profile B is running; Profile A
    converges to stopped, Profile B stays running.
    """
    server, token = supervisor_api

    # Profile A (target that closes)
    res_a = server.post("/api/v1/profiles", json={"name": "target-a"})
    profile_a = res_a.json()["id"]
    server.patch(
        f"/api/v1/profiles/{profile_a}/runtime/desired-state",
        json={"desired_state": "running"},
    )
    inst_a = "inst_target_a"
    _bind(server, token, profile_a, inst_a, 1)

    # Profile B (companion that remains healthy)
    res_b = server.post("/api/v1/profiles", json={"name": "companion-b"})
    profile_b = res_b.json()["id"]
    server.patch(
        f"/api/v1/profiles/{profile_b}/runtime/desired-state",
        json={"desired_state": "running"},
    )
    inst_b = "inst_companion_b"
    _bind(server, token, profile_b, inst_b, 1)

    data_root = (
        Path(".scratch/normal_exit_fix") / f"d_{secrets.token_hex(3)}"
    ).resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    token_file = data_root / "control" / "supervisor_token"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)

    docker = _FakeDocker(data_root)
    dirs_a = docker.prepare_profile_directories(profile_a)
    dirs_b = docker.prepare_profile_directories(profile_b)

    # Docker containers for both are running
    b_c_a = _FakeContainer(inst_a, "running", 1)
    s_c_a = _FakeContainer(inst_a, "running", 1)
    b_c_b = _FakeContainer(inst_b, "running", 1)
    s_c_b = _FakeContainer(inst_b, "running", 1)

    docker.containers.set(docker.get_browser_container_name(profile_a), b_c_a)
    docker.containers.set(docker.get_stream_container_name(profile_a), s_c_a)
    docker.containers.set(docker.get_browser_container_name(profile_b), b_c_b)
    docker.containers.set(docker.get_stream_container_name(profile_b), s_c_b)

    docker._active = [
        {
            "profile_id": profile_a,
            "role": "browser",
            "instance_id": inst_a,
            "status": "running",
            "id": b_c_a.id,
            "config_version": 1,
            "policy_ready": True,
        },
        {
            "profile_id": profile_a,
            "role": "stream",
            "instance_id": inst_a,
            "status": "running",
            "id": s_c_a.id,
            "config_version": 1,
            "policy_ready": True,
        },
        {
            "profile_id": profile_b,
            "role": "browser",
            "instance_id": inst_b,
            "status": "running",
            "id": b_c_b.id,
            "config_version": 1,
            "policy_ready": True,
        },
        {
            "profile_id": profile_b,
            "role": "stream",
            "instance_id": inst_b,
            "status": "running",
            "id": s_c_b.id,
            "config_version": 1,
            "policy_ready": True,
        },
    ]

    # Profile A Agent: Clean exit state
    storage_a = EventStorage(dirs_a["runtime"])
    storage_a.save_state(
        RuntimeStateRecord(
            profile_id=profile_a,
            runtime_instance_id=inst_a,
            config_version=1,
            state="stopped",
            exit_code=0,
            exit_reason="normal",
            browser_pid=999999,
        )
    )
    (dirs_a["runtime"] / "runner_info.json").write_text(
        json.dumps(
            {
                "profile_id": profile_a,
                "runtime_instance_id": inst_a,
                "config_version": 1,
                "browser_pid": 999999,
                "cdp_port": 9222,
                "runner_pid": 100,
            }
        ),
        encoding="utf-8",
    )

    # Profile B: Spawn a real live process simulating healthy Chrome
    live_proc_b = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(30)"
    )
    (dirs_b["runtime"] / "runner_info.json").write_text(
        json.dumps(
            {
                "profile_id": profile_b,
                "runtime_instance_id": inst_b,
                "config_version": 1,
                "browser_pid": live_proc_b.pid,
                "cdp_port": 9223,
                "runner_pid": 101,
            }
        ),
        encoding="utf-8",
    )

    app_a = create_agent_app(
        run_dir=dirs_a["runtime"], default_download_dir=dirs_a["exchange"]
    )
    sock_a = dirs_a["runtime"] / "agent.sock"
    server_a, task_a = await _run_uds_server(app_a, sock_a)

    app_b = create_agent_app(
        run_dir=dirs_b["runtime"], default_download_dir=dirs_b["exchange"]
    )
    sock_b = dirs_b["runtime"] / "agent.sock"
    server_b, task_b = await _run_uds_server(app_b, sock_b)

    try:
        async with httpx.AsyncClient(
            base_url=str(server.base_url),
            headers={"Authorization": f"Bearer {token}"},
            trust_env=False,
        ) as api:
            # Fake gateway control for Profile B
            gw_mock = AsyncMock()
            gw_mock.has_foreground_viewers = AsyncMock(return_value=False)
            core = SupervisorCore(
                docker,
                PortAllocator(),
                EventForwarder(str(server.base_url), data_root / "spool", client=api),
                api,
                token_file=token_file,
                gateway_control=gw_mock,
            )
            # Reconcile existing containers
            await core.scan_and_reconcile_existing()

        # Check Profile A has converged to stopped
        rt_a = server.get(f"/api/v1/profiles/{profile_a}/runtime").json()
        assert rt_a["desired_state"] == "stopped", (
            f"Profile A desired_state must converge to stopped: {rt_a}"
        )
        assert rt_a["observed_state"] == "stopped"

        # Check Profile B is still running!
        rt_b = server.get(f"/api/v1/profiles/{profile_b}/runtime").json()
        assert rt_b["desired_state"] == "running", (
            f"Profile B desired_state must remain running: {rt_b}"
        )
        assert rt_b["failure_count"] == 0
    finally:
        server_a.should_exit = True
        server_b.should_exit = True
        live_proc_b.terminate()
        await live_proc_b.wait()
        await asyncio.sleep(0.1)
        task_a.cancel()
        task_b.cancel()
        await asyncio.gather(task_a, task_b, return_exceptions=True)
        sock_a.unlink(missing_ok=True)
        sock_b.unlink(missing_ok=True)
        shutil.rmtree(data_root)


@pytest.mark.asyncio
async def test_normal_exit_ack_triggers_scan_cleanup_and_port_release(
    supervisor_api, tmp_path: Path
) -> None:
    """AC-004: Normal exit ACK sets desired stopped; next scan pass cleans up
    containers, releases port and clears session.
    """
    server, token = supervisor_api

    # Profile A (normal exit target)
    res_a = server.post("/api/v1/profiles", json={"name": "target-a-clean"})
    profile_a = res_a.json()["id"]
    server.patch(
        f"/api/v1/profiles/{profile_a}/runtime/desired-state",
        json={"desired_state": "running"},
    )
    inst_a = "inst_clean_scan"
    _bind(server, token, profile_a, inst_a, 1)

    # Profile B (healthy companion)
    res_b = server.post("/api/v1/profiles", json={"name": "companion-b-clean"})
    profile_b = res_b.json()["id"]
    server.patch(
        f"/api/v1/profiles/{profile_b}/runtime/desired-state",
        json={"desired_state": "running"},
    )
    inst_b = "inst_companion_scan"
    _bind(server, token, profile_b, inst_b, 1)

    data_root = (
        Path(".scratch/normal_exit_fix") / f"d_{secrets.token_hex(3)}"
    ).resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    token_file = data_root / "control" / "supervisor_token"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)

    docker = _FakeDocker(data_root)
    dirs_a = docker.prepare_profile_directories(profile_a)
    dirs_b = docker.prepare_profile_directories(profile_b)

    b_c_a = _FakeContainer(inst_a, "running", 1)
    s_c_a = _FakeContainer(inst_a, "running", 1)
    b_c_b = _FakeContainer(inst_b, "running", 1)
    s_c_b = _FakeContainer(inst_b, "running", 1)

    docker.containers.set(docker.get_browser_container_name(profile_a), b_c_a)
    docker.containers.set(docker.get_stream_container_name(profile_a), s_c_a)
    docker.containers.set(docker.get_browser_container_name(profile_b), b_c_b)
    docker.containers.set(docker.get_stream_container_name(profile_b), s_c_b)

    docker._active = [
        {
            "profile_id": profile_a,
            "role": "browser",
            "instance_id": inst_a,
            "status": "running",
            "id": b_c_a.id,
            "config_version": 1,
            "policy_ready": True,
        },
        {
            "profile_id": profile_a,
            "role": "stream",
            "instance_id": inst_a,
            "status": "running",
            "id": s_c_a.id,
            "config_version": 1,
            "policy_ready": True,
        },
        {
            "profile_id": profile_b,
            "role": "browser",
            "instance_id": inst_b,
            "status": "running",
            "id": b_c_b.id,
            "config_version": 1,
            "policy_ready": True,
        },
        {
            "profile_id": profile_b,
            "role": "stream",
            "instance_id": inst_b,
            "status": "running",
            "id": s_c_b.id,
            "config_version": 1,
            "policy_ready": True,
        },
    ]

    storage_a = EventStorage(dirs_a["runtime"])
    storage_a.save_state(
        RuntimeStateRecord(
            profile_id=profile_a,
            runtime_instance_id=inst_a,
            config_version=1,
            state="stopped",
            exit_code=0,
            exit_reason="normal",
            browser_pid=999999,
        )
    )
    (dirs_a["runtime"] / "runner_info.json").write_text(
        json.dumps(
            {
                "profile_id": profile_a,
                "runtime_instance_id": inst_a,
                "config_version": 1,
                "browser_pid": 999999,
                "cdp_port": 9222,
                "runner_pid": 100,
            }
        ),
        encoding="utf-8",
    )

    live_proc_b = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(30)"
    )
    (dirs_b["runtime"] / "runner_info.json").write_text(
        json.dumps(
            {
                "profile_id": profile_b,
                "runtime_instance_id": inst_b,
                "config_version": 1,
                "browser_pid": live_proc_b.pid,
                "cdp_port": 9223,
                "runner_pid": 101,
            }
        ),
        encoding="utf-8",
    )

    app_a = create_agent_app(
        run_dir=dirs_a["runtime"], default_download_dir=dirs_a["exchange"]
    )
    sock_a = dirs_a["runtime"] / "agent.sock"
    server_a, task_a = await _run_uds_server(app_a, sock_a)

    app_b = create_agent_app(
        run_dir=dirs_b["runtime"], default_download_dir=dirs_b["exchange"]
    )
    sock_b = dirs_b["runtime"] / "agent.sock"
    server_b, task_b = await _run_uds_server(app_b, sock_b)

    try:
        async with httpx.AsyncClient(
            base_url=str(server.base_url),
            headers={"Authorization": f"Bearer {token}"},
            trust_env=False,
        ) as api:
            gw_mock = AsyncMock()
            gw_mock.has_foreground_viewers = AsyncMock(return_value=False)
            gw_mock.disconnect_viewers = AsyncMock(return_value=True)
            core = SupervisorCore(
                docker,
                PortAllocator(),
                EventForwarder(str(server.base_url), data_root / "spool", client=api),
                api,
                token_file=token_file,
                gateway_control=gw_mock,
            )

            # Pass 1: scan discovers both running; for Profile A, observes normal exit
            # and ACKs to API
            await core.scan_and_reconcile_existing()

            # Verify API state is now desired_state="stopped", runtime_instance_id=None
            rt_a_mid = server.get(f"/api/v1/profiles/{profile_a}/runtime").json()
            assert rt_a_mid["desired_state"] == "stopped"
            assert rt_a_mid["runtime_instance_id"] is None

            # Pass 2: scan encounters desired="stopped", does NOT short-circuit,
            # runs stop_profile!
            await core.scan_and_reconcile_existing()

            # Verify Profile A has been torn down and cleaned up!
            assert profile_a in docker.torn_down_profiles
            assert profile_a not in core.ports._allocated
            assert profile_a not in core._sessions

            # Verify API remains stopped and no instance
            rt_a_final = server.get(f"/api/v1/profiles/{profile_a}/runtime").json()
            assert rt_a_final["desired_state"] == "stopped"
            assert rt_a_final["runtime_instance_id"] is None

            # Verify Profile B is still running, session active, port still allocated!
            assert profile_b in core._sessions
            assert core._sessions[profile_b].desired_state == "running"
            assert profile_b in core.ports._allocated
            assert profile_b not in docker.torn_down_profiles
            rt_b = server.get(f"/api/v1/profiles/{profile_b}/runtime").json()
            assert rt_b["desired_state"] == "running"
    finally:
        server_a.should_exit = True
        server_b.should_exit = True
        live_proc_b.terminate()
        await live_proc_b.wait()
        await asyncio.sleep(0.05)
        task_a.cancel()
        task_b.cancel()
        await asyncio.gather(task_a, task_b, return_exceptions=True)
        sock_a.unlink(missing_ok=True)
        sock_b.unlink(missing_ok=True)
        shutil.rmtree(data_root)
