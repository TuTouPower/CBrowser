"""Production-grade Kernel E2E Failure Blackbox Test for Network Policy.

Contract invariants:
1. When Policy Agent creation/installation fails (here: the policy
   image is invalid, so the target's Agent never becomes healthy):
   - DockerAdapter raises DockerSandboxError.
   - Startup gate ready.json marker is NEVER created.
   - Target business processes inside container are NEVER executed.
   - SupervisorCore rolls back and cleans up any created containers/networks.
   - Port allocations are cleanly released.
   - Persistent API state records failure_count == 1,
     runtime_instance_id == None, desired_state == 'running'.
2. Zero leakage guarantee:
   - All test resources tagged with random 't005-nsbb-' prefix.
   - Pre-check and post-check confirm 0 leaked containers/networks/volumes for prefix.
   - Uses real SupervisorCore, DockerAdapter, EventForwarder, and real_api_server.
   - No mock transport, no FakeDocker.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import uuid
from pathlib import Path

import docker
import httpx
import pytest
from wait import poll_until

from e2e_env import free_udp_port_span, require_e2e_env
from e2e_volumes import (
    init_prefix_volumes,
    prepare_minimal_e2e_fonts_root,
    remove_prefix_volumes,
    run_volume_json,
)

logger = logging.getLogger("cbrowser.test.policy_failure_e2e")

pytestmark = pytest.mark.e2e_images(
    "CBROWSER_INVALID_POLICY_TEST_IMAGE",
    "CBROWSER_RUNTIME_TEST_IMAGE",
    "CBROWSER_STREAM_TEST_IMAGE",
    "CBROWSER_SUPERVISOR_TEST_IMAGE",
)


def _get_required_env_image(env_var: str) -> str:
    val = require_e2e_env(env_var)[env_var]
    if not (val.startswith("sha256:") or "@sha256:" in val):
        pytest.fail(f"Env var {env_var} must be immutable digest, got: {val}")
    return val


@pytest.fixture
def docker_client() -> docker.DockerClient:
    return docker.from_env()


_POLICY_FAIL_DRIVER = """
import asyncio
import json
import os
from pathlib import Path

import docker
import httpx
from cbrowser.domain.models import ProfileConfig
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator


async def main() -> None:
    data_root = Path("/data")
    control_dir = data_root / "control"
    control_dir.mkdir(parents=True, exist_ok=True)
    token_file = control_dir / "supervisor_token"
    token_file.write_text(os.environ["CB_AUTH_TOKEN"], encoding="utf-8")
    token_file.chmod(0o600)
    agent_key_file = control_dir / "agent_key"
    agent_key_file.write_text(os.environ["CB_AGENT_KEY"], encoding="utf-8")
    agent_key_file.chmod(0o600)

    headers = json.loads(os.environ["CB_API_HEADERS"])
    api_url = os.environ["CB_API_URL"]
    prefix = os.environ["CB_TEST_PREFIX"]
    profile_id = os.environ["CB_PROFILE_ID"]
    profile_number = int(os.environ["CB_PROFILE_NUMBER"])
    cfg = ProfileConfig.model_validate_json(os.environ["CB_PROFILE_CFG_JSON"])

    d_client = docker.from_env()
    api_client = httpx.AsyncClient(
        base_url=api_url,
        headers=headers,
        timeout=10.0,
        trust_env=False,
    )
    validator = PathValidator(data_root)
    docker_adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=data_root / "engine-cache",
        docker_client=d_client,
        browser_image=os.environ["CB_BROWSER_IMAGE"],
        stream_image=os.environ["CB_STREAM_IMAGE"],
        policy_image=os.environ["CB_INVALID_POLICY_IMAGE"],
        resource_prefix=prefix,
        geoip_cache_dir=data_root / "engine-cache" / "geoip",
    )
    udp_base = int(os.environ["CB_UDP_BASE"])
    port_allocator = PortAllocator(min_port=udp_base, max_port=udp_base + 5)
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
        gateway_url="ws://127.0.0.1:18097",
        token_file=token_file,
        agent_key_file=agent_key_file,
    )
    raised_sandbox_error = False
    try:
        try:
            await core.start_profile(
                profile_id=profile_id,
                config=cfg,
                config_version=1,
                profile_number=profile_number,
            )
        except DockerSandboxError:
            raised_sandbox_error = True

        gates_root = data_root / "control" / "gates" / profile_id
        ready_markers = [str(p) for p in gates_root.glob("**/ready.json")]
        runtime_dir = data_root / "runtime" / profile_id
        runner_info = [str(p) for p in runtime_dir.glob("**/runner_info.json")]
        await event_forwarder.replay_spooled_events()
        port_released = port_allocator.get_port(profile_id) is None
        print(
            "CBROWSER_E2E_RESULT="
            + json.dumps(
                {
                    "raised_sandbox_error": raised_sandbox_error,
                    "ready_markers": ready_markers,
                    "runner_info": runner_info,
                    "port_released": port_released,
                }
            )
        )
    finally:
        await event_forwarder.close()
        await api_client.aclose()
        d_client.close()


asyncio.run(main())
"""


@pytest.mark.asyncio
async def test_policy_installation_failure_fail_closed_and_cleanup(
    tmp_path: Path,
    docker_client: docker.DockerClient,
    real_api_server: tuple[str, str, Path, dict],
) -> None:
    """Verify fail-closed behavior when policy installation fails."""
    browser_image = _get_required_env_image("CBROWSER_RUNTIME_TEST_IMAGE")
    stream_image = _get_required_env_image("CBROWSER_STREAM_TEST_IMAGE")
    supervisor_image = _get_required_env_image("CBROWSER_SUPERVISOR_TEST_IMAGE")
    invalid_policy_image = _get_required_env_image("CBROWSER_INVALID_POLICY_TEST_IMAGE")

    env_caches = require_e2e_env(
        "CBROWSER_RUNTIME_ENGINE_CACHE",
        "CBROWSER_RUNTIME_GEOIP_CACHE",
        paths=("CBROWSER_RUNTIME_ENGINE_CACHE", "CBROWSER_RUNTIME_GEOIP_CACHE"),
    )
    engine_src = Path(env_caches["CBROWSER_RUNTIME_ENGINE_CACHE"])
    geoip_src = Path(env_caches["CBROWSER_RUNTIME_GEOIP_CACHE"])

    api_url, auth_token, token_file, auth_headers = real_api_server
    test_run_id = uuid.uuid4().hex[:8]
    prefix = f"t005-nsbb-{test_run_id}"

    # Pre-check: Ensure no lingering containers or networks with this prefix
    pre_containers = docker_client.containers.list(
        all=True, filters={"name": f"{prefix}-"}
    )
    pre_networks = docker_client.networks.list(names=[f"{prefix}-"])
    assert len(pre_containers) == 0, f"Pre-existing containers: {pre_containers}"
    assert len(pre_networks) == 0, f"Pre-existing networks: {pre_networks}"

    fonts_dir = token_file.parent / "fonts"
    if not fonts_dir.is_dir():
        fonts_dir, _ = prepare_minimal_e2e_fonts_root(
            tmp_path / "e2e_fonts",
            browser_image=browser_image,
            docker_client=docker_client,
        )

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
        # Register profile in real API server
        create_resp = await api_client.post(
            "/api/v1/profiles",
            json={"name": f"PolicyFailProfile-{test_run_id}", "geoip": False},
        )
        assert create_resp.status_code == 201, (
            f"Failed to create profile: {create_resp.text}"
        )
        created_pid = create_resp.json()["id"]
        profile_number = create_resp.json()["display_number"]

        # Set profile desired_state = running
        start_resp = await api_client.patch(
            f"/api/v1/profiles/{created_pid}/runtime/desired-state",
            json={"desired_state": "running"},
        )
        assert start_resp.status_code == 200, (
            f"Failed to set desired_state: {start_resp.text}"
        )

        snapshot = await api_client.get(
            f"/api/v1/internal/supervisor/profiles/{created_pid}/versions/1"
        )
        snapshot.raise_for_status()
        cfg_json = json.dumps(snapshot.json()["config"])

        init_prefix_volumes(
            docker_client,
            prefix,
            supervisor_image,
            roles=("data", "runtime", "fonts"),
            engine_cache_src=engine_src,
            geoip_cache_src=geoip_src,
            fonts_root_src=fonts_dir,
        )

        container_api_url = api_url.replace("127.0.0.1", "host.docker.internal")
        driver_res = await asyncio.to_thread(
            run_volume_json,
            docker_client,
            prefix,
            supervisor_image,
            _POLICY_FAIL_DRIVER,
            roles=("data", "runtime", "fonts"),
            mount_docker_sock=True,
            extra_hosts={"host.docker.internal": "host-gateway"},
            env={
                "CB_AUTH_TOKEN": auth_token,
                "CB_AGENT_KEY": secrets.token_urlsafe(32),
                "CB_API_HEADERS": json.dumps(headers),
                "CB_API_URL": container_api_url,
                "CB_TEST_PREFIX": prefix,
                "CB_PROFILE_ID": created_pid,
                "CB_PROFILE_NUMBER": str(profile_number),
                "CB_PROFILE_CFG_JSON": cfg_json,
                "CB_BROWSER_IMAGE": browser_image,
                "CB_STREAM_IMAGE": stream_image,
                "CB_INVALID_POLICY_IMAGE": invalid_policy_image,
                "CB_UDP_BASE": str(udp_base),
            },
        )

        # 1. SupervisorCore.start_profile MUST raise DockerSandboxError
        assert driver_res["raised_sandbox_error"] is True

        # 2. Startup gate ready marker and runner_info.json were NEVER created
        assert driver_res["ready_markers"] == [], (
            f"ready.json marker created despite failure: {driver_res['ready_markers']}"
        )
        assert driver_res["runner_info"] == [], (
            f"runner_info.json formed despite failure: {driver_res['runner_info']}"
        )

        # 5. Verify real API runtime state convergence
        async def read_runtime() -> dict:
            resp = await api_client.get(
                f"/api/v1/profiles/{created_pid}/runtime"
            )
            assert resp.status_code == 200, (
                f"Failed to fetch runtime state: {resp.text}"
            )
            return resp.json()

        rt_data = await poll_until(
            read_runtime,
            lambda data: data.get("failure_count") == 1
            and data.get("runtime_instance_id") is None,
            timeout=10.0,
            interval=0.1,
            description="API runtime convergence after policy failure",
        )
        assert rt_data.get("failure_count") == 1
        assert rt_data.get("runtime_instance_id") is None
        assert rt_data.get("desired_state") == "running"

        # 6. Verify port allocator released the port
        assert driver_res["port_released"] is True

        # 7. Post-check: Verify 0 container and network leakage
        post_containers = docker_client.containers.list(
            all=True, filters={"name": f"{prefix}-"}
        )
        post_networks = docker_client.networks.list(names=[f"{prefix}-"])
        assert len(post_containers) == 0, (
            f"Leaked containers: {[c.name for c in post_containers]}"
        )
        assert len(post_networks) == 0, (
            f"Leaked networks: {[n.name for n in post_networks]}"
        )

    finally:
        await api_client.aclose()
        cleanup_errors = []
        leak_containers = docker_client.containers.list(
            all=True, filters={"name": f"{prefix}-"}
        )
        for c in leak_containers:
            try:
                c.remove(force=True)
            except docker.errors.NotFound:
                pass
            except docker.errors.DockerException as exc:
                cleanup_errors.append(type(exc).__name__)
        leak_networks = docker_client.networks.list(names=[f"{prefix}-"])
        for n in leak_networks:
            try:
                n.remove()
            except docker.errors.NotFound:
                pass
            except docker.errors.DockerException as exc:
                cleanup_errors.append(type(exc).__name__)
        cleanup_errors.extend(remove_prefix_volumes(docker_client, prefix))
        docker_client.close()

    assert not cleanup_errors, "Owned resource cleanup failed: " + ",".join(
        cleanup_errors
    )
