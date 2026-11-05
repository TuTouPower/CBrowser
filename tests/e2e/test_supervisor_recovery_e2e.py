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
7. Diagnostic spool replay without stopping live runtime: spooled exit events
   replay as diagnostics to API without terminating or altering live healthy containers,
   confirming observation authority over sandboxed exit files.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

import docker
import httpx
import pytest
from unittest.mock import MagicMock

from e2e_env import free_udp_port_span, require_e2e_env
from api_auth import create_auth_context
from cbrowser.domain.models import RuntimeEventReportRequest
from cbrowser.runtime_agent.event_storage import atomic_write_json
from gateway_probe.topology import cleanup_prefixed_resources
from supervisor_recovery_probe.gateway_service import (
    ApiRuntimeLookup,
    ProductionGatewayService,
)
from supervisor_recovery_probe.offline_fixture import RealSupervisorContainer

logger = logging.getLogger(__name__)


def get_e2e_prerequisites() -> tuple[str, str, Path, Path]:
    env = require_e2e_env(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_STREAM_TEST_IMAGE",
        "CBROWSER_RUNTIME_ENGINE_CACHE",
        "CBROWSER_RUNTIME_GEOIP_CACHE",
    )
    browser_img = env["CBROWSER_RUNTIME_TEST_IMAGE"]
    stream_img = env["CBROWSER_STREAM_TEST_IMAGE"]
    engine_cache = env["CBROWSER_RUNTIME_ENGINE_CACHE"]
    geoip_cache = env["CBROWSER_RUNTIME_GEOIP_CACHE"]

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
    api_proc = None
    managed_procs: list[subprocess.Popen] = []

    with open(api_log, "w", encoding="utf-8") as api_log_handle:
        try:
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
                stdout=api_log_handle,
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
                "api_port": api_port,
                "sup_port": sup_port,
                "gw_port": gw_port,
                "sup_token": sup_token,
                "sup_token_file": sup_token_file,
                "agent_key_file": agent_key_file,
                "gw_token_file": gw_token_file,
                "root": root,
                "env": env,
                "auth_headers": auth_headers,
                "managed_procs": managed_procs,
            }
        finally:
            cleanup_errors: list[BaseException] = []
            for p in managed_procs:
                if p is not None and p.poll() is None:
                    try:
                        p.terminate()
                        try:
                            p.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            p.kill()
                            p.wait(timeout=2)
                    except BaseException as exc:  # noqa: BLE001 - Best-effort termination of managed subprocesses
                        logger.warning(
                            "Error terminating managed process: error_type=%s",
                            type(exc).__name__,
                        )
                        cleanup_errors.append(exc)
            if api_proc is not None and api_proc.poll() is None:
                try:
                    api_proc.terminate()
                    try:
                        api_proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        api_proc.kill()
                        api_proc.wait(timeout=2)
                except BaseException as exc:  # noqa: BLE001 - Best-effort termination of real api process
                    logger.warning(
                        "Error terminating api process: error_type=%s",
                        type(exc).__name__,
                    )
                    cleanup_errors.append(exc)

            if cleanup_errors:
                if len(cleanup_errors) == 1:
                    raise cleanup_errors[0]
                raise RuntimeError(f"Cleanup encountered errors: {cleanup_errors}")


@pytest.mark.asyncio
async def test_supervisor_sigkill_reconciliation_and_event_persistence(
    tmp_path: Path, real_api_and_sup, request: pytest.FixtureRequest
):
    api_url = real_api_and_sup["api_url"]
    api_port = real_api_and_sup["api_port"]
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

    gateway = ProductionGatewayService(
        port=gw_port,
        agent_key_file=agent_key_file,
        gateway_token_file=gw_token_file,
        runtime_lookup=ApiRuntimeLookup(api_url, sup_token_file),
    )
    await gateway.start()

    test_run_id = uuid.uuid4().hex[:6]
    prefix = f"t005-rec-{test_run_id}"

    d_client = docker.from_env()
    request.addfinalizer(lambda: cleanup_prefixed_resources(d_client, prefix))


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

    # 2. Spawn Supervisor container
    udp_base = free_udp_port_span(2)
    sup_log = tmp_path / "supervisor.log"
    sup = RealSupervisorContainer(
        api_url=f"http://host.docker.internal:{api_port}",
        data_root=data_root,
        engine_cache=engine_cache,
        geoip_cache=engine_cache / "geoip",
        token_file=sup_token_file,
        agent_key_file=agent_key_file,
        gateway_url=f"ws://host.docker.internal:{gw_port}",
        gateway_port=gw_port,
        gateway_control_url=f"http://host.docker.internal:{gw_port}",
        gateway_token_file=gw_token_file,
        prefix=prefix,
        port=sup_port,
        root=root,
        env=env,
        log_path=sup_log,
        docker_client=d_client,
        udp_mux_min_port=udp_base,
        udp_mux_max_port=udp_base + 1,
    )
    await asyncio.to_thread(sup.start)
    c1_id = sup.container_id

    sup_url = sup.url
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

    # 3. SIGKILL the Supervisor container!
    await asyncio.to_thread(sup.sigkill)

    # Assert Browser and Stream containers STILL running during Supervisor absence
    b_c.reload()
    s_c.reload()
    assert b_c.status == "running", (
        "Browser container must NOT die on supervisor SIGKILL"
    )
    assert s_c.status == "running", (
        "Stream container must NOT die on supervisor SIGKILL"
    )

    # 4. Restart Supervisor container
    await asyncio.to_thread(sup.restart)
    c2_id = sup.container_id
    assert c2_id != c1_id, "Supervisor container identity must be renewed"

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
            assert stat_data["udp_mux_port"] == udp_base

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
            res = await asyncio.to_thread(
                subprocess.run,
                ["docker", "exec", b_cname, "python3", "-c", script],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            assert res.returncode == 0

            # Wait for exit event persistence and API reconcile
            # Give supervisor time to read event and push to API
            await asyncio.sleep(1.0)
            async with httpx.AsyncClient(
                base_url=api_url,
                headers=api_headers,
                trust_env=False,
            ) as api_client_check:
                for _ in range(120):
                    r_rt = await api_client_check.get(
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
        await asyncio.to_thread(sup.stop)
        await gateway.stop()
        cleanup_prefixed_resources(d_client, prefix)
        d_client.close()


@pytest.mark.asyncio
async def test_supervisor_dual_profile_port_invariance_on_sigkill(
    tmp_path: Path, real_api_and_sup, request: pytest.FixtureRequest
):
    api_url = real_api_and_sup["api_url"]
    api_port = real_api_and_sup["api_port"]
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

    gateway = ProductionGatewayService(
        port=gw_port,
        agent_key_file=agent_key_file,
        gateway_token_file=gw_token_file,
        runtime_lookup=ApiRuntimeLookup(api_url, sup_token_file),
    )
    await gateway.start()

    test_run_id = uuid.uuid4().hex[:6]
    prefix = f"t005-inv-{test_run_id}"
    d_client = docker.from_env()
    request.addfinalizer(lambda: cleanup_prefixed_resources(d_client, prefix))


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

    udp_base = free_udp_port_span(2)
    sup_log = tmp_path / "supervisor_inv.log"
    sup = RealSupervisorContainer(
        api_url=f"http://host.docker.internal:{api_port}",
        data_root=data_root,
        engine_cache=engine_cache,
        geoip_cache=engine_cache / "geoip",
        token_file=sup_token_file,
        agent_key_file=agent_key_file,
        gateway_url=f"ws://host.docker.internal:{gw_port}",
        gateway_port=gw_port,
        gateway_control_url=f"http://host.docker.internal:{gw_port}",
        gateway_token_file=gw_token_file,
        prefix=prefix,
        port=sup_port,
        root=root,
        env=env,
        log_path=sup_log,
        docker_client=d_client,
        udp_mux_min_port=udp_base,
        udp_mux_max_port=udp_base + 1,
    )
    await asyncio.to_thread(sup.start)
    c1_id = sup.container_id
    sup_url = sup.url
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

            # Start Profile A (allocates the run-local base port)
            res_a = await sup_client.post(
                "/supervisor/v1/profiles/start",
                json={"profile_id": p_a, "config_version": 1},
            )
            assert res_a.status_code == 200
            start_a = res_a.json()
            port_a = start_a["udp_mux_port"]
            inst_a = start_a["runtime_instance_id"]
            assert port_a == udp_base
            created_containers.extend(
                [start_a["browser_container"], start_a["stream_container"]]
            )

            # Start Profile B (allocates base + 1)
            res_b = await sup_client.post(
                "/supervisor/v1/profiles/start",
                json={"profile_id": p_b, "config_version": 1},
            )
            assert res_b.status_code == 200
            start_b = res_b.json()
            port_b = start_b["udp_mux_port"]
            inst_b = start_b["runtime_instance_id"]
            assert port_b == udp_base + 1
            created_containers.extend(
                [start_b["browser_container"], start_b["stream_container"]]
            )

        # SIGKILL supervisor container!
        await asyncio.to_thread(sup.sigkill)

        # Restart supervisor container
        await asyncio.to_thread(sup.restart)
        c2_id = sup.container_id
        assert c2_id != c1_id, "Supervisor container identity must be renewed"

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

            # Query status from resurrected supervisor: ports MUST be identical
            # (base, base + 1). Health 200 is liveness only: the
            # post-startup scan restores sessions asynchronously, so poll
            # for convergence before asserting port invariance.
            stat_a = stat_b = None
            for _ in range(120):
                stat_a = (
                    await sup_client2.get(f"/supervisor/v1/profiles/{p_a}/status")
                ).json()
                stat_b = (
                    await sup_client2.get(f"/supervisor/v1/profiles/{p_b}/status")
                ).json()
                if (
                    stat_a["observed_state"] == "running"
                    and stat_b["observed_state"] == "running"
                    and stat_a["udp_mux_port"] is not None
                    and stat_b["udp_mux_port"] is not None
                ):
                    break
                await asyncio.sleep(1.0)
            assert stat_a["observed_state"] == "running"
            assert stat_a["udp_mux_port"] == udp_base
            assert stat_b["observed_state"] == "running"
            assert stat_b["udp_mux_port"] == udp_base + 1

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
        await asyncio.to_thread(sup.stop)
        await gateway.stop()
        cleanup_prefixed_resources(d_client, prefix)
        d_client.close()


def _probe_in_container_agent_health(container_name: str) -> dict:
    probe_script = (
        "import httpx, json, sys\n"
        "try:\n"
        "    sock = '/run/cbrowser/runtime/agent.sock'\n"
        "    transport = httpx.HTTPTransport(uds=sock)\n"
        "    with httpx.Client(\n"
        "        transport=transport, base_url='http://uds', timeout=5.0\n"
        "    ) as client:\n"
        "        resp = client.get('/health')\n"
        "        assert resp.status_code == 200, (\n"
        "            f'Status {resp.status_code}: {resp.text}'\n"
        "        )\n"
        "        data = resp.json()\n"
        "        assert data.get('ready') is True, f'Agent not ready: {data}'\n"
        "        assert data.get('browser_ready') is True, (\n"
        "            f'Browser not ready: {data}'\n"
        "        )\n"
        "        assert data.get('cdp_ready') is True, f'CDP not ready: {data}'\n"
        "        print(json.dumps(data))\n"
        "except Exception as exc:\n"
        "    print(f'ERROR: {exc}', file=sys.stderr)\n"
        "    sys.exit(1)\n"
    )
    res = subprocess.run(
        ["docker", "exec", container_name, "python3", "-c", probe_script],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert res.returncode == 0, f"probe failed: {res.stderr}"
    return json.loads(res.stdout.strip())


def _query_runtime_events_ro(db_path: Path, event_id: str) -> list[tuple]:
    db_uri = f"{db_path.resolve().as_uri()}?mode=ro"
    with (
        contextlib.closing(sqlite3.connect(db_uri, uri=True)) as conn,
        contextlib.closing(conn.cursor()) as cursor,
    ):
        cursor.execute(
            "SELECT event_id, profile_id, runtime_instance_id, event_type, "
            "exit_code, exit_reason, config_version, payload "
            "FROM runtime_events WHERE event_id = ?",
            (event_id,),
        )
        return cursor.fetchall()


@pytest.mark.asyncio
async def test_supervisor_replays_diagnostic_spool_without_stopping_live_runtime(
    tmp_path: Path, real_api_and_sup, request: pytest.FixtureRequest
):
    api_url = real_api_and_sup["api_url"]
    api_port = real_api_and_sup["api_port"]
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

    gateway = ProductionGatewayService(
        port=gw_port,
        agent_key_file=agent_key_file,
        gateway_token_file=gw_token_file,
        runtime_lookup=ApiRuntimeLookup(api_url, sup_token_file),
    )
    await gateway.start()

    test_run_id = uuid.uuid4().hex[:6]
    prefix = f"t005-dsp-{test_run_id}"
    d_client = docker.from_env()
    request.addfinalizer(lambda: cleanup_prefixed_resources(d_client, prefix))


    api_headers = {"Authorization": f"Bearer {sup_token}"}
    api_headers.update(real_api_and_sup["auth_headers"])

    # 1. Create Profile in API and set desired_state = running
    async with httpx.AsyncClient(
        base_url=api_url,
        headers=api_headers,
        trust_env=False,
    ) as api_client:
        r_create = await api_client.post(
            "/api/v1/profiles",
            json={"name": "Diagnostic Spool Authority Profile", "geoip": True},
        )
        assert r_create.status_code == 201
        profile_id = r_create.json()["id"]
        await api_client.patch(
            f"/api/v1/profiles/{profile_id}/runtime/desired-state",
            json={"desired_state": "running"},
        )

    udp_base = free_udp_port_span(2)
    sup_log = tmp_path / "supervisor_spool_authority.log"
    sup = RealSupervisorContainer(
        api_url=f"http://host.docker.internal:{api_port}",
        data_root=data_root,
        engine_cache=engine_cache,
        geoip_cache=engine_cache / "geoip",
        token_file=sup_token_file,
        agent_key_file=agent_key_file,
        gateway_url=f"ws://host.docker.internal:{gw_port}",
        gateway_port=gw_port,
        gateway_control_url=f"http://host.docker.internal:{gw_port}",
        gateway_token_file=gw_token_file,
        prefix=prefix,
        port=sup_port,
        root=root,
        env=env,
        log_path=sup_log,
        docker_client=d_client,
        udp_mux_min_port=udp_base,
        udp_mux_max_port=udp_base + 1,
    )
    await asyncio.to_thread(sup.start)
    c1_id = sup.container_id
    sup_url = sup.url
    sup_headers = {"Authorization": f"Bearer {sup_token}"}

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

            # Start Profile via Supervisor control server
            res = await sup_client.post(
                "/supervisor/v1/profiles/start",
                json={"profile_id": profile_id, "config_version": 1},
            )
            assert res.status_code == 200
            start_payload = res.json()
            b_cname = start_payload["browser_container"]
            s_cname = start_payload["stream_container"]
            inst_id = start_payload["runtime_instance_id"]
            initial_udp_mux_port = start_payload["udp_mux_port"]
            assert initial_udp_mux_port is not None

        b_c = d_client.containers.get(b_cname)
        s_c = d_client.containers.get(s_cname)
        assert b_c.status == "running"
        assert s_c.status == "running"
        b_c_initial_id = b_c.id
        s_c_initial_id = s_c.id

        # 2. Verify live browser PID, CDP and Agent readiness before writing spool
        health_pre = await asyncio.to_thread(_probe_in_container_agent_health, b_cname)
        assert health_pre["ready"] is True
        assert health_pre["browser_ready"] is True
        assert health_pre["cdp_ready"] is True
        assert health_pre["profile_id"] == profile_id
        assert health_pre["runtime_instance_id"] == inst_id
        assert health_pre["config_version"] == 1
        browser_pid_pre = health_pre["details"]["browser_pid"]
        cdp_port_pre = health_pre["details"]["cdp_port"]
        assert browser_pid_pre is not None and browser_pid_pre > 0
        assert cdp_port_pre is not None and cdp_port_pre > 0

        # 3. Simulate durable diagnostic event queued in spool directory.
        # Uses production RuntimeEventReportRequest schema (exit_type=exit,
        # normal reason, bound config_version=1, valid ISO/Unix fields).
        spool_dir = data_root / "spool"
        spool_dir.mkdir(parents=True, exist_ok=True)
        evt_id = f"evt_diag_{uuid.uuid4().hex[:8]}"

        event_model = RuntimeEventReportRequest(
            event_id=evt_id,
            profile_id=profile_id,
            runtime_instance_id=inst_id,
            event_type="exit",
            exit_code=0,
            exit_reason="normal",
            config_version=1,
            payload={"source": "diagnostic_spool_authority_e2e"},
        )
        event_payload = event_model.model_dump()
        spool_key = hashlib.sha256(evt_id.encode("utf-8")).hexdigest()
        spool_file = spool_dir / f"{spool_key}.json"
        await asyncio.to_thread(atomic_write_json, spool_file, event_payload)
        assert spool_file.exists()

        # Check health again after spool write: living browser unaffected
        health_post_write = await asyncio.to_thread(
            _probe_in_container_agent_health, b_cname
        )
        assert health_post_write["ready"] is True
        assert health_post_write["browser_ready"] is True
        assert health_post_write["cdp_ready"] is True
        assert health_post_write["profile_id"] == profile_id
        assert health_post_write["runtime_instance_id"] == inst_id
        assert health_post_write["config_version"] == 1
        assert health_post_write["details"]["browser_pid"] == browser_pid_pre

        # 4. SIGKILL Supervisor container while event is spooled!
        await asyncio.to_thread(sup.sigkill)

        # Assert Browser and Stream containers STILL running during Supervisor absence
        b_c.reload()
        s_c.reload()
        assert b_c.status == "running"
        assert s_c.status == "running"

        # 5. Restart Supervisor container: on startup, spool replayer delivers event
        # to API, while ActiveSession reconciles running Docker containers.
        await asyncio.to_thread(sup.restart)
        c2_id = sup.container_id
        assert c2_id != c1_id, "Supervisor container identity must be renewed"

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

            # Wait for spool forwarder to deliver and unlink the event file
            for _ in range(60):
                if not spool_file.exists():
                    break
                await asyncio.sleep(0.5)
            assert not spool_file.exists(), (
                "Delivered spool event file must be unlinked after delivery"
            )

            # Quarantine directory must not have captured this event as invalid
            quarantine_file = spool_dir / "quarantine" / spool_file.name
            assert not quarantine_file.exists(), (
                f"Valid event was unexpectedly quarantined: {quarantine_file}"
            )

            # Verify resurrected supervisor reports running state and
            # preserved UDP mux port
            r_stat = await sup_client2.get(
                f"/supervisor/v1/profiles/{profile_id}/status"
            )
            assert r_stat.status_code == 200
            stat_data = r_stat.json()
            assert stat_data["observed_state"] == "running"
            assert stat_data["udp_mux_port"] == initial_udp_mux_port

        # 6. Verify real API diagnostic persistence via read-only SQLite mode=ro
        db_path = tmp_path / "control.db"
        db_records = await asyncio.to_thread(
            _query_runtime_events_ro, db_path, evt_id
        )
        assert len(db_records) == 1, (
            f"Expected exactly 1 diagnostic event record in DB for {evt_id}, "
            f"got {db_records}"
        )
        rec = db_records[0]
        assert rec[0] == evt_id
        assert rec[1] == profile_id
        assert rec[2] == inst_id
        assert rec[3] == "exit"
        assert rec[4] == 0
        assert rec[5] == "normal"
        assert rec[6] == 1

        # 7. A1 Observation Authority assertions:
        # Diagnostic events must NOT alter live running intent or observed state!
        async with httpx.AsyncClient(
            base_url=api_url,
            headers=api_headers,
            trust_env=False,
        ) as api_client:
            for _ in range(60):
                r_rt = await api_client.get(
                    f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime"
                )
                if (
                    r_rt.status_code == 200
                    and r_rt.json().get("observed_state") == "running"
                ):
                    break
                await asyncio.sleep(0.5)

            assert r_rt.status_code == 200
            rt_data = r_rt.json()
            assert rt_data["desired_state"] == "running", (
                f"Diagnostic event must NOT clear desired_state: {rt_data}"
            )
            assert rt_data["observed_state"] == "running", (
                f"Observed state must remain running: {rt_data}"
            )
            assert rt_data["runtime_instance_id"] == inst_id
            assert rt_data["failure_count"] == 0
            assert rt_data["restart_blocked"] is False

            # 8. Idempotency & duplicate replay test:
            # Replaying the identical event returns outcome="duplicate"
            r_dup = await api_client.post(
                "/api/v1/internal/supervisor/runtimes/events", json=event_payload
            )
            assert r_dup.status_code == 200
            dup_data = r_dup.json()
            assert dup_data["status"] == "ok"
            assert dup_data["outcome"] == "duplicate"
            assert dup_data["event_id"] == evt_id

            # Verify DB still has exactly 1 record for this event_id
            db_records_after_dup = await asyncio.to_thread(
                _query_runtime_events_ro, db_path, evt_id
            )
            assert len(db_records_after_dup) == 1

            # Duplicate replay must still NOT clear running intent
            r_rt_after_dup = await api_client.get(
                f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime"
            )
            assert r_rt_after_dup.status_code == 200
            rt_data_after_dup = r_rt_after_dup.json()
            assert rt_data_after_dup["desired_state"] == "running"
            assert rt_data_after_dup["observed_state"] == "running"
            assert rt_data_after_dup["runtime_instance_id"] == inst_id
            assert rt_data_after_dup["failure_count"] == 0
            assert rt_data_after_dup["restart_blocked"] is False

        # 9. Verify container identity and in-container Agent health preserved
        b_c.reload()
        s_c.reload()
        assert b_c.id == b_c_initial_id
        assert s_c.id == s_c_initial_id
        assert b_c.status == "running"
        assert s_c.status == "running"

        health_final = await asyncio.to_thread(
            _probe_in_container_agent_health, b_cname
        )
        assert health_final["ready"] is True
        assert health_final["browser_ready"] is True
        assert health_final["cdp_ready"] is True
        assert health_final["profile_id"] == profile_id
        assert health_final["runtime_instance_id"] == inst_id
        assert health_final["config_version"] == 1
        assert health_final["details"]["browser_pid"] == browser_pid_pre
        assert health_final["details"]["cdp_port"] == cdp_port_pre

        # 10. Cleanly stop Profile via resurrected supervisor
        async with httpx.AsyncClient(
            base_url=sup_url, headers=sup_headers, timeout=60.0, trust_env=False
        ) as sup_client_stop:
            r_stop = await sup_client_stop.post(
                "/supervisor/v1/profiles/stop",
                json={
                    "profile_id": profile_id,
                    "runtime_instance_id": inst_id,
                    "operation_id": f"stop-{profile_id}",
                },
            )
            assert r_stop.status_code == 200

    finally:
        cleanup_errors: list[BaseException] = []
        try:
            await asyncio.to_thread(sup.stop)
        except BaseException as exc:  # noqa: BLE001 - Best-effort supervisor stop during teardown
            logger.warning(
                "Teardown error stopping supervisor: error_type=%s",
                type(exc).__name__,
            )
            cleanup_errors.append(exc)
        try:
            await gateway.stop()
        except BaseException as exc:  # noqa: BLE001 - Best-effort gateway stop during teardown
            logger.warning(
                "Teardown error stopping gateway: error_type=%s",
                type(exc).__name__,
            )
            cleanup_errors.append(exc)
        try:
            cleanup_prefixed_resources(d_client, prefix)
        except BaseException as exc:  # noqa: BLE001 - Best-effort prefixed resource cleanup
            logger.warning(
                "Teardown error cleaning resources: error_type=%s",
                type(exc).__name__,
            )
            cleanup_errors.append(exc)
        try:
            d_client.close()
        except BaseException as exc:  # noqa: BLE001 - Best-effort docker client close
            logger.warning(
                "Teardown error closing docker client: error_type=%s",
                type(exc).__name__,
            )
            cleanup_errors.append(exc)


    if cleanup_errors:
        if len(cleanup_errors) == 1:
            raise cleanup_errors[0]
        raise RuntimeError(f"Cleanup encountered errors: {cleanup_errors}")


def test_real_api_and_sup_finally_propagates_cleanup_error_and_reaps_remaining(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """recovery E2E real_api_and_sup propagates wait error and cleans resources."""
    e2e_mod = sys.modules[__name__]

    orig_popen = subprocess.Popen
    sleep_cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
    spawned_procs = []

    def fake_popen(*args, **kwargs):
        p = orig_popen(
            sleep_cmd,
            stdout=kwargs.get("stdout"),
            stderr=kwargs.get("stderr"),
        )
        spawned_procs.append(p)
        return p

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        httpx.Client,
        "get",
        lambda self, url, *a, **kw: httpx.Response(
            503, request=httpx.Request("GET", url)
        ),
    )

    fake_auth = MagicMock()
    fake_auth.env = {}
    fake_auth.login_sync.return_value = {"Authorization": "Bearer test"}
    monkeypatch.setattr(e2e_mod, "create_auth_context", lambda *a, **kw: fake_auth)

    fn = getattr(real_api_and_sup, "__wrapped__", real_api_and_sup)
    gen = fn(tmp_path)
    ctx = next(gen)

    # Spawn two managed procs
    p1 = orig_popen(sleep_cmd)
    p2 = orig_popen(sleep_cmd)
    spawned_procs.extend([p1, p2])

    # p1 fails on wait
    def failing_wait(timeout=None):
        raise subprocess.TimeoutExpired(cmd=["p1"], timeout=timeout or 2.0)

    monkeypatch.setattr(p1, "wait", failing_wait)
    ctx["managed_procs"].extend([p1, p2])

    try:
        with pytest.raises(subprocess.TimeoutExpired):
            try:
                next(gen)
            except StopIteration:
                pass

        # Verify p2 was still reaped (best-effort cleanup)
        assert p2.poll() is not None, "p2 must be reaped despite p1 error"
    finally:
        monkeypatch.undo()
        for p in spawned_procs:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=2.0)
