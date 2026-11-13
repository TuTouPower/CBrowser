"""Production-grade Kernel E2E Failure Blackbox Test for Network Policy.

Contract invariants:
1. When policy installation helper fails:
   - DockerAdapter raises DockerSandboxError.
   - Startup gate ready.json marker is NEVER created.
   - Target business processes inside container are NEVER executed.
   - SupervisorCore rolls back and cleans up any created containers/networks.
   - Port allocations are cleanly released.
   - Persistent API state records failure_count == 1,
     runtime_instance_id == None, desired_state == 'running'.
2. Zero leakage guarantee:
   - All test resources tagged with random 't005-nsbb-' prefix.
   - Pre-check and post-check confirm 0 leaked containers/networks for prefix.
   - Uses real SupervisorCore, DockerAdapter, EventForwarder, and real_api_server.
   - No mock transport, no FakeDocker.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import shutil
import uuid
from pathlib import Path

import docker
import httpx
import pytest
from wait import poll_until

from e2e_env import free_udp_port_span, require_e2e_env
from cbrowser.domain.models import ProfileConfig
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator

logger = logging.getLogger("cbrowser.test.policy_failure_e2e")


def _get_required_env_image(env_var: str) -> str:
    val = require_e2e_env(env_var)[env_var]
    if not (val.startswith("sha256:") or "@sha256:" in val):
        pytest.fail(f"Env var {env_var} must be immutable digest, got: {val}")
    return val


@pytest.fixture
def docker_client() -> docker.DockerClient:
    return docker.from_env()


@pytest.mark.asyncio
async def test_policy_installation_failure_fail_closed_and_cleanup(
    tmp_path: Path,
    docker_client: docker.DockerClient,
    real_api_server: tuple[str, str, Path, dict],
) -> None:
    """Verify fail-closed behavior when policy installation fails."""
    browser_image = _get_required_env_image("CBROWSER_RUNTIME_TEST_IMAGE")
    stream_image = _get_required_env_image("CBROWSER_STREAM_TEST_IMAGE")
    invalid_policy_image = _get_required_env_image("CBROWSER_INVALID_POLICY_TEST_IMAGE")

    engine_cache_val = require_e2e_env(
        "CBROWSER_RUNTIME_ENGINE_CACHE", paths=("CBROWSER_RUNTIME_ENGINE_CACHE",)
    )["CBROWSER_RUNTIME_ENGINE_CACHE"]

    api_url, auth_token, token_file, auth_headers = real_api_server
    test_run_id = uuid.uuid4().hex[:8]
    prefix = f"t005-nsbb-{test_run_id}"

    data_root = tmp_path / "data_root"
    data_root.mkdir()
    engine_cache = data_root / "engine_cache"
    shutil.copytree(Path(engine_cache_val), engine_cache)
    (engine_cache / "geoip").mkdir(parents=True, exist_ok=True)

    # Pre-check: Ensure no lingering containers or networks with this prefix
    pre_containers = docker_client.containers.list(
        all=True, filters={"name": f"{prefix}-"}
    )
    pre_networks = docker_client.networks.list(names=[f"{prefix}-"])
    assert len(pre_containers) == 0, f"Pre-existing containers: {pre_containers}"
    assert len(pre_networks) == 0, f"Pre-existing networks: {pre_networks}"

    agent_key_file = data_root / "agent_key"
    agent_key_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    agent_key_file.chmod(0o600)

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
        docker_client=docker_client,
        browser_image=browser_image,
        stream_image=stream_image,
        policy_image=invalid_policy_image,
        resource_prefix=prefix,
        geoip_cache_dir=engine_cache / "geoip",
    )
    udp_base = free_udp_port_span(2)
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
        cfg = ProfileConfig.model_validate(snapshot.json()["config"])

        # 1. SupervisorCore.start_profile MUST raise DockerSandboxError
        with pytest.raises(DockerSandboxError):
            await core.start_profile(
                profile_id=created_pid, config=cfg, config_version=1,
                profile_number=create_resp.json()["display_number"]
            )

        # 2. Check startup gate ready marker was NEVER created
        gates_root = data_root / "control" / "gates" / created_pid
        ready_markers = list(gates_root.glob("**/ready.json"))
        assert len(ready_markers) == 0, (
            f"ready.json marker created despite failure: {ready_markers}"
        )

        # 3. Check runner_info.json was NEVER created
        runtime_dir = data_root / "runtime" / created_pid
        runner_info = list(runtime_dir.glob("**/runner_info.json"))
        assert len(runner_info) == 0, (
            f"runner_info.json formed despite failure: {runner_info}"
        )

        # 4. Drain any spooled events to ensure API receives startup_failure
        await event_forwarder.replay_spooled_events()

        # 5. Verify real API runtime state convergence: poll the runtime
        # fields with a deadline (t024 AC-007/A28) instead of sleeping a
        # fixed interval and reading once.
        async def read_runtime() -> dict:
            resp = await api_client.get(
                f"/api/v1/internal/supervisor/profiles/{created_pid}/runtime"
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
        assert rt_data.get("failure_count") == 1, (
            f"Expected failure_count == 1, got {rt_data.get('failure_count')}"
        )
        assert rt_data.get("runtime_instance_id") is None, (
            f"Expected runtime_instance_id None, got "
            f"{rt_data.get('runtime_instance_id')}"
        )
        assert rt_data.get("desired_state") == "running", (
            f"Expected desired_state 'running', got {rt_data.get('desired_state')}"
        )

        # 6. Verify port allocator released the port
        port_info = port_allocator.get_port(created_pid)
        assert port_info is None, f"Port was not released: {port_info}"

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
        await event_forwarder.close()
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
        docker_client.close()

    assert not cleanup_errors, "Owned resource cleanup failed: " + ",".join(
        cleanup_errors
    )

pytestmark = pytest.mark.e2e_images('CBROWSER_INVALID_POLICY_TEST_IMAGE', 'CBROWSER_RUNTIME_TEST_IMAGE', 'CBROWSER_STREAM_TEST_IMAGE')
