"""Real Process SIGKILL & State Recovery E2E Integration Suite.

Validates AC-003 & AC-004:
1. Real isolated API server + Real isolated Supervisor process running control_server.
2. Real Profile started with Browser 03 and Stream 07 containers.
3. Supervisor process is abruptly killed with SIGKILL (simulating crash/node failover).
4. Browser and Stream containers remain running and healthy during Supervisor absence.
5. Supervisor process restarts, rescans Docker containers via prefix labels,
   reconstructs ActiveSession and re-allocates UDP mux port without terminating live
   containers.
6. Normal exit event persistence & API reconciliation: when normal exit occurs,
   API state updates to stopped and neither restart nor duplicate replay clears
   stopped state.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import docker
import httpx
import pytest
from cbrowser.supervisor.agent_credentials import AgentCredentials

_gw_fixture_path = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "supervisor_recovery_probe"
    / "gateway_fixture.py"
)
_gw_spec = importlib.util.spec_from_file_location("gateway_fixture", _gw_fixture_path)
_gw_mod = importlib.util.module_from_spec(_gw_spec)
sys.modules["gateway_fixture"] = _gw_mod
_gw_spec.loader.exec_module(_gw_mod)
SupervisorGatewayFixture = _gw_mod.SupervisorGatewayFixture

_auth_path = Path(__file__).resolve().parents[1] / "fixtures" / "api_auth.py"
_auth_spec = importlib.util.spec_from_file_location("api_auth", _auth_path)
_auth_mod = importlib.util.module_from_spec(_auth_spec)
sys.modules["api_auth"] = _auth_mod
_auth_spec.loader.exec_module(_auth_mod)
create_auth_context = _auth_mod.create_auth_context

logger = logging.getLogger(__name__)


def get_e2e_prerequisites() -> tuple[str, str, Path, Path]:
    missing = []
    browser_img = os.environ.get("CBROWSER_RUNTIME_TEST_IMAGE")
    stream_img = os.environ.get("CBROWSER_STREAM_TEST_IMAGE")
    engine_cache = os.environ.get("CBROWSER_RUNTIME_ENGINE_CACHE")
    geoip_cache = os.environ.get("CBROWSER_RUNTIME_GEOIP_CACHE")

    if not browser_img:
        missing.append("CBROWSER_RUNTIME_TEST_IMAGE")
    if not stream_img:
        missing.append("CBROWSER_STREAM_TEST_IMAGE")
    if not engine_cache:
        missing.append("CBROWSER_RUNTIME_ENGINE_CACHE")
    if not geoip_cache:
        missing.append("CBROWSER_RUNTIME_GEOIP_CACHE")

    if missing:
        pytest.skip(f"Missing required E2E environment variables: {', '.join(missing)}")

    assert browser_img.startswith("sha256:"), (
        "CBROWSER_RUNTIME_TEST_IMAGE must be sha256 immutable digest, "
        f"got {browser_img}"
    )
    assert stream_img.startswith("sha256:"), (
        f"CBROWSER_STREAM_TEST_IMAGE must be sha256 immutable digest, got {stream_img}"
    )
    engine_path = Path(engine_cache)
    geoip_path = Path(geoip_cache)
    assert engine_path.is_dir(), (
        f"CBROWSER_RUNTIME_ENGINE_CACHE is not a valid directory: {engine_cache}"
    )
    assert geoip_path.is_dir(), (
        f"CBROWSER_RUNTIME_GEOIP_CACHE is not a valid directory: {geoip_cache}"
    )
    d_client = docker.from_env()
    try:
        d_client.images.get(browser_img)
        d_client.images.get(stream_img)
    finally:
        d_client.close()
    return browser_img, stream_img, engine_path, geoip_path


@pytest.fixture
def real_api_and_sup(tmp_path: Path):
    sup_token = secrets.token_urlsafe(32)
    sup_token_file = tmp_path / "supervisor_token"
    sup_token_file.write_text(sup_token, encoding="utf-8")
    sup_token_file.chmod(0o600)

    agent_key = secrets.token_urlsafe(32)
    agent_key_file = tmp_path / "agent_key"
    agent_key_file.write_text(agent_key, encoding="utf-8")
    agent_key_file.chmod(0o600)

    gw_token = secrets.token_urlsafe(32)
    gw_token_file = tmp_path / "gateway_token"
    gw_token_file.write_text(gw_token, encoding="utf-8")
    gw_token_file.chmod(0o600)

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        api_port = s.getsockname()[1]

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        sup_port = s.getsockname()[1]

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        gw_port = s.getsockname()[1]

    auth_ctx = create_auth_context(tmp_path, origin=f"http://127.0.0.1:{api_port}")
    root = Path(__file__).resolve().parents[2]
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
    env.update(
        PYTHONPATH=str(root / "src/backend"),
        PYTHONDONTWRITEBYTECODE="1",
        TMPDIR=str(tmp_path),
        CBROWSER_DB_PATH=str(tmp_path / "control.db"),
        CBROWSER_SUPERVISOR_TOKEN_FILE=str(sup_token_file),
        **auth_ctx.env,
    )

    api_log = tmp_path / "api.log"
    api_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "cbrowser.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
        ],
        cwd=root,
        env=env,
        stdout=open(api_log, "w"),
        stderr=subprocess.STDOUT,
    )

    api_url = f"http://127.0.0.1:{api_port}"
    with httpx.Client(base_url=api_url, trust_env=False) as c:
        for _ in range(100):
            try:
                if c.get("/api/v1/health").status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.1)
        auth_headers = auth_ctx.login_sync(api_url, c)

    yield {
        "api_url": api_url,
        "sup_port": sup_port,
        "gw_port": gw_port,
        "sup_token": sup_token,
        "sup_token_file": sup_token_file,
        "agent_key_file": agent_key_file,
        "gw_token_file": gw_token_file,
        "root": root,
        "env": env,
        "auth_headers": auth_headers,
    }

    api_proc.terminate()
    try:
        api_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        api_proc.kill()


@pytest.mark.asyncio
async def test_supervisor_sigkill_reconciliation_and_event_persistence(
    tmp_path: Path, real_api_and_sup
):
    api_url = real_api_and_sup["api_url"]
    sup_port = real_api_and_sup["sup_port"]
    gw_port = real_api_and_sup["gw_port"]
    sup_token = real_api_and_sup["sup_token"]
    sup_token_file = real_api_and_sup["sup_token_file"]
    agent_key_file = real_api_and_sup["agent_key_file"]
    gw_token_file = real_api_and_sup["gw_token_file"]
    root = real_api_and_sup["root"]
    env = real_api_and_sup["env"]

    browser_image, stream_image, engine_src, geoip_src = get_e2e_prerequisites()

    data_root = tmp_path / "data_root"
    data_root.mkdir()
    engine_cache = data_root / "engine_cache"
    shutil.copytree(engine_src, engine_cache)
    shutil.copytree(geoip_src, engine_cache / "geoip", dirs_exist_ok=True)
    env = dict(
        env,
        CBROWSER_BROWSER_IMAGE=browser_image,
        CBROWSER_STREAM_IMAGE=stream_image,
    )

    gateway = SupervisorGatewayFixture(
        port=gw_port,
        credentials=AgentCredentials(agent_key_file),
        token_file=gw_token_file,
    )
    await gateway.start()

    test_run_id = uuid.uuid4().hex[:6]
    prefix = f"t005-rec-{test_run_id}"

    d_client = docker.from_env()

    turn_image = os.environ.get(
        "CBROWSER_TURN_TEST_IMAGE",
        "sha256:e2bca2f79a4269d7240de5872ab60a9305013ad37296d2acf14f9510874346be",
    )
    d_client.images.get(turn_image)
    turn_config = data_root / "turn.conf"
    turn_config.write_text(
        "listening-port=3478\nrealm=cbrowser.local\nuse-auth-secret\n"
        "no-cli\nno-tls\nno-dtls\n"
        "static-auth-secret=" + secrets.token_hex(32) + "\n"
    )
    turn_config.chmod(0o644)
    coturn = d_client.containers.run(
        turn_image,
        name=f"{prefix}-coturn",
        detach=True,
        read_only=True,
        cap_drop=["ALL"],
        cap_add=["NET_BIND_SERVICE"],
        security_opt=["no-new-privileges:true"],
        tmpfs={"/tmp": "rw,size=256m"},
        entrypoint="/usr/bin/turnserver",
        command=[
            "-c",
            "/etc/turnserver.conf",
            "--relay-threads=1",
            "--log-file=stdout",
        ],
        volumes={str(turn_config): {"bind": "/etc/turnserver.conf", "mode": "ro"}},
        labels={
            "com.cbrowser.prefix": prefix,
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.role": "coturn",
        },
    )

    api_headers = {"Authorization": f"Bearer {sup_token}"}
    api_headers.update(real_api_and_sup["auth_headers"])

    # 1. Create Profile in API
    async with httpx.AsyncClient(
        base_url=api_url,
        headers=api_headers,
        trust_env=False,
    ) as api_client:
        r_create = await api_client.post(
            "/api/v1/profiles", json={"name": "Recovery Profile", "geoip": True}
        )
        assert r_create.status_code == 201
        profile_id = r_create.json()["id"]
        r_des = await api_client.patch(
            f"/api/v1/profiles/{profile_id}/runtime/desired-state",
            json={"desired_state": "running"},
        )
        assert r_des.status_code == 200

    # 2. Spawn Supervisor process
    sup_log = tmp_path / "supervisor.log"
    sup_cmd = [
        sys.executable,
        "-m",
        "cbrowser.supervisor.runner",
        "--api-url",
        api_url,
        "--data-root",
        str(data_root),
        "--engine-cache",
        str(engine_cache),
        "--geoip-cache",
        str(engine_cache / "geoip"),
        "--token-file",
        str(sup_token_file),
        "--agent-key-file",
        str(agent_key_file),
        "--gateway-url",
        f"ws://host.docker.internal:{gw_port}",
        "--gateway-control-url",
        f"http://127.0.0.1:{gw_port}",
        "--gateway-token-file",
        str(gw_token_file),
        "--coturn-container-id",
        coturn.id,
        "--prefix",
        prefix,
        "--host",
        "127.0.0.1",
        "--port",
        str(sup_port),
    ]

    sup_proc = subprocess.Popen(
        sup_cmd, cwd=root, env=env, stdout=open(sup_log, "w"), stderr=subprocess.STDOUT
    )

    sup_url = f"http://127.0.0.1:{sup_port}"
    sup_headers = {"Authorization": f"Bearer {sup_token}"}

    async with httpx.AsyncClient(
        base_url=sup_url, headers=sup_headers, timeout=60.0, trust_env=False
    ) as sup_client:
        # Wait for supervisor health
        for _ in range(100):
            try:
                r_h = await sup_client.get("/supervisor/v1/health")
                if r_h.status_code == 200:
                    break
            except httpx.TransportError:
                pass
            await asyncio.sleep(0.1)

        # Start Profile via Supervisor control server
        r_start = await sup_client.post(
            "/supervisor/v1/profiles/start",
            json={"profile_id": profile_id, "config_version": 1},
        )
        assert r_start.status_code == 200
        start_info = r_start.json()
        b_cname = start_info["browser_container"]
        s_cname = start_info["stream_container"]

    # Verify both containers running
    b_c = d_client.containers.get(b_cname)
    s_c = d_client.containers.get(s_cname)
    assert b_c.status == "running"
    assert s_c.status == "running"

    # 3. SIGKILL the Supervisor process!
    sup_proc.send_signal(signal.SIGKILL)
    sup_proc.wait()

    # Assert Browser and Stream containers STILL running during Supervisor absence
    b_c.reload()
    s_c.reload()
    assert b_c.status == "running", (
        "Browser container must NOT die on supervisor SIGKILL"
    )
    assert s_c.status == "running", (
        "Stream container must NOT die on supervisor SIGKILL"
    )

    # 4. Restart Supervisor process
    sup_proc2 = subprocess.Popen(
        sup_cmd, cwd=root, env=env, stdout=open(sup_log, "a"), stderr=subprocess.STDOUT
    )

    try:
        async with httpx.AsyncClient(
            base_url=sup_url, headers=sup_headers, timeout=60.0, trust_env=False
        ) as sup_client2:
            for _ in range(100):
                try:
                    r_h = await sup_client2.get("/supervisor/v1/health")
                    if r_h.status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.1)

            # Query status from resurrected supervisor
            r_stat = await sup_client2.get(
                f"/supervisor/v1/profiles/{profile_id}/status"
            )
            assert r_stat.status_code == 200
            stat_data = r_stat.json()
            assert stat_data["observed_state"] == "running"
            assert stat_data["udp_mux_port"] == 30000

            # 5. Real Browser Normal Exit via in-container Agent UDS /control RPC
            # Execute python inside browser container to trigger graceful close
            script = (
                "import httpx; "
                "transport = httpx.HTTPTransport("
                "uds='/run/cbrowser/runtime/agent.sock'); "
                "client = httpx.Client(transport=transport, base_url='http://uds'); "
                "r = client.post('/control', json={'action': 'close'}); "
                "assert r.status_code == 200, r.text; "
                "client.close()"
            )
            close_cmd = ["docker", "exec", b_cname, "python3", "-c", script]
            res_close = subprocess.run(
                close_cmd, capture_output=True, text=True, check=True
            )
            logger.info(f"Triggered real browser close: {res_close.stdout}")

            # Wait for background monitoring loop in supervisor to consume real disk
            # exit event and sync API
            async with httpx.AsyncClient(
                base_url=api_url,
                headers={"Authorization": f"Bearer {sup_token}"},
                trust_env=False,
            ) as api_client2:
                for _ in range(50):
                    r_rt = await api_client2.get(
                        f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime"
                    )
                    if (
                        r_rt.status_code == 200
                        and r_rt.json()["desired_state"] == "stopped"
                    ):
                        break
                    await asyncio.sleep(0.5)

                assert r_rt.status_code == 200
                assert r_rt.json()["desired_state"] == "stopped", (
                    f"API desired_state did not converge to stopped: {r_rt.text}"
                )

            # Stop Profile cleanly via revived supervisor
            r_stop = await sup_client2.post(
                "/supervisor/v1/profiles/stop",
                json={
                    "profile_id": profile_id,
                    "runtime_instance_id": start_info["runtime_instance_id"],
                    "operation_id": f"stop-{profile_id}",
                },
            )
            assert r_stop.status_code == 200

    finally:
        sup_proc2.terminate()
        try:
            sup_proc2.wait(timeout=5)
        except subprocess.TimeoutExpired:
            sup_proc2.kill()
        await gateway.stop()
        if coturn is not None:
            try:
                coturn.remove(force=True)
            except Exception:
                pass
        # Clean containers
        for c in (b_cname, s_cname):
            try:
                d_client.containers.get(c).remove(force=True)
            except docker.errors.NotFound:
                pass
        for network in d_client.networks.list(
            filters={
                "label": [
                    f"com.cbrowser.prefix={prefix}",
                    "com.cbrowser.managed-by=supervisor",
                ]
            },
        ):
            network.remove()
        d_client.close()


@pytest.mark.asyncio
async def test_supervisor_dual_profile_port_invariance_on_sigkill(
    tmp_path: Path, real_api_and_sup
):
    api_url = real_api_and_sup["api_url"]
    sup_port = real_api_and_sup["sup_port"]
    gw_port = real_api_and_sup["gw_port"]
    sup_token = real_api_and_sup["sup_token"]
    sup_token_file = real_api_and_sup["sup_token_file"]
    agent_key_file = real_api_and_sup["agent_key_file"]
    gw_token_file = real_api_and_sup["gw_token_file"]
    root = real_api_and_sup["root"]
    env = real_api_and_sup["env"]

    browser_image, stream_image, engine_src, geoip_src = get_e2e_prerequisites()

    data_root = tmp_path / "data_root"
    data_root.mkdir()
    engine_cache = data_root / "engine_cache"
    shutil.copytree(engine_src, engine_cache)
    shutil.copytree(geoip_src, engine_cache / "geoip", dirs_exist_ok=True)
    env = dict(
        env,
        CBROWSER_BROWSER_IMAGE=browser_image,
        CBROWSER_STREAM_IMAGE=stream_image,
    )

    gateway = SupervisorGatewayFixture(
        port=gw_port,
        credentials=AgentCredentials(agent_key_file),
        token_file=gw_token_file,
    )
    await gateway.start()

    test_run_id = uuid.uuid4().hex[:6]
    prefix = f"t005-inv-{test_run_id}"
    d_client = docker.from_env()

    turn_image = os.environ.get(
        "CBROWSER_TURN_TEST_IMAGE",
        "sha256:e2bca2f79a4269d7240de5872ab60a9305013ad37296d2acf14f9510874346be",
    )
    d_client.images.get(turn_image)
    turn_config = data_root / "turn.conf"
    turn_config.write_text(
        "listening-port=3478\nrealm=cbrowser.local\nuse-auth-secret\n"
        "no-cli\nno-tls\nno-dtls\n"
        "static-auth-secret=" + secrets.token_hex(32) + "\n"
    )
    turn_config.chmod(0o644)
    coturn = d_client.containers.run(
        turn_image,
        name=f"{prefix}-coturn",
        detach=True,
        read_only=True,
        cap_drop=["ALL"],
        cap_add=["NET_BIND_SERVICE"],
        security_opt=["no-new-privileges:true"],
        tmpfs={"/tmp": "rw,size=256m"},
        entrypoint="/usr/bin/turnserver",
        command=[
            "-c",
            "/etc/turnserver.conf",
            "--relay-threads=1",
            "--log-file=stdout",
        ],
        volumes={str(turn_config): {"bind": "/etc/turnserver.conf", "mode": "ro"}},
        labels={
            "com.cbrowser.prefix": prefix,
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.role": "coturn",
        },
    )

    api_headers = {"Authorization": f"Bearer {sup_token}"}
    api_headers.update(real_api_and_sup["auth_headers"])

    # 1. Create two Profiles in API and set desired_state = running
    async with httpx.AsyncClient(
        base_url=api_url,
        headers=api_headers,
        trust_env=False,
    ) as api_client:
        r_a = await api_client.post(
            "/api/v1/profiles", json={"name": "Profile Inv A", "geoip": True}
        )
        assert r_a.status_code == 201
        p_a = r_a.json()["id"]
        await api_client.patch(
            f"/api/v1/profiles/{p_a}/runtime/desired-state",
            json={"desired_state": "running"},
        )

        r_b = await api_client.post(
            "/api/v1/profiles", json={"name": "Profile Inv B", "geoip": True}
        )
        assert r_b.status_code == 201
        p_b = r_b.json()["id"]
        await api_client.patch(
            f"/api/v1/profiles/{p_b}/runtime/desired-state",
            json={"desired_state": "running"},
        )

    sup_log = tmp_path / "supervisor_inv.log"
    sup_cmd = [
        sys.executable,
        "-m",
        "cbrowser.supervisor.runner",
        "--api-url",
        api_url,
        "--data-root",
        str(data_root),
        "--engine-cache",
        str(engine_cache),
        "--geoip-cache",
        str(engine_cache / "geoip"),
        "--token-file",
        str(sup_token_file),
        "--agent-key-file",
        str(agent_key_file),
        "--gateway-url",
        f"ws://host.docker.internal:{gw_port}",
        "--gateway-control-url",
        f"http://127.0.0.1:{gw_port}",
        "--gateway-token-file",
        str(gw_token_file),
        "--coturn-container-id",
        coturn.id,
        "--prefix",
        prefix,
        "--host",
        "127.0.0.1",
        "--port",
        str(sup_port),
    ]

    sup_proc = subprocess.Popen(
        sup_cmd, cwd=root, env=env, stdout=open(sup_log, "w"), stderr=subprocess.STDOUT
    )
    sup_url = f"http://127.0.0.1:{sup_port}"
    sup_headers = {"Authorization": f"Bearer {sup_token}"}

    created_containers = []
    try:
        async with httpx.AsyncClient(
            base_url=sup_url, headers=sup_headers, timeout=60.0, trust_env=False
        ) as sup_client:
            for _ in range(100):
                try:
                    if (
                        await sup_client.get("/supervisor/v1/health")
                    ).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.1)

            # Start Profile A (allocates 30000)
            res_a = await sup_client.post(
                "/supervisor/v1/profiles/start",
                json={"profile_id": p_a, "config_version": 1},
            )
            assert res_a.status_code == 200
            start_a = res_a.json()
            port_a = start_a["udp_mux_port"]
            inst_a = start_a["runtime_instance_id"]
            assert port_a == 30000
            created_containers.extend(
                [start_a["browser_container"], start_a["stream_container"]]
            )

            # Start Profile B (allocates 30001)
            res_b = await sup_client.post(
                "/supervisor/v1/profiles/start",
                json={"profile_id": p_b, "config_version": 1},
            )
            assert res_b.status_code == 200
            start_b = res_b.json()
            port_b = start_b["udp_mux_port"]
            inst_b = start_b["runtime_instance_id"]
            assert port_b == 30001
            created_containers.extend(
                [start_b["browser_container"], start_b["stream_container"]]
            )

        # 2. SIGKILL the Supervisor process
        sup_proc.send_signal(signal.SIGKILL)
        sup_proc.wait()

        # 3. Restart Supervisor process
        sup_proc2 = subprocess.Popen(
            sup_cmd,
            cwd=root,
            env=env,
            stdout=open(sup_log, "a"),
            stderr=subprocess.STDOUT,
        )

        async with httpx.AsyncClient(
            base_url=sup_url, headers=sup_headers, timeout=60.0, trust_env=False
        ) as sup_client2:
            for _ in range(100):
                try:
                    if (
                        await sup_client2.get("/supervisor/v1/health")
                    ).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.1)

            # Query status of both profiles: verify port invariance from HostConfig
            # (not scan order!)
            stat_a = (
                await sup_client2.get(f"/supervisor/v1/profiles/{p_a}/status")
            ).json()
            stat_b = (
                await sup_client2.get(f"/supervisor/v1/profiles/{p_b}/status")
            ).json()

            assert stat_a["observed_state"] == "running"
            assert stat_a["udp_mux_port"] == 30000
            assert stat_b["observed_state"] == "running"
            assert stat_b["udp_mux_port"] == 30001

            # Stop both cleanly
            await sup_client2.post(
                "/supervisor/v1/profiles/stop",
                json={
                    "profile_id": p_a,
                    "runtime_instance_id": inst_a,
                    "operation_id": f"stop-{p_a}",
                },
            )
            await sup_client2.post(
                "/supervisor/v1/profiles/stop",
                json={
                    "profile_id": p_b,
                    "runtime_instance_id": inst_b,
                    "operation_id": f"stop-{p_b}",
                },
            )

    finally:
        if "sup_proc2" in locals():
            sup_proc2.terminate()
            try:
                sup_proc2.wait(timeout=5)
            except subprocess.TimeoutExpired:
                sup_proc2.kill()
        await gateway.stop()
        if "coturn" in locals() and coturn is not None:
            try:
                coturn.remove(force=True)
            except Exception:
                pass
        for c in created_containers:
            try:
                d_client.containers.get(c).remove(force=True)
            except docker.errors.NotFound:
                pass
        for network in d_client.networks.list(
            filters={
                "label": [
                    f"com.cbrowser.prefix={prefix}",
                    "com.cbrowser.managed-by=supervisor",
                ]
            },
        ):
            network.remove()
        d_client.close()


@pytest.mark.asyncio
async def test_api_offline_event_spool_and_reconciliation_replay(
    tmp_path: Path, real_api_and_sup
):
    api_url = real_api_and_sup["api_url"]
    sup_port = real_api_and_sup["sup_port"]
    gw_port = real_api_and_sup["gw_port"]
    sup_token = real_api_and_sup["sup_token"]
    sup_token_file = real_api_and_sup["sup_token_file"]
    agent_key_file = real_api_and_sup["agent_key_file"]
    gw_token_file = real_api_and_sup["gw_token_file"]
    root = real_api_and_sup["root"]
    env = real_api_and_sup["env"]

    browser_image, stream_image, engine_src, geoip_src = get_e2e_prerequisites()

    data_root = tmp_path / "data_root"
    data_root.mkdir()
    engine_cache = data_root / "engine_cache"
    shutil.copytree(engine_src, engine_cache)
    shutil.copytree(geoip_src, engine_cache / "geoip", dirs_exist_ok=True)
    env = dict(
        env,
        CBROWSER_BROWSER_IMAGE=browser_image,
        CBROWSER_STREAM_IMAGE=stream_image,
    )

    gateway = SupervisorGatewayFixture(
        port=gw_port,
        credentials=AgentCredentials(agent_key_file),
        token_file=gw_token_file,
    )
    await gateway.start()

    test_run_id = uuid.uuid4().hex[:6]
    prefix = f"t005-off-{test_run_id}"
    d_client = docker.from_env()

    turn_image = os.environ.get(
        "CBROWSER_TURN_TEST_IMAGE",
        "sha256:e2bca2f79a4269d7240de5872ab60a9305013ad37296d2acf14f9510874346be",
    )
    d_client.images.get(turn_image)
    turn_config = data_root / "turn.conf"
    turn_config.write_text(
        "listening-port=3478\nrealm=cbrowser.local\nuse-auth-secret\n"
        "no-cli\nno-tls\nno-dtls\n"
        "static-auth-secret=" + secrets.token_hex(32) + "\n"
    )
    turn_config.chmod(0o644)
    coturn = d_client.containers.run(
        turn_image,
        name=f"{prefix}-coturn",
        detach=True,
        read_only=True,
        cap_drop=["ALL"],
        cap_add=["NET_BIND_SERVICE"],
        security_opt=["no-new-privileges:true"],
        tmpfs={"/tmp": "rw,size=256m"},
        entrypoint="/usr/bin/turnserver",
        command=[
            "-c",
            "/etc/turnserver.conf",
            "--relay-threads=1",
            "--log-file=stdout",
        ],
        volumes={str(turn_config): {"bind": "/etc/turnserver.conf", "mode": "ro"}},
        labels={
            "com.cbrowser.prefix": prefix,
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.role": "coturn",
        },
    )

    api_headers = {"Authorization": f"Bearer {sup_token}"}
    api_headers.update(real_api_and_sup["auth_headers"])

    # 1. Create Profile in API
    async with httpx.AsyncClient(
        base_url=api_url,
        headers=api_headers,
        trust_env=False,
    ) as api_client:
        r_create = await api_client.post(
            "/api/v1/profiles", json={"name": "Offline Spool Profile", "geoip": True}
        )
        assert r_create.status_code == 201
        profile_id = r_create.json()["id"]
        await api_client.patch(
            f"/api/v1/profiles/{profile_id}/runtime/desired-state",
            json={"desired_state": "running"},
        )

    sup_log = tmp_path / "supervisor_offline.log"
    sup_cmd = [
        sys.executable,
        "-m",
        "cbrowser.supervisor.runner",
        "--api-url",
        api_url,
        "--data-root",
        str(data_root),
        "--engine-cache",
        str(engine_cache),
        "--geoip-cache",
        str(engine_cache / "geoip"),
        "--token-file",
        str(sup_token_file),
        "--agent-key-file",
        str(agent_key_file),
        "--gateway-url",
        f"ws://host.docker.internal:{gw_port}",
        "--gateway-control-url",
        f"http://127.0.0.1:{gw_port}",
        "--gateway-token-file",
        str(gw_token_file),
        "--coturn-container-id",
        coturn.id,
        "--prefix",
        prefix,
        "--host",
        "127.0.0.1",
        "--port",
        str(sup_port),
    ]

    sup_proc = subprocess.Popen(
        sup_cmd, cwd=root, env=env, stdout=open(sup_log, "w"), stderr=subprocess.STDOUT
    )
    sup_url = f"http://127.0.0.1:{sup_port}"
    sup_headers = {"Authorization": f"Bearer {sup_token}"}

    created_containers = []
    try:
        async with httpx.AsyncClient(
            base_url=sup_url, headers=sup_headers, timeout=60.0, trust_env=False
        ) as sup_client:
            for _ in range(100):
                try:
                    if (
                        await sup_client.get("/supervisor/v1/health")
                    ).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.1)

            # Start Profile
            res = await sup_client.post(
                "/supervisor/v1/profiles/start",
                json={"profile_id": profile_id, "config_version": 1},
            )
            assert res.status_code == 200
            b_cname = res.json()["browser_container"]
            s_cname = res.json()["stream_container"]
            inst_id = res.json()["runtime_instance_id"]
            created_containers.extend([b_cname, s_cname])

        # 2. Simulate offline event queueing in spool directory
        spool_dir = data_root / "spool"
        spool_dir.mkdir(parents=True, exist_ok=True)
        evt_id = f"evt_offline_{uuid.uuid4().hex[:8]}"
        spool_file = spool_dir / f"{evt_id}.json"
        event_payload = {
            "event_id": evt_id,
            "profile_id": profile_id,
            "runtime_instance_id": inst_id,
            "event_type": "exit",
            "exit_code": 0,
            "exit_reason": "normal",
            "config_version": 1,
            "payload": {},
        }
        spool_file.write_text(json.dumps(event_payload), encoding="utf-8")

        # 3. Wait for supervisor background monitoring loop to pick up and forward
        # the spooled event to API
        async with httpx.AsyncClient(
            base_url=api_url,
            headers=api_headers,
            trust_env=False,
        ) as api_client:
            for _ in range(30):
                if not spool_file.exists():
                    break
                await asyncio.sleep(0.5)

            assert not spool_file.exists(), (
                "Spooled event must be consumed and deleted upon successful "
                "API delivery"
            )

            # Disk events are diagnostics: a synthetic exit while the real
            # Browser container keeps running must not clear running intent.
            r_rt = await api_client.get(
                f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime"
            )
            assert r_rt.status_code == 200
            assert r_rt.json()["desired_state"] == "running"
            assert r_rt.json()["runtime_instance_id"] == inst_id

            # 4. Idempotency test: Replay the identical event
            r_dup = await api_client.post(
                "/api/v1/internal/supervisor/runtimes/events", json=event_payload
            )
            assert r_dup.status_code == 200
            dup_data = r_dup.json()
            assert dup_data["status"] == "ok"
            assert dup_data["outcome"] == "duplicate"

            # Verify that replaying duplicate event does NOT clear the new running
            # intent!
            r_rt2 = await api_client.get(
                f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime"
            )
            assert r_rt2.json()["desired_state"] == "running"

    finally:
        sup_proc.terminate()
        try:
            sup_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            sup_proc.kill()
        await gateway.stop()
        if "coturn" in locals() and coturn is not None:
            try:
                coturn.remove(force=True)
            except Exception:
                pass
        for c in created_containers:
            try:
                d_client.containers.get(c).remove(force=True)
            except docker.errors.NotFound:
                pass
        for network in d_client.networks.list(
            filters={
                "label": [
                    f"com.cbrowser.prefix={prefix}",
                    "com.cbrowser.managed-by=supervisor",
                ]
            },
        ):
            network.remove()
        d_client.close()
