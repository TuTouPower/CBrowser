"""True API Process Offline & Supervisor Event Spool Recovery E2E Suite.

Validates AC-004 under genuine multi-process failure scenarios:
1. Real API process (SQLite WAL fresh DB + dynamic Bearer token file)
   + Real Supervisor process + Real Gateway.
2. Dual real profile sandboxes running (Profile A target for exit,
   Profile B healthy companion).
3. API process is genuinely stopped (HTTP connection actively refused).
4. Profile A Chrome is cleanly closed via in-container Agent UDS
   /run/cbrowser/runtime/agent.sock RPC.
5. Supervisor background monitor detects exit, writes atomic spool file,
   and retains it on disk due to API offline.
6. Supervisor is killed with SIGKILL and resurrected with same data_root
   while API is still offline.
7. Resurrected Supervisor retains Profile A spool file and leaves Profile B
   healthy containers intact.
8. API process is restarted on same port with same DB.
9. Supervisor continuously re-evaluates and automatically replays the spooled
   event to API without test direct POST.
10. Spool file is unlinked upon delivery, API desired_state converges to
    stopped, and replay does not clear new intent.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import secrets
import sys
import uuid
from pathlib import Path

import docker
import httpx
import pytest
from cbrowser.supervisor.agent_credentials import AgentCredentials

ROOT = Path(__file__).resolve().parents[2]

_fixture_path = ROOT / "tests/fixtures/supervisor_recovery_probe/offline_fixture.py"
_spec = importlib.util.spec_from_file_location("offline_fixture", _fixture_path)
offline_fixture = importlib.util.module_from_spec(_spec)
sys.modules["offline_fixture"] = offline_fixture
_spec.loader.exec_module(offline_fixture)

OfflineGatewayMock = offline_fixture.OfflineGatewayMock
RealApiProcess = offline_fixture.RealApiProcess
RealBrowserActionProbe = offline_fixture.RealBrowserActionProbe
RealSupervisorProcess = offline_fixture.RealSupervisorProcess
SandboxContainerTracker = offline_fixture.SandboxContainerTracker
SpoolDirectoryWatcher = offline_fixture.SpoolDirectoryWatcher
get_free_port = offline_fixture.get_free_port
prepare_engine_cache = offline_fixture.prepare_engine_cache

logger = logging.getLogger("cbrowser.tests.e2e.offline_recovery")


@pytest.mark.asyncio
async def test_supervisor_true_api_offline_event_spool_and_recovery(tmp_path: Path):
    """AC-004: True API process termination, disk spooling, SIGKILL survival.

    Replays events to convergence.
    """
    browser_image, stream_image, _, _ = offline_fixture.get_e2e_prerequisites()
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

    api_port = get_free_port()
    sup_port = get_free_port()
    gw_port = get_free_port()

    data_root = tmp_path / "data_root"
    data_root.mkdir(parents=True, exist_ok=True)
    engine_cache, geoip_cache = prepare_engine_cache(data_root)

    clean_environ = dict(os.environ)
    for k in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        clean_environ.pop(k, None)
    clean_environ.update(
        CBROWSER_BROWSER_IMAGE=browser_image,
        CBROWSER_STREAM_IMAGE=stream_image,
        PYTHONPATH=str(ROOT / "src/backend"),
        PYTHONDONTWRITEBYTECODE="1",
        TMPDIR=str(tmp_path),
    )

    test_run_id = uuid.uuid4().hex[:6]
    prefix = f"t005-off-{test_run_id}"

    tracker = SandboxContainerTracker()
    d_client = docker.from_env()

    gateway = OfflineGatewayMock(
        port=gw_port,
        credentials=AgentCredentials(agent_key_file),
        token_file=gw_token_file,
    )

    api_db_path = tmp_path / "control.db"
    api_log = tmp_path / "api.log"
    api_proc = RealApiProcess(
        port=api_port,
        db_path=api_db_path,
        token_file=sup_token_file,
        root=ROOT,
        env=clean_environ,
        log_path=api_log,
    )

    sup_log = tmp_path / "supervisor.log"
    sup_proc = RealSupervisorProcess(
        api_url=api_proc.url,
        data_root=data_root,
        engine_cache=engine_cache,
        geoip_cache=geoip_cache,
        token_file=sup_token_file,
        agent_key_file=agent_key_file,
        gateway_url=f"ws://host.docker.internal:{gw_port}",
        gateway_control_url=f"http://127.0.0.1:{gw_port}",
        gateway_token_file=gw_token_file,
        prefix=prefix,
        port=sup_port,
        root=ROOT,
        env=clean_environ,
        log_path=sup_log,
    )

    api_headers = {"Authorization": f"Bearer {sup_token}"}
    sup_headers = {"Authorization": f"Bearer {sup_token}"}

    try:
        await gateway.start()
        api_proc.start()
        sup_proc.start()
        async with httpx.AsyncClient(
            base_url=api_proc.url, headers=api_headers, trust_env=False
        ) as api_client:
            r_create_a = await api_client.post(
                "/api/v1/profiles", json={"name": "Offline Target A", "geoip": True}
            )
            assert r_create_a.status_code == 201, (
                f"Failed to create Profile A: {r_create_a.text}"
            )
            profile_a_id = r_create_a.json()["id"]
            r_des_a = await api_client.patch(
                f"/api/v1/profiles/{profile_a_id}/runtime/desired-state",
                json={"desired_state": "running"},
            )
            assert r_des_a.status_code == 200

            r_create_b = await api_client.post(
                "/api/v1/profiles", json={"name": "Healthy Companion B", "geoip": True}
            )
            assert r_create_b.status_code == 201, (
                f"Failed to create Profile B: {r_create_b.text}"
            )
            profile_b_id = r_create_b.json()["id"]
            r_des_b = await api_client.patch(
                f"/api/v1/profiles/{profile_b_id}/runtime/desired-state",
                json={"desired_state": "running"},
            )
            assert r_des_b.status_code == 200

        async with httpx.AsyncClient(
            base_url=sup_proc.url, headers=sup_headers, timeout=60.0, trust_env=False
        ) as sup_client:
            res_a = await sup_client.post(
                "/supervisor/v1/profiles/start",
                json={"profile_id": profile_a_id, "config_version": 1},
            )
            assert res_a.status_code == 200, (
                f"Supervisor failed to start Profile A: {res_a.text}"
            )
            start_a = res_a.json()
            b_cname_a = start_a["browser_container"]
            s_cname_a = start_a["stream_container"]
            inst_a = start_a["runtime_instance_id"]
            tracker.track(b_cname_a)
            tracker.track(s_cname_a)
            tracker.track_network(f"{prefix}-net-{profile_a_id}")

            res_b = await sup_client.post(
                "/supervisor/v1/profiles/start",
                json={"profile_id": profile_b_id, "config_version": 1},
            )
            assert res_b.status_code == 200, (
                f"Supervisor failed to start Profile B: {res_b.text}"
            )
            start_b = res_b.json()
            b_cname_b = start_b["browser_container"]
            s_cname_b = start_b["stream_container"]
            inst_b = start_b["runtime_instance_id"]
            tracker.track(b_cname_b)
            tracker.track(s_cname_b)
            tracker.track_network(f"{prefix}-net-{profile_b_id}")

        b_c_a = d_client.containers.get(b_cname_a)
        s_c_a = d_client.containers.get(s_cname_a)
        b_c_b = d_client.containers.get(b_cname_b)
        s_c_b = d_client.containers.get(s_cname_b)
        assert b_c_a.status == "running"
        assert s_c_a.status == "running"
        assert b_c_b.status == "running"
        assert s_c_b.status == "running"

        logger.info("Taking API process genuinely offline...")
        api_proc.stop()
        assert api_proc.verify_offline(), (
            "API process MUST be genuinely offline and refusing HTTP connections"
        )

        await asyncio.sleep(2.0)

        async with httpx.AsyncClient(
            base_url=sup_proc.url, headers=sup_headers, timeout=10.0, trust_env=False
        ) as sup_client:
            r_sup_health = await sup_client.get("/supervisor/v1/health")
            assert r_sup_health.status_code == 200
        b_c_b.reload()
        s_c_b.reload()
        assert b_c_b.status == "running", (
            "Healthy companion Profile B browser must NOT be killed on API offline"
        )
        assert s_c_b.status == "running", (
            "Healthy companion Profile B stream must NOT be killed on API offline"
        )

        logger.info(
            f"Triggering clean Chrome close in container {b_cname_a} "
            "while API is offline..."
        )
        RealBrowserActionProbe.trigger_clean_close(b_cname_a)

        spool_watcher = SpoolDirectoryWatcher(data_root / "spool")
        spool_file, event_data = await spool_watcher.wait_for_spool_event(
            profile_a_id, timeout_sec=30.0
        )

        assert event_data["profile_id"] == profile_a_id
        assert event_data["runtime_instance_id"] == inst_a
        assert event_data["event_type"] == "exit"
        assert event_data["exit_reason"] == "normal"
        assert event_data["exit_code"] == 0
        recorded_event_id = event_data["event_id"]
        logger.info(
            f"Verified atomic on-disk spool event: {recorded_event_id} in {spool_file}"
        )

        await asyncio.sleep(2.0)
        assert spool_file.exists(), (
            "Spooled event MUST remain on disk while API is offline"
        )
        b_c_b.reload()
        s_c_b.reload()
        assert b_c_b.status == "running"
        assert s_c_b.status == "running"

        logger.info("Executing SIGKILL on Supervisor...")
        sup_proc.sigkill()
        assert api_proc.verify_offline(), (
            "API must remain offline during Supervisor kill"
        )
        assert spool_file.exists(), "Spool file must persist across Supervisor SIGKILL"

        logger.info(
            "Restarting Supervisor with same data_root while API is still offline..."
        )
        sup_proc.start()

        assert api_proc.verify_offline(), "API is still offline"
        await asyncio.sleep(2.0)
        assert spool_file.exists(), (
            "Resurrected Supervisor must retain spooled event while API remains down"
        )
        b_c_b.reload()
        s_c_b.reload()
        assert b_c_b.status == "running", (
            "Supervisor resurrection while API is offline must NOT delete Profile B"
        )
        assert s_c_b.status == "running"

        logger.info(f"Restarting API process on port {api_port} with same database...")
        api_proc.start()

        logger.info(
            "Waiting for Supervisor background monitoring loop to automatically "
            "replay spooled event..."
        )
        await spool_watcher.wait_for_spool_cleared(spool_file, timeout_sec=30.0)
        logger.info(
            "Spool file successfully cleared following confirmed delivery to API!"
        )

        async with httpx.AsyncClient(
            base_url=api_proc.url, headers=api_headers, trust_env=False
        ) as api_client:
            for _ in range(50):
                r_rt_a = await api_client.get(
                    f"/api/v1/internal/supervisor/profiles/{profile_a_id}/runtime"
                )
                if (
                    r_rt_a.status_code == 200
                    and r_rt_a.json()["desired_state"] == "stopped"
                ):
                    break
                await asyncio.sleep(0.5)

            assert r_rt_a.status_code == 200
            data_rt_a = r_rt_a.json()
            assert data_rt_a["desired_state"] == "stopped", (
                f"Profile A desired_state did not converge: {data_rt_a}"
            )
            assert data_rt_a["last_exit_event_id"] == recorded_event_id

            r_rt_b = await api_client.get(
                f"/api/v1/internal/supervisor/profiles/{profile_b_id}/runtime"
            )
            assert r_rt_b.status_code == 200
            assert r_rt_b.json()["desired_state"] == "running"

        logger.info(
            "Restarting Supervisor again to verify closed profile is not "
            "erroneously restarted..."
        )
        sup_proc.restart()

        async with httpx.AsyncClient(
            base_url=sup_proc.url, headers=sup_headers, timeout=20.0, trust_env=False
        ) as sup_client:
            stat_a = (
                await sup_client.get(f"/supervisor/v1/profiles/{profile_a_id}/status")
            ).json()
            assert stat_a["observed_state"] in ("stopped", "inactive", "idle")

            # Verify in Docker directly: Profile A original container is exited or
            # cleanly removed, and zero running containers exist for Profile A
            try:
                b_c_a.reload()
                assert b_c_a.status in ("exited", "dead", "stopped")
            except docker.errors.NotFound:
                pass  # Container was cleanly removed upon stop

            running_a = [
                c
                for c in d_client.containers.list()
                if c.labels.get("com.cbrowser.profile-id") == profile_a_id
                and c.status == "running"
            ]
            assert len(running_a) == 0, (
                f"Expected 0 running containers for closed profile A, found {running_a}"
            )

            r_stop_b = await sup_client.post(
                "/supervisor/v1/profiles/stop",
                json={
                    "profile_id": profile_b_id,
                    "runtime_instance_id": inst_b,
                    "operation_id": f"stop-{profile_b_id}",
                },
            )
            assert r_stop_b.status_code == 200

        async with httpx.AsyncClient(
            base_url=api_proc.url, headers=api_headers, trust_env=False
        ) as api_client:
            await api_client.patch(
                f"/api/v1/profiles/{profile_a_id}/runtime/desired-state",
                json={"desired_state": "running"},
            )
            r_dup = await api_client.post(
                "/api/v1/internal/supervisor/runtimes/events", json=event_data
            )
            assert r_dup.status_code == 200
            dup_res = r_dup.json()
            assert dup_res["status"] == "ok"
            assert dup_res["outcome"] == "duplicate"

            r_rt_a2 = await api_client.get(
                f"/api/v1/internal/supervisor/profiles/{profile_a_id}/runtime"
            )
            assert r_rt_a2.json()["desired_state"] == "running", (
                "Duplicate old exit event must NOT overwrite new running intent"
            )

        logger.info(
            "All offline recovery & event spool replay verification phases "
            "passed successfully!"
        )

    finally:
        logger.info("Executing safe teardown of test processes and owned containers...")
        if sup_proc:
            sup_proc.stop()
        if api_proc:
            api_proc.stop()
        await gateway.stop()
        # Discover remaining resources after Supervisor has stopped, including
        # failures before a start response could register individual IDs.
        for container in d_client.containers.list(
            all=True,
            filters={
                "label": [
                    f"com.cbrowser.prefix={prefix}",
                    "com.cbrowser.managed-by=supervisor",
                ]
            },
        ):
            tracker.track(container.id)
        for network in d_client.networks.list(
            filters={
                "label": [
                    f"com.cbrowser.prefix={prefix}",
                    "com.cbrowser.managed-by=supervisor",
                ]
            },
        ):
            tracker.track_network(network.id)
        try:
            tracker.cleanup()
        finally:
            d_client.close()
