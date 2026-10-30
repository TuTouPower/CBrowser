"""Real Docker E2E test suite for dynamic infrastructure network attachment (AC006).

Validates:
1. Dynamic attachment of Gateway and Coturn containers to Profile networks.
2. Actual IPv4 retrieval matching Docker container inspect for each bridge.
3. Real positive/negative sandbox network isolation:
   - Profile B Runtime listens on 0.0.0.0:9222 on net_b.
   - Probe B on net_b connects to Runtime B IP:9222 -> SUCCEEDS (positive control).
   - Probe A on net_a connects to Runtime B -> FAILS (negative control).
4. Shared Gateway/Coturn services reachable from respective Profile networks.
5. Auxiliary loopback containment verification.
6. Mid-way connection failure with real Docker error (network_mode=none coturn):
   - Gateway successfully attaches first.
   - Coturn fails Docker connect.
   - Gateway's new endpoint on this network is rolled back.
   - Gateway's pre-existing endpoint on another Profile network is untouched.
7. Error propagation during rollback (no swallowing of failures).
8. Network cleanup refuses to proceed if runtime containers are still attached.
9. Network cleanup refuses to delete when unknown endpoints exist.
10. Strict fixture teardown without force-disconnecting or swallowing unexpected errors.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, List

import docker
import pytest
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.path_validator import PathValidator
from docker.errors import NotFound

INFRA_SERVER_SCRIPT = """import socket, sys
port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('0.0.0.0', port))
s.listen(10)
print(f'READY:{port}', flush=True)
while True:
    conn, _ = s.accept()
    conn.sendall(b'PONG' + bytes([10]))
    conn.close()
"""

LOOPBACK_SERVER_SCRIPT = """import socket, sys, time
port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('127.0.0.1', port))
s.listen(10)
print(f'READY:{port}', flush=True)
while True:
    time.sleep(1)
"""


def _create_standin_container(
    client: docker.DockerClient,
    image: str,
    name: str,
    prefix: str,
    role: str,
    port: int,
    mode: str = "infra",  # "infra", "runtime", "loopback"
    network: str | None = None,
    network_mode: str | None = None,
) -> docker.models.containers.Container:
    """Create a secured stand-in container without publishing host ports."""
    if mode == "loopback":
        script = LOOPBACK_SERVER_SCRIPT
    else:
        script = INFRA_SERVER_SCRIPT

    kwargs: dict[str, Any] = {
        "entrypoint": "python3",
        "command": ["-u", "-c", script, str(port)],
        "name": name,
        "detach": True,
        "user": "1000:1000",
        "read_only": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "tmpfs": {"/tmp": "rw,size=64m"},
        "ports": {},
        "restart_policy": {"Name": "no"},
        "labels": {
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.prefix": prefix,
            "com.cbrowser.role": role,
        },
    }
    if network:
        kwargs["network"] = network
    elif network_mode:
        kwargs["network_mode"] = network_mode
    return client.containers.run(image, **kwargs)


def _wait_container_ready(
    container: docker.models.containers.Container, timeout: float = 10.0
) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        container.reload()
        if container.status == "running":
            logs = container.logs().decode("utf-8", errors="ignore")
            if "READY:" in logs:
                return
        time.sleep(0.2)
    raise TimeoutError(
        f"Container {container.name} failed to become ready: logs={container.logs()}"
    )


def _probe_tcp_connection(
    client: docker.DockerClient,
    image: str,
    network_name: str,
    target_ip: str,
    target_port: int,
    timeout: float = 2.0,
    secured_adapter: DockerAdapter | None = None,
) -> bool:
    """Use a raw control probe, or install the real sandbox egress policy first."""
    script = """import socket,sys,json
s=socket.socket();s.settimeout(float(sys.argv[3]))
try:
 s.connect((sys.argv[1],int(sys.argv[2])));data=s.recv(1024)
 result={'reachable':b'PONG' in data}
except OSError as e:
 result={'reachable':False,'error_type':type(e).__name__,'errno':e.errno}
finally:s.close()
sys.stdout.write(json.dumps(result))
"""
    command = ["python3", "-c", script, target_ip, str(target_port), str(timeout)]
    if secured_adapter is None:
        output = client.containers.run(
            image,
            entrypoint=command[0],
            command=command[1:],
            network=network_name,
            detach=False,
            remove=True,
            user="1000:1000",
            read_only=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
        )
    else:
        instance = "probe_" + uuid.uuid4().hex
        profile = client.networks.get(network_name).attrs["Labels"][
            "com.cbrowser.profile-id"
        ]
        gate = secured_adapter._prepare_policy_gate(profile, instance, "browser")
        probe = client.containers.create(
            image,
            entrypoint="python3",
            command=["-c", "import time;time.sleep(30)"],
            name=secured_adapter.resource_prefix + "-probe-" + uuid.uuid4().hex[:12],
            network=network_name,
            user="1000:1000",
            read_only=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            labels={"com.cbrowser.prefix": secured_adapter.resource_prefix},
        )
        try:
            probe.start()
            secured_adapter._install_network_policy(
                probe, {"role": "browser"}, gate, instance, "browser"
            )
            result = probe.exec_run(command, user="1000:1000")
            assert result.exit_code == 0, result.output.decode()
            output = result.output
        finally:
            probe.remove(force=True)
    return json.loads(output)["reachable"]


@pytest.fixture
def test_env(tmp_path: Path):
    client = docker.from_env()

    missing = []
    browser_img = os.environ.get("CBROWSER_RUNTIME_TEST_IMAGE")
    stream_img = os.environ.get("CBROWSER_STREAM_TEST_IMAGE")
    if not browser_img:
        missing.append("CBROWSER_RUNTIME_TEST_IMAGE")
    if not stream_img:
        missing.append("CBROWSER_STREAM_TEST_IMAGE")
    if missing:
        pytest.skip(
            f"Missing required E2E image environment variables: {', '.join(missing)}"
        )
    assert browser_img.startswith("sha256:"), (
        "CBROWSER_RUNTIME_TEST_IMAGE must be sha256 immutable digest, "
        f"got {browser_img}"
    )
    assert stream_img.startswith("sha256:"), (
        f"CBROWSER_STREAM_TEST_IMAGE must be sha256 immutable digest, got {stream_img}"
    )
    client.images.get(browser_img)
    client.images.get(stream_img)

    run_id = uuid.uuid4().hex[:8]
    prefix = f"t005-net-{run_id}"

    engine_cache = tmp_path / "engine_cache"
    geoip_cache = engine_cache / "geoip"
    engine_cache.mkdir(parents=True)
    geoip_cache.mkdir(parents=True)

    validator = PathValidator(tmp_path)
    adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=engine_cache,
        docker_client=client,
        browser_image=browser_img,
        stream_image=stream_img,
        resource_prefix=prefix,
        geoip_cache_dir=geoip_cache,
    )

    created_containers: List[docker.models.containers.Container] = []
    created_networks: List[str] = []

    try:
        yield {
            "client": client,
            "prefix": prefix,
            "adapter": adapter,
            "created_containers": created_containers,
            "created_networks": created_networks,
            "browser_image": browser_img,
            "stream_image": stream_img,
        }
    finally:
        # Strict resource teardown: only remove self-tracked containers and networks
        for c in created_containers:
            try:
                c.remove(force=True)
            except NotFound:
                pass
        for net_name in created_networks:
            try:
                adapter.cleanup_network_by_name(net_name)
            except NotFound:
                pass
        client.close()


@pytest.mark.asyncio
async def test_attach_profile_infrastructure_and_sandbox_isolation_e2e(test_env):
    """AC006 Real Docker Verification:
    1. Attach Gateway & Coturn to Profile A & Profile B networks.
    2. Validate returned IP matches inspect.
    3. Positive control: Probe B connects to Profile B 0.0.0.0:9222 -> SUCCEEDS.
    4. Negative control: Probe A on net_a connects to Profile B 0.0.0.0:9222 -> FAILS.
    5. Profile A reaches Gateway & Coturn on its network.
    6. Auxiliary check: Loopback-bound service inside sandbox inaccessible externally.
    7. Cleanup Profile A does not disrupt Profile B.
    """
    client: docker.DockerClient = test_env["client"]
    prefix: str = test_env["prefix"]
    adapter: DockerAdapter = test_env["adapter"]
    browser_image: str = test_env["browser_image"]

    policy_image = os.environ.get("CBROWSER_SUPERVISOR_TEST_IMAGE")
    if not policy_image:
        pytest.skip("Missing CBROWSER_SUPERVISOR_TEST_IMAGE for sandbox policy")
    assert policy_image.startswith("sha256:")
    client.images.get(policy_image)
    adapter.policy_image = policy_image

    # 1. Create two Profile networks
    net_a = await adapter.create_profile_network("prof_a")
    net_b = await adapter.create_profile_network("prof_b")
    test_env["created_networks"].extend([net_a.name, net_b.name])

    # 2. Create secured placeholder Gateway and Coturn containers
    gw_container = _create_standin_container(
        client,
        browser_image,
        f"{prefix}-gw-fixture",
        prefix,
        "gateway",
        18097,
        mode="infra",
        network=net_a.name,
    )
    test_env["created_containers"].append(gw_container)
    _wait_container_ready(gw_container)

    coturn_container = _create_standin_container(
        client,
        browser_image,
        f"{prefix}-coturn-fixture",
        prefix,
        "coturn",
        3478,
        mode="infra",
        network=net_a.name,
    )
    test_env["created_containers"].append(coturn_container)
    _wait_container_ready(coturn_container)

    # 3. Attach infrastructure to Profile A (idempotent reuse of net_a)
    info_a = adapter.attach_profile_infrastructure(
        profile_id="prof_a",
        gateway_container_id=gw_container.id,
        coturn_container_id=coturn_container.id,
    )
    assert "gateway_ip" in info_a and info_a["gateway_ip"]
    assert "coturn_ip" in info_a and info_a["coturn_ip"]
    assert info_a["gateway_url"] == f"ws://{info_a['gateway_ip']}:18097"
    assert info_a["coturn_ice_address"] == f"{info_a['coturn_ip']}:3478"

    gw_container.reload()
    coturn_container.reload()
    actual_gw_ip_a = gw_container.attrs["NetworkSettings"]["Networks"][net_a.name][
        "IPAddress"
    ]
    actual_coturn_ip_a = coturn_container.attrs["NetworkSettings"]["Networks"][
        net_a.name
    ]["IPAddress"]
    assert actual_gw_ip_a == info_a["gateway_ip"]
    assert actual_coturn_ip_a == info_a["coturn_ip"]

    # 4. Attach infrastructure to Profile B
    info_b = adapter.attach_profile_infrastructure(
        profile_id="prof_b",
        gateway_container_id=gw_container.id,
        coturn_container_id=coturn_container.id,
    )
    assert info_b["gateway_ip"] != info_a["gateway_ip"]
    assert info_b["coturn_ip"] != info_a["coturn_ip"]

    gw_container.reload()
    actual_gw_ip_b = gw_container.attrs["NetworkSettings"]["Networks"][net_b.name][
        "IPAddress"
    ]
    assert actual_gw_ip_b == info_b["gateway_ip"]

    # 5. Idempotent re-attach
    info_a2 = adapter.attach_profile_infrastructure(
        profile_id="prof_a",
        gateway_container_id=gw_container.id,
        coturn_container_id=coturn_container.id,
    )
    assert info_a2 == info_a

    # 6. Verify TCP connectivity from within Profile A to shared infrastructure
    reach_gw = _probe_tcp_connection(
        client, browser_image, net_a.name, info_a["gateway_ip"], 18097
    )
    assert reach_gw is True, "Gateway TCP port 18097 unreachable from Profile A probe"

    reach_coturn = _probe_tcp_connection(
        client, browser_image, net_a.name, info_a["coturn_ip"], 3478
    )
    assert reach_coturn is True, "Coturn TCP port 3478 unreachable from Profile A probe"

    # 7. Real positive/negative bridge network isolation test:
    # Profile B stand-in Runtime container listening on 0.0.0.0:9222 on net_b
    b_runtime = _create_standin_container(
        client,
        browser_image,
        f"{prefix}-prof-b-runtime",
        prefix,
        "browser",
        9222,
        mode="runtime",
        network=net_b.name,
    )
    test_env["created_containers"].append(b_runtime)
    _wait_container_ready(b_runtime)
    b_runtime.reload()
    runtime_b_ip = b_runtime.attrs["NetworkSettings"]["Networks"][net_b.name][
        "IPAddress"
    ]

    # Positive control: Probe in net_b CAN reach Profile B runtime on net_b
    same_net_reach = _probe_tcp_connection(
        client, browser_image, net_b.name, runtime_b_ip, 9222, timeout=2.0
    )
    assert same_net_reach is True, (
        "Positive control failed: Probe B could not reach Runtime B on net_b!"
    )

    # Negative control: production sandbox policy blocks foreign Profile traffic.
    cross_reach = _probe_tcp_connection(
        client,
        browser_image,
        net_a.name,
        runtime_b_ip,
        9222,
        timeout=2.0,
        secured_adapter=adapter,
    )
    assert cross_reach is False, (
        "Isolation violation: Probe A reached Runtime B across bridge boundaries!"
    )

    # 8. Auxiliary check: loopback-bound service inside sandbox (like real CDP loopback)
    loopback_runtime = _create_standin_container(
        client,
        browser_image,
        f"{prefix}-prof-b-loopback",
        prefix,
        "browser",
        9223,
        mode="loopback",
        network=net_b.name,
    )
    test_env["created_containers"].append(loopback_runtime)
    _wait_container_ready(loopback_runtime)
    loopback_runtime.reload()
    loopback_ip = loopback_runtime.attrs["NetworkSettings"]["Networks"][net_b.name][
        "IPAddress"
    ]

    loopback_reach = _probe_tcp_connection(
        client, browser_image, net_b.name, loopback_ip, 9223, timeout=1.0
    )
    assert loopback_reach is False, (
        "Auxiliary check: loopback service leaked outside container!"
    )

    # 9. Clean up Profile B runtime containers for teardown
    b_runtime.remove(force=True)
    test_env["created_containers"].remove(b_runtime)
    loopback_runtime.remove(force=True)
    test_env["created_containers"].remove(loopback_runtime)

    # 10. Clean up Profile A network without affecting net_b
    adapter.cleanup_network_by_name(net_a.name)
    test_env["created_networks"].remove(net_a.name)

    with pytest.raises(NotFound):
        client.networks.get(net_a.id)

    # Net B and its infra connectivity remain intact
    gw_container.reload()
    assert net_b.name in gw_container.attrs["NetworkSettings"]["Networks"]
    reach_gw_b = _probe_tcp_connection(
        client, browser_image, net_b.name, info_b["gateway_ip"], 18097
    )
    assert reach_gw_b is True, (
        "Profile B Gateway connection broken after Profile A teardown"
    )


@pytest.mark.asyncio
async def test_midway_failure_atomic_rollback_and_error_propagation_e2e(test_env):
    """Validates true mid-way connection failure and atomic rollback:
    1. Pre-connect Gateway to network D.
    2. Attempt attachment to network E where Gateway connects successfully,
       but Coturn (network_mode=none) causes real Docker daemon connect failure.
    3. Assert Gateway's new endpoint on network E is rolled back.
    4. Assert Gateway's prior endpoint on network D is preserved.
    """
    client: docker.DockerClient = test_env["client"]
    prefix: str = test_env["prefix"]
    adapter: DockerAdapter = test_env["adapter"]
    browser_image: str = test_env["browser_image"]

    net_d = await adapter.create_profile_network("prof_d")
    net_e = await adapter.create_profile_network("prof_e")
    test_env["created_networks"].extend([net_d.name, net_e.name])

    # Gateway container
    valid_gw = _create_standin_container(
        client,
        browser_image,
        f"{prefix}-gw-rollback",
        prefix,
        "gateway",
        18097,
        network=net_d.name,
    )
    test_env["created_containers"].append(valid_gw)
    _wait_container_ready(valid_gw)

    # Coturn container configured with network_mode='none'
    # Passes validation, but Docker daemon rejects connecting 'none' container
    failing_coturn = _create_standin_container(
        client,
        browser_image,
        f"{prefix}-coturn-none",
        prefix,
        "coturn",
        3478,
        network_mode="none",
    )
    test_env["created_containers"].append(failing_coturn)
    _wait_container_ready(failing_coturn)

    # Attach must fail mid-way
    with pytest.raises(DockerSandboxError, match="[Ii]nfrastructure attachment failed"):
        adapter.attach_profile_infrastructure(
            profile_id="prof_e",
            gateway_container_id=valid_gw.id,
            coturn_container_id=failing_coturn.id,
        )

    # Verify Gateway new endpoint on net_e rolled back
    valid_gw.reload()
    assert net_e.name not in (valid_gw.attrs["NetworkSettings"]["Networks"] or {})

    # Verify Gateway pre-existing endpoint on net_d preserved
    assert net_d.name in (valid_gw.attrs["NetworkSettings"]["Networks"] or {})


@pytest.mark.asyncio
async def test_network_cleanup_lifecycle_and_unknown_endpoint_rejection_e2e(test_env):
    """Validates:
    1. Cleanup refuses to proceed while runtime containers are still attached.
    2. Cleanup refuses to proceed if unknown/unmanaged endpoints are attached.
    3. Cleanup succeeds once runtime containers are removed and only infra remains.
    """
    client: docker.DockerClient = test_env["client"]
    prefix: str = test_env["prefix"]
    adapter: DockerAdapter = test_env["adapter"]
    browser_image: str = test_env["browser_image"]

    net_f = await adapter.create_profile_network("prof_f")
    test_env["created_networks"].append(net_f.name)

    # 1. Attach a running runtime container (e.g. browser)
    runtime_c = client.containers.run(
        browser_image,
        entrypoint="sleep",
        command=["60"],
        name=f"{prefix}-browser-prof_f",
        network=net_f.name,
        detach=True,
        labels={
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.prefix": prefix,
            "com.cbrowser.role": "browser",
            "com.cbrowser.profile-id": "prof_f",
        },
    )
    test_env["created_containers"].append(runtime_c)

    # Cleanup must refuse because runtime container is still attached
    with pytest.raises(DockerSandboxError, match="runtime container.*still attached"):
        adapter.cleanup_network_by_name(net_f.name)

    # Remove the runtime container (proper lifecycle teardown)
    runtime_c.remove(force=True)
    test_env["created_containers"].remove(runtime_c)

    # 2. Unknown / unmanaged container attached blocks cleanup
    unmanaged = client.containers.run(
        browser_image,
        entrypoint="sleep",
        command=["60"],
        name=f"{prefix}-unmanaged",
        network=net_f.name,
        detach=True,
        labels={"foreign.label": "true"},
    )
    test_env["created_containers"].append(unmanaged)

    with pytest.raises(DockerSandboxError, match="[Uu]nknown endpoint|[Uu]nauthorized"):
        adapter.cleanup_network_by_name(net_f.name)

    # Disconnect unmanaged, cleanup succeeds
    net_f.disconnect(unmanaged)
    adapter.cleanup_network_by_name(net_f.name)
    test_env["created_networks"].remove(net_f.name)
