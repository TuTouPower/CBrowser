"""True API Process Offline & Supervisor Event Spool Recovery E2E Suite.

Validates AC-004 under genuine multi-process failure scenarios with A1
Authoritative Observation Architecture:
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
10. Spool file is unlinked upon delivery; authoritative observation converges
    Profile A to desired_state=stopped and observed_state=stopped, failure_count=0,
    restart_blocked=False, and last_exit_event_id=None (fence separation).
11. Diagnostic UUID verified in API SQLite runtime_events via read-only query.
12. Negative diagnostic probe against active Profile B proves diagnostic event
    payloads cannot alter business state (desired/observed running intact).
13. Second Supervisor restart preserves stopped profile; duplicate old exit event
    does not overwrite new user intent.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import json
import logging
import os
import secrets
import sqlite3
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
RealSupervisorContainer = offline_fixture.RealSupervisorContainer
SandboxContainerTracker = offline_fixture.SandboxContainerTracker
SpoolDirectoryWatcher = offline_fixture.SpoolDirectoryWatcher
get_free_port = offline_fixture.get_free_port
prepare_engine_cache = offline_fixture.prepare_engine_cache

logger = logging.getLogger("cbrowser.tests.e2e.offline_recovery")


@pytest.mark.asyncio
async def test_supervisor_authoritative_api_offline_replay_and_recovery_e2e(
    tmp_path: Path,
):
    """AC-004 & A1: Authoritative observation recovery and event replay E2E.

    Replaces legacy test_supervisor_true_api_offline_event_spool_and_recovery.
    Verifies spool survival, authoritative convergence, and payload isolation.
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
    sup_proc = RealSupervisorContainer(
        api_url=f"http://host.docker.internal:{api_port}",
        data_root=data_root,
        engine_cache=engine_cache,
        geoip_cache=geoip_cache,
        token_file=sup_token_file,
        agent_key_file=agent_key_file,
        gateway_url=f"ws://host.docker.internal:{gw_port}",
        gateway_control_url=f"http://host.docker.internal:{gw_port}",
        gateway_token_file=gw_token_file,
        prefix=prefix,
        port=sup_port,
        root=ROOT,
        env=clean_environ,
        log_path=sup_log,
        docker_client=d_client,
    )

    api_headers = {"Authorization": f"Bearer {sup_token}"}
    sup_headers = {"Authorization": f"Bearer {sup_token}"}

    try:
        await gateway.start()
        await asyncio.to_thread(api_proc.start)
        await asyncio.to_thread(sup_proc.start)
        api_headers.update(api_proc.auth_headers)
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
        await asyncio.to_thread(api_proc.stop)
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
        await asyncio.to_thread(sup_proc.sigkill)
        assert api_proc.verify_offline(), (
            "API must remain offline during Supervisor kill"
        )
        assert spool_file.exists(), "Spool file must persist across Supervisor SIGKILL"

        logger.info(
            "Restarting Supervisor with same data_root while API is still offline..."
        )
        await asyncio.to_thread(sup_proc.start)

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
        await asyncio.to_thread(api_proc.start)

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
                    and r_rt_a.json()["observed_state"] == "stopped"
                ):
                    break
                await asyncio.sleep(0.5)

            assert r_rt_a.status_code == 200
            data_rt_a = r_rt_a.json()
            assert data_rt_a["desired_state"] == "stopped", (
                f"Profile A desired_state did not converge: {data_rt_a}"
            )
            assert data_rt_a["observed_state"] == "stopped", (
                f"Profile A observed_state did not converge to stopped: {data_rt_a}"
            )
            assert data_rt_a["failure_count"] == 0, (
                f"Profile A failure_count must not increment on clean exit: {data_rt_a}"
            )
            assert data_rt_a["restart_blocked"] is False, (
                f"Profile A must not be restart blocked on clean exit: {data_rt_a}"
            )
            # A1 Authoritative Observation: last_exit_event_id is strictly an
            # abnormal retry fence, never written from normal diagnostic exit events.
            assert data_rt_a["last_exit_event_id"] is None, (
                "Profile A last_exit_event_id must remain None for normal exit: "
                f"{data_rt_a}"
            )

            # Authoritative read-only SQLite inspection: verify diagnostic UUID was
            # durably ingested into runtime_events exactly once without test writing DB.
            db_ro_uri = f"{api_db_path.resolve().as_uri()}?mode=ro"
            with contextlib.closing(sqlite3.connect(db_ro_uri, uri=True)) as conn:
                cursor = conn.cursor()
                rows = cursor.execute(
                    "SELECT event_id, profile_id, runtime_instance_id, "
                    "event_type, exit_code, exit_reason FROM runtime_events "
                    "WHERE event_id = ?",
                    (recorded_event_id,),
                ).fetchall()
            assert len(rows) == 1, (
                f"Expected exactly 1 diagnostic event for {recorded_event_id}, "
                f"found {len(rows)}"
            )
            evt_row = rows[0]
            assert evt_row[0] == recorded_event_id
            assert evt_row[1] == profile_a_id
            assert evt_row[2] == inst_a
            assert evt_row[3] == "exit"
            assert evt_row[4] == 0
            assert evt_row[5] == "normal"

            r_rt_b = await api_client.get(
                f"/api/v1/internal/supervisor/profiles/{profile_b_id}/runtime"
            )
            assert r_rt_b.status_code == 200
            data_rt_b = r_rt_b.json()
            assert data_rt_b["desired_state"] == "running"
            assert data_rt_b["observed_state"] == "running"
            assert data_rt_b["failure_count"] == 0
            assert data_rt_b["last_exit_event_id"] is None

            # A1 Negative Probe: With Profile B still running live Browser and Stream
            # containers, probe Agent/Chrome liveness via container UDS /health before
            # and after injecting a fake normal diagnostic exit event.
            cfg_b = int(data_rt_b["config_version"])

            async def _probe_b_agent_health() -> dict:
                script = (
                    "import httpx, json; "
                    "t = httpx.HTTPTransport(uds='/run/cbrowser/runtime/agent.sock'); "
                    "c = httpx.Client(transport=t, base_url='http://uds'); "
                    "r = c.get('/health'); "
                    "assert r.status_code == 200, f'HTTP {r.status_code}: {r.text}'; "
                    "print(json.dumps(r.json())); "
                    "c.close()"
                )
                exec_res = await asyncio.to_thread(
                    b_c_b.exec_run,
                    ["python3", "-c", script],
                )
                assert exec_res.exit_code == 0, (
                    "Profile B Browser Agent health exec failed "
                    f"(code {exec_res.exit_code}): "
                    f"{exec_res.output.decode('utf-8', errors='replace')}"
                )
                health = json.loads(exec_res.output.decode("utf-8").strip())
                assert health.get("ready") is True, f"Agent B not ready: {health}"
                assert health.get("browser_ready") is True, (
                    f"Browser B not ready: {health}"
                )
                assert health.get("profile_id") == profile_b_id, (
                    f"Profile mismatch: expected {profile_b_id}, "
                    f"got {health.get('profile_id')}"
                )
                assert health.get("runtime_instance_id") == inst_b, (
                    f"Instance mismatch: expected {inst_b}, "
                    f"got {health.get('runtime_instance_id')}"
                )
                assert health.get("config_version") == cfg_b, (
                    f"Version mismatch: expected {cfg_b}, "
                    f"got {health.get('config_version')}"
                )
                return health

            await _probe_b_agent_health()

            fake_b_event_id = f"diag-b-{uuid.uuid4().hex}"
            fake_b_exit_payload = {
                "event_id": fake_b_event_id,
                "profile_id": profile_b_id,
                "runtime_instance_id": inst_b,
                "event_type": "exit",
                "exit_code": 0,
                "exit_reason": "normal",
                "config_version": cfg_b,
                "payload": {"source": "negative_diagnostic_probe"},
            }
            r_diag_b = await api_client.post(
                "/api/v1/internal/supervisor/runtimes/events",
                json=fake_b_exit_payload,
            )
            assert r_diag_b.status_code == 200
            diag_b_res = r_diag_b.json()
            assert diag_b_res["status"] == "ok"
            assert diag_b_res["outcome"] == "applied"

            # Verify event was received and stored in runtime_events
            with contextlib.closing(sqlite3.connect(db_ro_uri, uri=True)) as conn:
                b_rows = (
                    conn.cursor()
                    .execute(
                        "SELECT event_id, profile_id FROM runtime_events "
                        "WHERE event_id = ?",
                        (fake_b_event_id,),
                    )
                    .fetchall()
                )
            assert len(b_rows) == 1, (
                f"Expected exactly 1 diagnostic event for {fake_b_event_id}, "
                f"found {len(b_rows)}"
            )

            # Authoritative State Proof: diagnostic event payload CANNOT alter
            # business runtime state!
            r_rt_b_after = await api_client.get(
                f"/api/v1/internal/supervisor/profiles/{profile_b_id}/runtime"
            )
            assert r_rt_b_after.status_code == 200
            data_rt_b_after = r_rt_b_after.json()
            assert data_rt_b_after["desired_state"] == "running", (
                "Profile B desired_state mutated by diagnostic event: "
                f"{data_rt_b_after}"
            )
            assert data_rt_b_after["observed_state"] == "running", (
                "Profile B observed_state mutated by diagnostic event: "
                f"{data_rt_b_after}"
            )
            assert data_rt_b_after["failure_count"] == 0, (
                "Profile B failure_count mutated by diagnostic event: "
                f"{data_rt_b_after}"
            )
            assert data_rt_b_after["last_exit_event_id"] is None, (
                "Profile B last_exit_event_id mutated by diagnostic event: "
                f"{data_rt_b_after}"
            )

            # Verify Agent/Chrome inside Profile B browser container remains active
            await _probe_b_agent_health()

            # Verify Docker containers for Profile B are genuinely still running
            b_c_b.reload()
            s_c_b.reload()
            assert b_c_b.status == "running", (
                "Profile B browser container must remain running after "
                "diagnostic negative probe"
            )
            assert s_c_b.status == "running", (
                "Profile B stream container must remain running after "
                "diagnostic negative probe"
            )

        logger.info(
            "Restarting Supervisor again to verify closed profile is not "
            "erroneously restarted..."
        )
        await asyncio.to_thread(sup_proc.restart)

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

            # Ensure duplicate replay did not create second entry in runtime_events
            with contextlib.closing(sqlite3.connect(db_ro_uri, uri=True)) as conn:
                rows_after_dup = (
                    conn.cursor()
                    .execute(
                        "SELECT COUNT(*) FROM runtime_events WHERE event_id = ?",
                        (recorded_event_id,),
                    )
                    .fetchone()[0]
                )
            assert rows_after_dup == 1, (
                "Duplicate event replay must not duplicate row in runtime_events, "
                f"count={rows_after_dup}"
            )

        logger.info(
            "All offline recovery & event spool replay verification phases "
            "passed successfully!"
        )

    finally:
        logger.info("Executing safe teardown of test processes and owned containers...")
        if sup_proc:
            await asyncio.to_thread(sup_proc.stop)
        if api_proc:
            await asyncio.to_thread(api_proc.stop)
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
