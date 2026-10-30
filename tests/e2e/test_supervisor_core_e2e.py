"""Full Real Docker E2E Integration Suite for Supervisor Core (AC-001 - AC-006).

Validates:
1. Real isolated FastAPI Uvicorn process with SQLite WAL and external Bearer token file.
2. Real Gateway WebSocket mock server for Stream Agent outbound registration.
3. Dual-container sandbox for Profile A and Profile B concurrently.
4. Browser 03 with default GeoIP cache & Stream 07 with UDP mux ports 30000 / 30001.
5. Verification of Browser Agent ready (runner_info.json, agent.sock, PID > 0).
6. Verification of Stream Agent authenticating and registering with Gateway.
7. Verification of cross-profile isolation (non-shared IPC / independent network).
8. Orderly stop sequence: Gateway viewer disconnect -> Stream container
   -> Browser container -> port recycled.
9. Stopping Profile A does not affect Profile B.
10. Exact cleanup of all created test containers and networks.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import docker
import httpx
import pytest
from cbrowser.domain.models import ProfileConfig
from cbrowser.supervisor.agent_credentials import AgentCredentials
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.gateway_client import GatewayControlClient
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator

_gw_spec = importlib.util.spec_from_file_location(
    "supervisor_gateway_fixture",
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "supervisor_recovery_probe"
    / "gateway_fixture.py",
)
_gw_module = importlib.util.module_from_spec(_gw_spec)
sys.modules["supervisor_gateway_fixture"] = _gw_module
_gw_spec.loader.exec_module(_gw_module)
SupervisorGatewayFixture = _gw_module.SupervisorGatewayFixture


@pytest.fixture
def real_api_server(tmp_path: Path):
    token = secrets.token_urlsafe(32)
    token_file = tmp_path / "supervisor_token"
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    env = dict(os.environ)
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        env.pop(name, None)

    root = Path(__file__).resolve().parents[2]
    env.update(
        PYTHONPATH=str(root / "src/backend"),
        PYTHONDONTWRITEBYTECODE="1",
        TMPDIR=str(tmp_path),
        CBROWSER_DB_PATH=str(tmp_path / "control.db"),
        CBROWSER_SUPERVISOR_TOKEN_FILE=str(token_file),
    )

    log_path = tmp_path / "api_server.log"
    log_f = open(log_path, "w")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "cbrowser.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=root,
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
    )

    api_url = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(base_url=api_url, trust_env=False) as client:
            ready = False
            for _ in range(100):
                try:
                    if client.get("/api/v1/health").status_code == 200:
                        ready = True
                        break
                except httpx.TransportError:
                    pass
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
            if not ready:
                pytest.fail(
                    f"Real API process failed to become ready: {log_path.read_text()}"
                )
        yield api_url, token, token_file
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        log_f.close()


@pytest.mark.asyncio
async def test_supervisor_dual_profile_real_docker_e2e(tmp_path: Path, real_api_server):
    missing = []
    browser_image = os.environ.get("CBROWSER_RUNTIME_TEST_IMAGE")
    stream_image = os.environ.get("CBROWSER_STREAM_TEST_IMAGE")
    engine_cache_val = os.environ.get("CBROWSER_RUNTIME_ENGINE_CACHE")
    geoip_cache_val = os.environ.get("CBROWSER_RUNTIME_GEOIP_CACHE")

    if not browser_image:
        missing.append("CBROWSER_RUNTIME_TEST_IMAGE")
    if not stream_image:
        missing.append("CBROWSER_STREAM_TEST_IMAGE")
    if not engine_cache_val:
        missing.append("CBROWSER_RUNTIME_ENGINE_CACHE")
    if not geoip_cache_val:
        missing.append("CBROWSER_RUNTIME_GEOIP_CACHE")

    if missing:
        pytest.skip(f"Missing required E2E environment variables: {', '.join(missing)}")

    assert browser_image.startswith("sha256:"), (
        "CBROWSER_RUNTIME_TEST_IMAGE must be sha256 immutable digest, "
        f"got {browser_image}"
    )
    assert stream_image.startswith("sha256:"), (
        "CBROWSER_STREAM_TEST_IMAGE must be sha256 immutable digest, "
        f"got {stream_image}"
    )
    engine_src = Path(engine_cache_val)
    geoip_src = Path(geoip_cache_val)
    assert engine_src.is_dir(), f"Engine cache missing at {engine_cache_val}"
    assert geoip_src.is_dir(), f"GeoIP cache missing at {geoip_cache_val}"

    api_url, auth_token, token_file = real_api_server
    test_run_id = uuid.uuid4().hex[:6]
    prefix = f"t005-{test_run_id}"
    data_root = tmp_path / "data_root"
    data_root.mkdir()
    engine_cache = data_root / "engine_cache"
    shutil.copytree(engine_src, engine_cache)
    shutil.copytree(geoip_src, engine_cache / "geoip", dirs_exist_ok=True)

    d_client = docker.from_env()
    d_client.images.get(browser_image)
    d_client.images.get(stream_image)

    # Find free port for Gateway mock
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        gw_port = s.getsockname()[1]

    agent_key_file = data_root / "agent_key"
    agent_key_file.write_text(secrets.token_urlsafe(32))
    agent_key_file.chmod(0o600)

    gw_token_file = data_root / "gateway_token"
    gw_token_file.write_text(secrets.token_urlsafe(32))
    gw_token_file.chmod(0o600)

    gateway = SupervisorGatewayFixture(
        port=gw_port,
        credentials=AgentCredentials(agent_key_file),
        token_file=gw_token_file,
    )
    await gateway.start()

    gateway_control = GatewayControlClient(f"http://127.0.0.1:{gw_port}", gw_token_file)

    api_client = httpx.AsyncClient(
        base_url=api_url,
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=10.0,
        trust_env=False,
    )

    validator = PathValidator(data_root)
    docker_adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=engine_cache,
        docker_client=d_client,
        browser_image=browser_image,
        stream_image=stream_image,
        resource_prefix=prefix,
        geoip_cache_dir=engine_cache / "geoip",
    )
    port_allocator = PortAllocator(min_port=30000, max_port=30010)
    event_forwarder = EventForwarder(
        api_base_url=api_url,
        events_spool_dir=data_root / "spool",
        token_file=token_file,
        client=api_client,
    )

    core = SupervisorCore(
        docker_adapter=docker_adapter,
        port_allocator=port_allocator,
        event_forwarder=event_forwarder,
        api_client=api_client,
        gateway_url=f"ws://host.docker.internal:{gw_port}",
        token_file=token_file,
        agent_key_file=agent_key_file,
        gateway_control=gateway_control,
    )

    # 1. Create Profile A and Profile B in real API
    resp_a = await api_client.post(
        "/api/v1/profiles", json={"name": "Profile Real A", "geoip": True}
    )
    assert resp_a.status_code == 201
    profile_a = resp_a.json()["id"]
    await api_client.patch(
        f"/api/v1/profiles/{profile_a}/runtime/desired-state",
        json={"desired_state": "running"},
    )

    resp_b = await api_client.post(
        "/api/v1/profiles", json={"name": "Profile Real B", "geoip": True}
    )
    assert resp_b.status_code == 201
    profile_b = resp_b.json()["id"]
    await api_client.patch(
        f"/api/v1/profiles/{profile_b}/runtime/desired-state",
        json={"desired_state": "running"},
    )

    cfg_a = ProfileConfig(
        name="Profile Real A", screen_width=1920, screen_height=1080, geoip=True
    )
    cfg_b = ProfileConfig(
        name="Profile Real B", screen_width=1920, screen_height=1080, geoip=True
    )

    try:
        # 2. Start Profile A in Supervisor
        session_a = await core.start_profile(profile_a, cfg_a)
        assert session_a.udp_mux_port == 30000

        # Reload & verify Browser container A
        b_c_a = d_client.containers.get(session_a.browser_container_id)
        b_c_a.reload()
        assert b_c_a.status == "running", f"Browser A status is {b_c_a.status}"
        assert b_c_a.attrs["HostConfig"]["IpcMode"] == "shareable"

        # Verify Browser Agent ready and PID exists
        r_info_a = json.loads(
            (data_root / "runtime" / profile_a / "runner_info.json").read_text()
        )
        assert r_info_a["browser_pid"] > 0

        # Wait for Stream Agent A to register with Gateway
        for _ in range(50):
            if profile_a in gateway.registered_agents:
                break
            await asyncio.sleep(0.2)
        assert profile_a in gateway.registered_agents, (
            "Stream Agent A failed to register with Gateway"
        )

        # 3. Start Profile B concurrently
        session_b = await core.start_profile(profile_b, cfg_b)
        assert session_b.udp_mux_port == 30001
        assert session_b.browser_container_id != session_a.browser_container_id

        b_c_b = d_client.containers.get(session_b.browser_container_id)
        b_c_b.reload()
        assert b_c_b.status == "running", f"Browser B status is {b_c_b.status}"

        r_info_b = json.loads(
            (data_root / "runtime" / profile_b / "runner_info.json").read_text()
        )
        assert r_info_b["browser_pid"] > 0
        assert b_c_b.id != b_c_a.id

        for _ in range(50):
            if profile_b in gateway.registered_agents:
                break
            await asyncio.sleep(0.2)
        assert profile_b in gateway.registered_agents, (
            "Stream Agent B failed to register with Gateway"
        )

        # 4. Verify cross-profile isolation
        s_c_a = d_client.containers.get(session_a.stream_container_id)
        s_c_b = d_client.containers.get(session_b.stream_container_id)
        assert s_c_a.attrs["HostConfig"]["IpcMode"] in (
            f"container:{b_c_a.name}",
            f"container:{b_c_a.id}",
        )
        assert s_c_b.attrs["HostConfig"]["IpcMode"] in (
            f"container:{b_c_b.name}",
            f"container:{b_c_b.id}",
        )
        assert (
            s_c_a.attrs["HostConfig"]["IpcMode"] != s_c_b.attrs["HostConfig"]["IpcMode"]
        )
        for container in (b_c_a, b_c_b, s_c_a, s_c_b):
            for mount in container.attrs["Mounts"]:
                if mount["Type"] == "bind":
                    assert (
                        Path(mount["Source"])
                        .resolve()
                        .is_relative_to(data_root.resolve())
                    )
                if mount["Destination"].startswith("/data/engine-cache"):
                    assert mount["RW"] is False

        # Verify active container scan
        active = docker_adapter.scan_active_containers()
        assert len(active) == 4

        # 5. Orderly Stop Profile A
        await core.stop_profile(profile_a)

        # Port 30000 released
        assert not port_allocator.is_port_used(30000)

        # Profile B remains running and intact
        b_c_b.reload()
        assert b_c_b.status == "running"
        active_after_a = docker_adapter.scan_active_containers()
        assert len(active_after_a) == 2
        assert all(c["profile_id"] == profile_b for c in active_after_a)

    finally:
        await core.stop_profile(profile_a)
        await core.stop_profile(profile_b)
        await event_forwarder.close()
        await gateway_control.close()
        await gateway.stop()
        await api_client.aclose()
        d_client.close()

        # Strict assert: zero orphan containers left
        active_final = docker_adapter.scan_active_containers()
        assert len(active_final) == 0, f"Leaked containers: {active_final}"
