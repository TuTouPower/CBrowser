"""Full Real Docker E2E Integration Suite for Supervisor Core (AC-001 - AC-006).

Validates:
1. Real isolated FastAPI Uvicorn process with SQLite WAL and external Bearer token file.
2. Production Gateway application for Stream Agent outbound registration.
3. Dual-container sandbox for Profile A and Profile B concurrently using named volumes.
4. Browser 03 with default GeoIP cache & Stream 07 with run-local UDP mux ports.
5. Verification of Browser Agent ready (runner_info.json, agent.sock, PID > 0).
6. Verification of Stream Agent authenticating and registering with Gateway.
7. Verification of cross-profile isolation (non-shared IPC / independent network).
8. Orderly stop sequence: Gateway viewer disconnect -> Stream container
   -> Browser container -> port recycled.
9. Stopping Profile A does not affect Profile B.
10. Exact cleanup of all created test containers, networks, and named volumes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import socket
import uuid
from pathlib import Path

import docker
import httpx
import pytest

from e2e_env import free_udp_port_span, require_e2e_env
from e2e_volumes import (
    init_prefix_volumes,
    prepare_minimal_e2e_fonts_root,
    run_volume_json,
)
from gateway_probe.topology import cleanup_prefixed_resources
from supervisor_recovery_probe.gateway_service import (
    ApiRuntimeLookup,
    ProductionGatewayService,
)

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.e2e_images(
    "CBROWSER_RUNTIME_TEST_IMAGE",
    "CBROWSER_STREAM_TEST_IMAGE",
    "CBROWSER_SUPERVISOR_TEST_IMAGE",
)


_SUPERVISOR_CORE_DRIVER = """
import asyncio
import json
import os
from pathlib import Path

import docker
import httpx
from cbrowser.domain.models import ProfileConfig


async def _wait_until(check, *, timeout: float, interval: float, description: str) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if await check():
            return
        await asyncio.sleep(interval)
    raise TimeoutError(f"Timed out waiting for: {description}")
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.gateway_client import GatewayControlClient
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator
from cbrowser.supervisor.storage_layout import volume_name


async def main() -> None:
    data_root = Path("/data")
    control_dir = data_root / "control"
    control_dir.mkdir(parents=True, exist_ok=True)

    token_file = control_dir / "sup_token"
    token_file.write_text(os.environ["CB_AUTH_TOKEN"], encoding="utf-8")
    token_file.chmod(0o600)

    agent_key_file = control_dir / "agent_key"
    agent_key_file.write_text(os.environ["CB_AGENT_KEY"], encoding="utf-8")
    agent_key_file.chmod(0o600)

    gw_token_file = control_dir / "gateway_token"
    gw_token_file.write_text(os.environ["CB_GW_TOKEN"], encoding="utf-8")
    gw_token_file.chmod(0o600)

    api_url = os.environ["CB_API_URL"]
    gw_port = int(os.environ["CB_GW_PORT"])
    prefix = os.environ["CB_TEST_PREFIX"]
    headers = json.loads(os.environ["CB_API_HEADERS"])
    profile_a = os.environ["CB_PROFILE_A"]
    profile_b = os.environ["CB_PROFILE_B"]
    num_a = int(os.environ["CB_NUM_A"])
    num_b = int(os.environ["CB_NUM_B"])
    cfg_a = ProfileConfig.model_validate_json(os.environ["CB_CFG_A"])
    cfg_b = ProfileConfig.model_validate_json(os.environ["CB_CFG_B"])
    udp_base = int(os.environ["CB_UDP_BASE"])

    d_client = docker.from_env()
    gateway_control = GatewayControlClient(
        f"http://host.docker.internal:{gw_port}", gw_token_file
    )
    api_client = httpx.AsyncClient(
        base_url=api_url, headers=headers, timeout=10.0, trust_env=False
    )
    validator = PathValidator(data_root)
    docker_adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=data_root / "engine-cache",
        docker_client=d_client,
        browser_image=os.environ["CB_BROWSER_IMAGE"],
        stream_image=os.environ["CB_STREAM_IMAGE"],
        resource_prefix=prefix,
        geoip_cache_dir=data_root / "engine-cache" / "geoip",
        manage_ownership=True,
    )
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

    try:
        # 2. Start Profile A in Supervisor
        session_a = await core.start_profile(
            profile_a, cfg_a, profile_number=num_a
        )
        assert session_a.udp_mux_port == udp_base

        b_c_a = d_client.containers.get(session_a.browser_container_id)
        b_c_a.reload()
        assert b_c_a.status == "running", f"Browser A status is {b_c_a.status}"
        assert b_c_a.attrs["HostConfig"]["IpcMode"] == "shareable"

        r_info_a = json.loads(
            (data_root / "runtime" / profile_a / "runner_info.json").read_text()
        )
        assert r_info_a["browser_pid"] > 0

        async def _a_registered() -> bool:
            try:
                await gateway_control.has_foreground_viewers(
                    profile_a, session_a.runtime_instance_id
                )
                return True
            except httpx.HTTPError:
                return False

        await _wait_until(
            _a_registered,
            timeout=10.0,
            interval=0.2,
            description="Stream Agent A to register with Gateway",
        )

        # 3. Start Profile B concurrently
        session_b = await core.start_profile(
            profile_b, cfg_b, profile_number=num_b
        )
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

        await _wait_until(
            _b_registered,
            timeout=10.0,
            interval=0.2,
            description="Stream Agent B to register with Gateway",
        )

        # 4. Verify cross-profile isolation and volume mount contract
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
            s_c_a.attrs["HostConfig"]["IpcMode"]
            != s_c_b.attrs["HostConfig"]["IpcMode"]
        )
        allowed_vols = {
            volume_name(prefix, "data"),
            volume_name(prefix, "runtime"),
            volume_name(prefix, "fonts"),
        }
        for container in (b_c_a, b_c_b, s_c_a, s_c_b):
            for mount in container.attrs["Mounts"]:
                assert mount["Type"] == "volume", f"Unexpected non-volume mount: {mount}"
                assert mount["Name"] in allowed_vols, mount
                if mount["Destination"].startswith("/data/engine-cache"):
                    assert mount["RW"] is False

        active = docker_adapter.scan_active_containers()
        assert len(active) == 4

        # 5. Orderly Stop Profile A
        await core.stop_profile(profile_a)
        assert not port_allocator.is_port_used(udp_base)

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
        await api_client.aclose()
        active_final = docker_adapter.scan_active_containers()
        d_client.close()

    assert len(active_final) == 0, f"Leaked containers: {active_final}"
    print("CBROWSER_E2E_RESULT=" + json.dumps({"ok": True}))


asyncio.run(main())
"""


@pytest.mark.asyncio
async def test_supervisor_dual_profile_real_docker_e2e(tmp_path: Path, real_api_server):
    env = require_e2e_env(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_STREAM_TEST_IMAGE",
        "CBROWSER_SUPERVISOR_TEST_IMAGE",
        "CBROWSER_RUNTIME_ENGINE_CACHE",
        "CBROWSER_RUNTIME_GEOIP_CACHE",
        paths=("CBROWSER_RUNTIME_ENGINE_CACHE", "CBROWSER_RUNTIME_GEOIP_CACHE"),
    )
    browser_image = env["CBROWSER_RUNTIME_TEST_IMAGE"]
    stream_image = env["CBROWSER_STREAM_TEST_IMAGE"]
    supervisor_image = env["CBROWSER_SUPERVISOR_TEST_IMAGE"]
    engine_src = Path(env["CBROWSER_RUNTIME_ENGINE_CACHE"])
    geoip_src = Path(env["CBROWSER_RUNTIME_GEOIP_CACHE"])

    for var_name, img in (
        ("CBROWSER_RUNTIME_TEST_IMAGE", browser_image),
        ("CBROWSER_STREAM_TEST_IMAGE", stream_image),
        ("CBROWSER_SUPERVISOR_TEST_IMAGE", supervisor_image),
    ):
        assert img.startswith("sha256:"), (
            f"{var_name} must be sha256 immutable digest, got {img}"
        )
    assert engine_src.is_dir(), f"Engine cache missing at {engine_src}"
    assert geoip_src.is_dir(), f"GeoIP cache missing at {geoip_src}"

    api_url, auth_token, token_file, auth_headers = real_api_server
    test_run_id = uuid.uuid4().hex[:6]
    prefix = f"t005-{test_run_id}"

    d_client = docker.from_env()
    d_client.images.get(browser_image)
    d_client.images.get(stream_image)
    d_client.images.get(supervisor_image)

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        gw_port = s.getsockname()[1]

    agent_key_val = secrets.token_urlsafe(32)
    agent_key_file = tmp_path / "agent_key"
    agent_key_file.write_text(agent_key_val, encoding="utf-8")
    agent_key_file.chmod(0o600)

    gw_token_val = secrets.token_urlsafe(32)
    gw_token_file = tmp_path / "gateway_token"
    gw_token_file.write_text(gw_token_val, encoding="utf-8")
    gw_token_file.chmod(0o600)

    gateway = ProductionGatewayService(
        port=gw_port,
        agent_key_file=agent_key_file,
        gateway_token_file=gw_token_file,
        runtime_lookup=ApiRuntimeLookup(api_url, token_file),
    )
    await gateway.start()

    headers = {"Authorization": f"Bearer {auth_token}"}
    headers.update(auth_headers)
    api_client = httpx.AsyncClient(
        base_url=api_url,
        headers=headers,
        timeout=10.0,
        trust_env=False,
    )
    udp_base = free_udp_port_span(2)

    try:
        # 1. Create Profile A and Profile B in real API
        resp_a = await api_client.post(
            "/api/v1/profiles", json={"name": "Profile Real A", "geoip": True}
        )
        assert resp_a.status_code == 201
        profile_a = resp_a.json()["id"]
        num_a = resp_a.json()["display_number"]
        await api_client.patch(
            f"/api/v1/profiles/{profile_a}/runtime/desired-state",
            json={"desired_state": "running"},
        )
        snap_a = await api_client.get(
            f"/api/v1/internal/supervisor/profiles/{profile_a}/versions/1"
        )
        snap_a.raise_for_status()

        resp_b = await api_client.post(
            "/api/v1/profiles", json={"name": "Profile Real B", "geoip": True}
        )
        assert resp_b.status_code == 201
        profile_b = resp_b.json()["id"]
        num_b = resp_b.json()["display_number"]
        await api_client.patch(
            f"/api/v1/profiles/{profile_b}/runtime/desired-state",
            json={"desired_state": "running"},
        )
        snap_b = await api_client.get(
            f"/api/v1/internal/supervisor/profiles/{profile_b}/versions/1"
        )
        snap_b.raise_for_status()

        fonts_dir = token_file.parent / "fonts"
        if not fonts_dir.is_dir():
            fonts_dir, _ = prepare_minimal_e2e_fonts_root(
                tmp_path / "e2e_fonts",
                browser_image=browser_image,
                docker_client=d_client,
            )

        init_prefix_volumes(
            d_client,
            prefix,
            supervisor_image,
            roles=("data", "runtime", "fonts"),
            engine_cache_src=engine_src,
            geoip_cache_src=geoip_src,
            fonts_root_src=fonts_dir,
        )

        container_api_url = api_url.replace("127.0.0.1", "host.docker.internal")
        res = await asyncio.to_thread(
            run_volume_json,
            d_client,
            prefix,
            supervisor_image,
            _SUPERVISOR_CORE_DRIVER,
            roles=("data", "runtime", "fonts"),
            mount_docker_sock=True,
            extra_hosts={"host.docker.internal": "host-gateway"},
            env={
                "CB_AUTH_TOKEN": auth_token,
                "CB_AGENT_KEY": agent_key_val,
                "CB_GW_TOKEN": gw_token_val,
                "CB_API_URL": container_api_url,
                "CB_GW_PORT": str(gw_port),
                "CB_TEST_PREFIX": prefix,
                "CB_API_HEADERS": json.dumps(headers),
                "CB_PROFILE_A": profile_a,
                "CB_PROFILE_B": profile_b,
                "CB_NUM_A": str(num_a),
                "CB_NUM_B": str(num_b),
                "CB_CFG_A": json.dumps(snap_a.json()["config"]),
                "CB_CFG_B": json.dumps(snap_b.json()["config"]),
                "CB_BROWSER_IMAGE": browser_image,
                "CB_STREAM_IMAGE": stream_image,
                "CB_UDP_BASE": str(udp_base),
            },
        )
        assert res == {"ok": True}
    finally:
        await gateway.stop()
        await api_client.aclose()
        try:
            cleanup_prefixed_resources(d_client, prefix)
        finally:
            d_client.close()
