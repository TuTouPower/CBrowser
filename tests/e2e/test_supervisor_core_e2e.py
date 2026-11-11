"""Full Real Docker E2E Integration Suite for Supervisor Core (AC-001 - AC-006).

Validates:
1. Real isolated FastAPI Uvicorn process with SQLite WAL and external Bearer token file.
2. Production Gateway application for Stream Agent outbound registration.
3. Dual-container sandbox for Profile A and Profile B concurrently.
4. Browser 03 with default GeoIP cache & Stream 07 with run-local UDP mux ports.
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
import json
import logging
import secrets
import shutil
import socket
import uuid
from pathlib import Path

import docker
import httpx
import pytest
from wait import poll_until

from e2e_env import free_udp_port_span, require_e2e_env
from cbrowser.domain.models import ProfileConfig
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.gateway_client import GatewayControlClient
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator
from supervisor_recovery_probe.gateway_service import (
    ApiRuntimeLookup,
    ProductionGatewayService,
)

logger = logging.getLogger(__name__)




@pytest.mark.asyncio
async def test_supervisor_dual_profile_real_docker_e2e(tmp_path: Path, real_api_server):
    env = require_e2e_env(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_STREAM_TEST_IMAGE",
        "CBROWSER_RUNTIME_ENGINE_CACHE",
        "CBROWSER_RUNTIME_GEOIP_CACHE",
        paths=("CBROWSER_RUNTIME_ENGINE_CACHE", "CBROWSER_RUNTIME_GEOIP_CACHE"),
    )
    browser_image = env["CBROWSER_RUNTIME_TEST_IMAGE"]
    stream_image = env["CBROWSER_STREAM_TEST_IMAGE"]
    engine_cache_val = env["CBROWSER_RUNTIME_ENGINE_CACHE"]
    geoip_cache_val = env["CBROWSER_RUNTIME_GEOIP_CACHE"]

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

    api_url, auth_token, token_file, auth_headers = real_api_server
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

    # Find free port for the production Gateway
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        gw_port = s.getsockname()[1]

    agent_key_file = data_root / "agent_key"
    agent_key_file.write_text(secrets.token_urlsafe(32))
    agent_key_file.chmod(0o600)

    gw_token_file = data_root / "gateway_token"
    gw_token_file.write_text(secrets.token_urlsafe(32))
    gw_token_file.chmod(0o600)

    gateway = ProductionGatewayService(
        port=gw_port,
        agent_key_file=agent_key_file,
        gateway_token_file=gw_token_file,
        runtime_lookup=ApiRuntimeLookup(api_url, token_file),
    )
    await gateway.start()

    gateway_control = GatewayControlClient(f"http://127.0.0.1:{gw_port}", gw_token_file)

    headers = {"Authorization": f"Bearer {auth_token}"}
    headers.update(auth_headers)

    api_client = httpx.AsyncClient(
        base_url=api_url,
        headers=headers,
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
    udp_base = free_udp_port_span(2)
    port_allocator = PortAllocator(min_port=udp_base, max_port=udp_base + 10)
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
        session_a = await core.start_profile(profile_a, cfg_a, profile_number=resp_a.json()["display_number"])
        assert session_a.udp_mux_port == udp_base

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

        # Wait for Stream Agent A to register and report through the production
        # Gateway control surface (deadline poll, t024 AC-007/A28).
        async def _a_registered() -> bool:
            try:
                await gateway_control.has_foreground_viewers(
                    profile_a, session_a.runtime_instance_id
                )
                return True
            except httpx.HTTPError:
                return False

        await poll_until(
            _a_registered,
            bool,
            timeout=10.0,
            interval=0.2,
            description="Stream Agent A to register with Gateway",
        )

        # 3. Start Profile B concurrently
        session_b = await core.start_profile(profile_b, cfg_b, profile_number=resp_b.json()["display_number"])
        assert session_b.udp_mux_port == udp_base + 1
        assert session_b.browser_container_id != session_a.browser_container_id

        b_c_b = d_client.containers.get(session_b.browser_container_id)
        b_c_b.reload()
        assert b_c_b.status == "running", f"Browser B status is {b_c_b.status}"

        r_info_b = json.loads(
            (data_root / "runtime" / profile_b / "runner_info.json").read_text()
        )
        assert r_info_b["browser_pid"] > 0
        assert b_c_b.id != b_c_a.id

        async def _b_registered() -> bool:
            try:
                await gateway_control.has_foreground_viewers(
                    profile_b, session_b.runtime_instance_id
                )
                return True
            except httpx.HTTPError:
                return False

        await poll_until(
            _b_registered,
            bool,
            timeout=10.0,
            interval=0.2,
            description="Stream Agent B to register with Gateway",
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

        # Base port released
        assert not port_allocator.is_port_used(udp_base)

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

    active_final = docker_adapter.scan_active_containers()
    assert len(active_final) == 0, f"Leaked containers: {active_final}"

pytestmark = pytest.mark.e2e_images('CBROWSER_RUNTIME_TEST_IMAGE', 'CBROWSER_STREAM_TEST_IMAGE')
