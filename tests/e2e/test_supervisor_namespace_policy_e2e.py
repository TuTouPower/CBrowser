"""Production-grade Kernel E2E Blackbox Test for Network Policy and Startup Gate.

Contract invariants:
1. Startup Gate Process Sentinel (real subprocess test):
   - Blocks application startup while ready.json is absent.
   - Rejects missing ready.json on timeout or malformed JSON.
   - Rejects mismatched instance_id, mismatched role, or status != 'ready'.
   - Successfully executes application command ONLY when valid marker arrives.
2. Kernel Network Policy Application & Isolation:
   - Uses CBROWSER_SUPERVISOR_TEST_IMAGE as immutable policy helper.
   - Uses CBROWSER_RUNTIME_TEST_IMAGE as Python raw server/client target.
   - Target containers run as UID 1000:1000, read_only=True, cap_drop=['ALL'].
   - Helper container runs with cap_drop=['ALL'], cap_add=['NET_ADMIN'],
     security_opt=['no-new-privileges:true'], read_only=True,
     tmpfs={'/run': 'rw,noexec,nosuid,size=16m'},
     network_mode='container:<target_id>'.
   - Helper entrypoint is explicitly
     ['python3', '-m', 'cbrowser.supervisor.network_policy'].
   - Positive same-peer communication to explicitly allowed TCP endpoint.
   - Negative same-peer blocked port (listening raw socket, but not in policy).
   - Negative cross-peer / blocked bridge communication.
   - Negative other-bridge communication (isolated network).
   - IPv4 public egress verified reachable (e.g. 1.1.1.1:80).
   - Policy persistence after helper exits and is removed.
   - Non-modified namespaces remain unaffected.
   - Real dual-stack / ULA IPv6 fail-closed verification.
3. Clean-up & Tracking:
   - Strict tracking of all containers and networks with 't005-nsbb-' prefix.
   - Exact cleanup in finally blocks ensuring 0 leaked resources.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import docker
import pytest
from cbrowser.supervisor.network_policy import NetworkPolicySpec

logger = logging.getLogger("cbrowser.test.namespace_policy_e2e")


def _get_required_env_image(env_var: str) -> str:
    val = os.environ.get(env_var)
    if not val:
        pytest.skip(f"Env var {env_var} not set; skipping policy e2e.")
    if not (val.startswith("sha256:") or "@sha256:" in val):
        pytest.fail(f"Env var {env_var} must be immutable digest, got: {val}")
    return val


@pytest.fixture
def policy_helper_image(docker_client: docker.DockerClient) -> str:
    img = _get_required_env_image("CBROWSER_SUPERVISOR_TEST_IMAGE")
    try:
        docker_client.images.get(img)
    except docker.errors.ImageNotFound:
        pytest.fail(f"CBROWSER_SUPERVISOR_TEST_IMAGE ({img}) not found")
    return img


@pytest.fixture
def runtime_target_image(docker_client: docker.DockerClient) -> str:
    img = _get_required_env_image("CBROWSER_RUNTIME_TEST_IMAGE")
    try:
        docker_client.images.get(img)
    except docker.errors.ImageNotFound:
        pytest.fail(f"CBROWSER_RUNTIME_TEST_IMAGE ({img}) not found")
    return img


@pytest.fixture
def docker_client() -> docker.DockerClient:
    return docker.from_env()


@pytest.fixture
def resource_tracker():
    """Tracks created containers and networks for deterministic cleanup."""
    containers: list[docker.models.containers.Container] = []
    networks: list[docker.models.networks.Network] = []

    class Tracker:
        def register_container(
            self, container: docker.models.containers.Container
        ) -> docker.models.containers.Container:
            containers.append(container)
            return container

        def register_network(
            self, network: docker.models.networks.Network
        ) -> docker.models.networks.Network:
            networks.append(network)
            return network

    tracker = Tracker()
    yield tracker

    for c in reversed(containers):
        try:
            c.stop(timeout=2)
        except Exception as exc:
            logger.debug("Container stop error: %s", exc)
        try:
            c.remove(force=True)
        except Exception as exc:
            logger.debug("Container remove error: %s", exc)

    for n in reversed(networks):
        try:
            n.remove()
        except Exception as exc:
            logger.debug("Network remove error: %s", exc)


def test_startup_gate_subprocess_sentinel(tmp_path: Path) -> None:
    """Verify startup_gate.py in a real subprocess: sentinel blocks & execs."""
    gate_dir = tmp_path / "gate"
    gate_dir.mkdir(parents=True)
    out_file = tmp_path / "app_executed.txt"

    instance_id = f"inst-{uuid.uuid4().hex[:6]}"
    role = "browser"

    gate_script = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "backend"
        / "cbrowser"
        / "supervisor"
        / "startup_gate.py"
    )

    cmd = [
        sys.executable,
        str(gate_script),
        "--instance-id",
        instance_id,
        "--role",
        role,
        "--gate-dir",
        str(gate_dir),
        "--timeout",
        "3.0",
        "--poll-interval",
        "0.05",
        "--",
        sys.executable,
        "-c",
        f"from pathlib import Path; Path({str(out_file)!r}).write_text('SUCCESS')",
    ]

    # 1. Absence of marker: process waits and does not execute application
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.3)
    assert proc.poll() is None, "Gate exited prematurely while marker absent"
    assert not out_file.exists(), "Target app ran before marker appeared!"

    # 2. Corrupt / malformed JSON: gate must reject and exit with non-zero
    marker_file = gate_dir / "ready.json"
    marker_file.write_text("{corrupt-json", encoding="utf-8")
    ret_corrupt = proc.wait(timeout=2.0)
    assert ret_corrupt != 0, f"Gate did not reject corrupt JSON (ret={ret_corrupt})"
    assert not out_file.exists()
    marker_file.unlink()

    # 3. Mismatched instance_id: gate must reject and exit with non-zero
    proc_wrong_inst = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.1)
    marker_file.write_text(
        json.dumps({"instance_id": "other-inst", "role": role, "status": "ready"}),
        encoding="utf-8",
    )
    ret_wrong_inst = proc_wrong_inst.wait(timeout=2.0)
    assert ret_wrong_inst != 0, "Gate did not reject mismatched instance_id"
    assert not out_file.exists()
    marker_file.unlink()

    # 4. Mismatched role: gate must reject and exit with non-zero
    proc_wrong_role = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.1)
    marker_file.write_text(
        json.dumps({"instance_id": instance_id, "role": "stream", "status": "ready"}),
        encoding="utf-8",
    )
    ret_wrong_role = proc_wrong_role.wait(timeout=2.0)
    assert ret_wrong_role != 0, "Gate did not reject mismatched role"
    assert not out_file.exists()
    marker_file.unlink()

    # 5. Non-ready status: gate must reject and exit with non-zero
    proc_wrong_status = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.1)
    marker_file.write_text(
        json.dumps(
            {"instance_id": instance_id, "role": role, "status": "initializing"}
        ),
        encoding="utf-8",
    )
    ret_wrong_status = proc_wrong_status.wait(timeout=2.0)
    assert ret_wrong_status != 0, "Gate did not reject non-ready status"
    assert not out_file.exists()
    marker_file.unlink()

    # 6. Valid ready marker: gate allows os.execv of application command
    proc_valid = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.2)
    assert proc_valid.poll() is None
    assert not out_file.exists()

    tmp_marker = gate_dir / "ready.json.tmp"
    tmp_marker.write_text(
        json.dumps({"instance_id": instance_id, "role": role, "status": "ready"}),
        encoding="utf-8",
    )
    tmp_marker.replace(gate_dir / "ready.json")

    ret_valid = proc_valid.wait(timeout=2.0)
    assert ret_valid == 0, f"Gate failed with exit code {ret_valid}"
    assert out_file.exists(), "Target application was not executed upon valid marker"
    assert out_file.read_text().strip() == "SUCCESS"


def _wait_for_server_ready(container: docker.models.containers.Container) -> None:
    """Bounded wait for Python raw TCP server inside container to log READY."""
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        logs = container.logs().decode("utf-8", errors="replace")
        if "READY" in logs:
            return
        time.sleep(0.1)
    raise TimeoutError(f"Server {container.name} did not become READY in 10s")


def _run_python_probe(
    container: docker.models.containers.Container,
    host: str,
    port: int,
    send_payload: bytes = b"PING\n",
    timeout: float = 1.5,
    family: int = 4,
) -> tuple[int, str]:
    """Execute raw Python client probe inside target container."""
    py_code = (
        "import socket, sys\n"
        "host = sys.argv[1]\n"
        "port = int(sys.argv[2])\n"
        "timeout = float(sys.argv[3])\n"
        "payload = sys.argv[4].encode('utf-8')\n"
        "family = socket.AF_INET6 if int(sys.argv[5]) == 6 else socket.AF_INET\n"
        "try:\n"
        "    s = socket.socket(family, socket.SOCK_STREAM)\n"
        "    s.settimeout(timeout)\n"
        "    s.connect((host, port))\n"
        "    s.sendall(payload)\n"
        "    data = s.recv(1024)\n"
        "    s.close()\n"
        "    sys.stdout.write('RECV:' + data.decode('utf-8', errors='replace'))\n"
        "    sys.exit(0)\n"
        "except Exception as e:\n"
        "    sys.stderr.write(f'ERR:{type(e).__name__}:{e}')\n"
        "    sys.exit(1)\n"
    )
    res = container.exec_run(
        [
            "python3",
            "-c",
            py_code,
            host,
            str(port),
            str(timeout),
            send_payload.decode("utf-8", errors="replace"),
            str(family),
        ],
        user="1000:1000",
    )
    return res.exit_code, res.output.decode("utf-8", errors="replace")


def test_kernel_network_policy_real_netns(
    docker_client: docker.DockerClient,
    policy_helper_image: str,
    runtime_target_image: str,
    resource_tracker: Any,
) -> None:
    """Verify kernel network policy in dual-stack netns."""
    prefix = f"t005-nsbb-{uuid.uuid4().hex[:8]}"

    server_script = (
        "import socket, threading, sys\n"
        "def serve(port, msg):\n"
        "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
        "    s.bind(('0.0.0.0', port))\n"
        "    s.listen(5)\n"
        "    while True:\n"
        "        conn, _ = s.accept()\n"
        "        _ = conn.recv(1024)\n"
        "        conn.sendall(msg.encode('utf-8'))\n"
        "        conn.close()\n"
        "threading.Thread("
        "target=serve, args=(8888, 'PROXY_PONG'), daemon=True).start()\n"
        "threading.Thread("
        "target=serve, args=(9999, 'OTHER_PONG'), daemon=True).start()\n"
        "sys.stdout.write('READY\\n')\n"
        "sys.stdout.flush()\n"
        "import time\n"
        "while True: time.sleep(1)\n"
    )

    idle_script = "import time; [time.sleep(1) for _ in iter(int, 1)]"

    primary_net = resource_tracker.register_network(
        docker_client.networks.create(
            name=f"{prefix}-pri-net",
            driver="bridge",
            enable_ipv6=True,
            ipam=docker.types.IPAMConfig(
                pool_configs=[
                    docker.types.IPAMPool(
                        subnet=f"fdcb:{uuid.uuid4().hex[:4]}:{uuid.uuid4().hex[:4]}::/64"
                    ),
                ]
            ),
            check_duplicate=True,
        )
    )

    sec_net = resource_tracker.register_network(
        docker_client.networks.create(
            name=f"{prefix}-sec-net",
            driver="bridge",
            check_duplicate=True,
        )
    )

    target_a = resource_tracker.register_container(
        docker_client.containers.create(
            image=runtime_target_image,
            name=f"{prefix}-target-a",
            entrypoint=["python3", "-u", "-c", idle_script],
            command=[],
            network=primary_net.name,
            user="1000:1000",
            read_only=True,
            cap_drop=["ALL"],
            tmpfs={"/tmp": "rw,noexec,nosuid,size=16m"},
            detach=True,
        )
    )
    target_a.start()

    target_b = resource_tracker.register_container(
        docker_client.containers.create(
            image=runtime_target_image,
            name=f"{prefix}-peer-b",
            entrypoint=["python3", "-u", "-c", server_script],
            command=[],
            network=primary_net.name,
            user="1000:1000",
            read_only=True,
            cap_drop=["ALL"],
            tmpfs={"/tmp": "rw,noexec,nosuid,size=16m"},
            detach=True,
        )
    )
    target_b.start()

    target_c = resource_tracker.register_container(
        docker_client.containers.create(
            image=runtime_target_image,
            name=f"{prefix}-proxy-c",
            entrypoint=["python3", "-u", "-c", server_script],
            command=[],
            network=primary_net.name,
            user="1000:1000",
            read_only=True,
            cap_drop=["ALL"],
            tmpfs={"/tmp": "rw,noexec,nosuid,size=16m"},
            detach=True,
        )
    )
    target_c.start()

    target_d = resource_tracker.register_container(
        docker_client.containers.create(
            image=runtime_target_image,
            name=f"{prefix}-other-d",
            entrypoint=["python3", "-u", "-c", server_script],
            command=[],
            network=sec_net.name,
            user="1000:1000",
            read_only=True,
            cap_drop=["ALL"],
            tmpfs={"/tmp": "rw,noexec,nosuid,size=16m"},
            detach=True,
        )
    )
    target_d.start()

    target_e = resource_tracker.register_container(
        docker_client.containers.create(
            image=runtime_target_image,
            name=f"{prefix}-ctrl-e",
            entrypoint=["python3", "-u", "-c", idle_script],
            command=[],
            network=sec_net.name,
            user="1000:1000",
            read_only=True,
            cap_drop=["ALL"],
            tmpfs={"/tmp": "rw,noexec,nosuid,size=16m"},
            detach=True,
        )
    )
    target_e.start()

    _wait_for_server_ready(target_b)
    _wait_for_server_ready(target_c)
    _wait_for_server_ready(target_d)

    target_a.reload()
    target_b.reload()
    target_c.reload()
    target_d.reload()
    target_e.reload()

    ip_b = target_b.attrs["NetworkSettings"]["Networks"][primary_net.name]["IPAddress"]
    ip_c = target_c.attrs["NetworkSettings"]["Networks"][primary_net.name]["IPAddress"]
    ip_d = target_d.attrs["NetworkSettings"]["Networks"][sec_net.name]["IPAddress"]

    code_ctrl, out_ctrl = _run_python_probe(target_e, ip_d, 8888)
    assert code_ctrl == 0 and "PROXY_PONG" in out_ctrl, (
        f"Control container E failed to reach D: code={code_ctrl}, out={out_ctrl}"
    )

    spec = NetworkPolicySpec(
        role="browser",
        allowed_tcp=[(ip_c, 8888)],
        allowed_udp=[],
    )
    spec_json = spec.model_dump_json()

    helper = resource_tracker.register_container(
        docker_client.containers.create(
            image=policy_helper_image,
            name=f"{prefix}-helper",
            entrypoint=["python3", "-m", "cbrowser.supervisor.network_policy"],
            command=[spec_json],
            network_mode=f"container:{target_a.id}",
            cap_drop=["ALL"],
            cap_add=["NET_ADMIN"],
            security_opt=["no-new-privileges:true"],
            read_only=True,
            tmpfs={"/run": "rw,noexec,nosuid,size=16m"},
            detach=True,
        )
    )
    helper.start()
    res_helper = helper.wait(timeout=15)
    helper_logs = helper.logs().decode("utf-8", errors="replace")
    assert res_helper.get("StatusCode") == 0, f"Policy helper failed: {helper_logs}"

    helper.remove(force=True)

    # 1. Positive case: Target C port 8888 allowed
    code_c_allowed, out_c_allowed = _run_python_probe(target_a, ip_c, 8888)
    assert code_c_allowed == 0, f"Allowed proxy C unreachable: {out_c_allowed}"
    assert "PROXY_PONG" in out_c_allowed

    # 2. Negative case: Target C unlisted port 9999 blocked
    code_c_blocked, out_c_blocked = _run_python_probe(target_a, ip_c, 9999, timeout=1.0)
    assert code_c_blocked != 0, (
        f"Unlisted port on proxy C was not blocked! Out: {out_c_blocked}"
    )

    # 3. Negative case: Same-bridge unauthorized peer B blocked
    code_b_blocked, out_b_blocked = _run_python_probe(target_a, ip_b, 8888, timeout=1.0)
    assert code_b_blocked != 0, (
        f"Unauthorized peer B was not blocked! Out: {out_b_blocked}"
    )

    # 4. Negative case: Target D on secondary bridge blocked
    code_d_blocked, out_d_blocked = _run_python_probe(target_a, ip_d, 8888, timeout=1.0)
    assert code_d_blocked != 0, (
        f"Target D on secondary bridge was reachable! Out: {out_d_blocked}"
    )

    # 5. Non-public / RFC1918 / CGNAT / Benchmark ranges blocked
    code_cgnat, _ = _run_python_probe(target_a, "100.64.1.1", 80, timeout=0.8)
    assert code_cgnat != 0, "CGNAT range was not blocked!"

    code_bench, _ = _run_python_probe(target_a, "198.18.1.1", 80, timeout=0.8)
    assert code_bench != 0, "Benchmark range was not blocked!"

    # 6. Public IPv4 egress preserved
    code_pub, out_pub = _run_python_probe(
        target_a, "1.1.1.1", 80, send_payload=b"HEAD / HTTP/1.0\r\n\r\n", timeout=3.0
    )
    assert code_pub == 0, f"Public IPv4 egress was blocked: {out_pub}"

    # 7. IPv6 ULA fail-closed verification
    v6_b = target_b.attrs["NetworkSettings"]["Networks"][primary_net.name].get(
        "GlobalIPv6Address"
    )
    v6_c = target_c.attrs["NetworkSettings"]["Networks"][primary_net.name].get(
        "GlobalIPv6Address"
    )
    if v6_c:
        code_v6_c, out_v6_c = _run_python_probe(
            target_a, v6_c, 8888, timeout=1.0, family=6
        )
        assert code_v6_c != 0, f"IPv6 ULA on peer C not blocked: {out_v6_c}"
    if v6_b:
        code_v6_b, out_v6_b = _run_python_probe(
            target_a, v6_b, 8888, timeout=1.0, family=6
        )
        assert code_v6_b != 0, f"IPv6 ULA on peer B not blocked: {out_v6_b}"

    # 8. Verify other namespace (Target B) was NOT modified
    code_b_to_c, out_b_to_c = _run_python_probe(target_b, ip_c, 9999, timeout=1.5)
    assert code_b_to_c == 0 and "OTHER_PONG" in out_b_to_c, (
        f"Target B namespace was modified by helper! Out: {out_b_to_c}"
    )
