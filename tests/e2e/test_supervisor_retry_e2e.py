"""Real API Subprocess & Docker Container 3-Strikes Recovery E2E Suite.

Validates the complete recovery lifecycle with real independent processes:
1. Real independent API subprocess (RealApiProcess).
2. Production Gateway application with HMAC Bearer authentication
   (ProductionGatewayService).
3. Real Supervisor container (RealSupervisorContainer running
   cbrowser.supervisor.runner).
4. Dual-container sandbox lifecycle (real Browser and Stream Docker containers).
5. Strike 1: Kill Browser -> wait 2.0s retry backoff -> verify new container
   Created >= updated_at + 2.0s.
6. Strike 2: Kill Browser -> 10.0s retry backoff.
   During backoff, SIGKILL the Supervisor container, restart it and verify
   it comes back with a new container identity.
   Verify new container Created >= updated_at + 10.0s (durable recovery does
   NOT reset timer).
7. Strike 3: Kill Browser -> wait 30.0s retry backoff -> verify new container
   Created >= updated_at + 30.0s.
8. Strike 4: Kill Browser -> failure_count reaches 4, restart_blocked=True,
   no container created.
9. Manual unblock: reset_blocked clears block -> immediate recovery.
10. Normal clean exit: via RealBrowserActionProbe -> desired_state becomes
    stopped -> no retry.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import shutil
import signal
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import docker
import httpx
import pytest

from e2e_env import free_udp_port_span

from e2e_env import require_e2e_env
from gateway_probe.topology import cleanup_prefixed_resources
from supervisor_recovery_probe.gateway_service import (
    ApiRuntimeLookup,
    ProductionGatewayService,
)
from supervisor_recovery_probe.offline_fixture import (
    RealApiProcess,
    RealBrowserActionProbe,
    RealSupervisorContainer,
    get_free_port,
)

logger = logging.getLogger(__name__)


def parse_docker_timestamp(ts_str: str) -> datetime:
    """Parse Docker inspect Created timestamp (e.g. 2026-10-29T14:12:34.567890123Z)."""
    clean_str = ts_str.rstrip("Z")
    if "." in clean_str:
        base, frac = clean_str.split(".", 1)
        frac = (frac + "000000")[:6]
        clean_str = f"{base}.{frac}"
    return datetime.fromisoformat(clean_str).replace(tzinfo=UTC)


@pytest.mark.asyncio
async def test_supervisor_real_container_retry_e2e(tmp_path: Path):
    env = require_e2e_env(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_STREAM_TEST_IMAGE",
        "CBROWSER_RUNTIME_ENGINE_CACHE",
        "CBROWSER_RUNTIME_GEOIP_CACHE",
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
    engine_cache_src = Path(engine_cache_val)
    geoip_cache_src = Path(geoip_cache_val)
    assert engine_cache_src.is_dir(), (
        f"CBROWSER_RUNTIME_ENGINE_CACHE is not a valid directory: {engine_cache_val}"
    )
    assert geoip_cache_src.is_dir(), (
        f"CBROWSER_RUNTIME_GEOIP_CACHE is not a valid directory: {geoip_cache_val}"
    )

    d_client = docker.from_env()
    d_client.images.get(browser_image)
    d_client.images.get(stream_image)

    # Generate isolated directories and credentials
    data_root = tmp_path / "data_root"
    data_root.mkdir()
    engine_cache = data_root / "engine_cache"
    shutil.copytree(engine_cache_src, engine_cache)
    shutil.copytree(geoip_cache_src, engine_cache / "geoip", dirs_exist_ok=True)

    sup_token_file = tmp_path / "supervisor_token"
    sup_token_val = secrets.token_urlsafe(32)
    sup_token_file.write_text(sup_token_val, encoding="utf-8")
    sup_token_file.chmod(0o600)

    agent_key_file = tmp_path / "agent_key"
    agent_key_val = secrets.token_urlsafe(32)
    agent_key_file.write_text(agent_key_val, encoding="utf-8")
    agent_key_file.chmod(0o600)

    gw_token_file = tmp_path / "gateway_token"
    gw_token_val = secrets.token_urlsafe(32)
    gw_token_file.write_text(gw_token_val, encoding="utf-8")
    gw_token_file.chmod(0o600)

    api_port = get_free_port()
    sup_port = get_free_port()
    gw_port = get_free_port()

    test_run_id = uuid.uuid4().hex[:6]
    prefix = f"t005-retry-e2e-{test_run_id}"


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
        CBROWSER_BROWSER_IMAGE=browser_image,
        CBROWSER_STREAM_IMAGE=stream_image,
        TMPDIR=str(tmp_path),
    )

    api_proc = RealApiProcess(
        port=api_port,
        db_path=tmp_path / "control.db",
        token_file=sup_token_file,
        root=root,
        env=env,
        log_path=tmp_path / "api.log",
    )

    gateway = ProductionGatewayService(
        port=gw_port,
        agent_key_file=agent_key_file,
        gateway_token_file=gw_token_file,
        runtime_lookup=ApiRuntimeLookup(api_proc.url, sup_token_file),
    )

    udp_base = free_udp_port_span(2)
    sup_proc = RealSupervisorContainer(
        api_url=f"http://host.docker.internal:{api_port}",
        data_root=data_root,
        engine_cache=engine_cache,
        geoip_cache=engine_cache / "geoip",
        token_file=sup_token_file,
        agent_key_file=agent_key_file,
        gateway_url=f"ws://host.docker.internal:{gw_port}",
        gateway_control_url=f"http://host.docker.internal:{gw_port}",
        gateway_token_file=gw_token_file,
        prefix=prefix,
        port=sup_port,
        root=root,
        env=env,
        log_path=tmp_path / "supervisor.log",
        docker_client=d_client,
        udp_mux_min_port=udp_base,
        udp_mux_max_port=udp_base + 1,
    )

    evidence_records: list[dict] = []
    tracked_cids: list[str] = []

    try:
        # Start API, Gateway, and Supervisor subprocesses
        await asyncio.to_thread(api_proc.start)
        await gateway.start()
        await asyncio.to_thread(sup_proc.start)

        api_headers = {"Authorization": f"Bearer {sup_token_val}"}
        api_headers.update(api_proc.auth_headers)
        sup_headers = {"Authorization": f"Bearer {sup_token_val}"}

        async with (
            httpx.AsyncClient(
                base_url=api_proc.url,
                headers=api_headers,
                timeout=15.0,
                trust_env=False,
            ) as api_client,
            httpx.AsyncClient(
                base_url=sup_proc.url,
                headers=sup_headers,
                timeout=30.0,
                trust_env=False,
            ) as sup_client,
        ):
            # 1. Create Profile and set desired_state = running
            r_create = await api_client.post(
                "/api/v1/profiles", json={"name": "Subprocess Retry Profile"}
            )
            assert r_create.status_code == 201
            profile_id = r_create.json()["id"]

            r_des = await api_client.patch(
                f"/api/v1/profiles/{profile_id}/runtime/desired-state",
                json={"desired_state": "running"},
            )
            assert r_des.status_code == 200

            # 2. Launch initial profile via Supervisor Control RPC
            r_start = await sup_client.post(
                "/supervisor/v1/profiles/start",
                json={"profile_id": profile_id, "config_version": 1},
            )
            assert r_start.status_code == 200
            start_info = r_start.json()
            inst_0 = start_info["runtime_instance_id"]
            b0_name = start_info["browser_container"]
            b0_c = d_client.containers.get(b0_name)
            tracked_cids.append(b0_c.id)
            assert b0_c.status == "running"

            # ------------------------------------------------------------------
            # Strike 1: Kill Browser -> 2.0s delay interval backoff
            # ------------------------------------------------------------------
            t_kill_1 = time.monotonic()
            b0_c.kill(signal=signal.SIGKILL)
            logger.info("Killed initial container %s at mono=%.3f", b0_c.id, t_kill_1)

            # Wait for API to register failure 1 with durable updated_at
            updated_at_1_dt = None
            for _ in range(40):
                await asyncio.sleep(0.25)
                r_rt = await api_client.get(
                    f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime"
                )
                rt_val = r_rt.json()
                if (
                    rt_val.get("failure_count") == 1
                    and rt_val.get("runtime_instance_id") is None
                ):
                    updated_at_1_dt = datetime.fromisoformat(
                        rt_val["updated_at"]
                    ).replace(tzinfo=UTC)
                    break
            assert updated_at_1_dt is not None, "API did not register failure 1"

            # Wait for new instance 1 to be launched
            inst_1 = None
            b1_created_dt = None
            b1_cid = None
            for _ in range(120):
                await asyncio.sleep(0.25)
                r_rt = await api_client.get(
                    f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime"
                )
                rt_val = r_rt.json()
                curr_inst = rt_val.get("runtime_instance_id")
                if (
                    curr_inst
                    and curr_inst != inst_0
                    and rt_val.get("observed_state") == "running"
                ):
                    inst_1 = curr_inst
                    active_containers = d_client.containers.list(
                        filters={"label": f"com.cbrowser.prefix={prefix}"}
                    )
                    for c in active_containers:
                        if (
                            c.labels.get("com.cbrowser.instance-id") == inst_1
                            and c.labels.get("com.cbrowser.role") == "browser"
                        ):
                            b1_cid = c.id
                            c.reload()
                            b1_created_dt = parse_docker_timestamp(c.attrs["Created"])
                            break
                    if b1_created_dt is not None:
                        break

            assert inst_1 is not None and b1_created_dt is not None
            tracked_cids.append(b1_cid)
            delay_1 = (b1_created_dt - updated_at_1_dt).total_seconds()
            logger.info(
                "Strike 1: updated_at=%s, created_at=%s, delta=%.3fs "
                "(expected >= 2.0s)",
                updated_at_1_dt,
                b1_created_dt,
                delay_1,
            )
            assert 2.0 <= delay_1 <= 2.0 + max(5.0, 2.0 * 0.5), (
                f"Strike 1 delay outside tolerant window: {delay_1:.3f}s"
            )
            evidence_records.append(
                {
                    "strike": 1,
                    "target_delay_sec": 2.0,
                    "actual_delay_sec": delay_1,
                    "updated_at": updated_at_1_dt.isoformat(),
                    "container_created_at": b1_created_dt.isoformat(),
                    "instance_id": inst_1,
                }
            )

            # ------------------------------------------------------------------
            # Strike 2: Kill Browser -> 10.0s delay interval backoff
            # IN-FLIGHT SIGKILL: Kill Supervisor process during delay!
            # ------------------------------------------------------------------
            b1_c = d_client.containers.get(b1_cid)
            t_kill_2 = time.monotonic()
            b1_c.kill(signal=signal.SIGKILL)
            logger.info("Killed container %s at mono=%.3f", b1_cid, t_kill_2)

            updated_at_2_dt = None
            for _ in range(40):
                await asyncio.sleep(0.25)
                r_rt = await api_client.get(
                    f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime"
                )
                rt_val = r_rt.json()
                if (
                    rt_val.get("failure_count") == 2
                    and rt_val.get("runtime_instance_id") is None
                ):
                    updated_at_2_dt = datetime.fromisoformat(
                        rt_val["updated_at"]
                    ).replace(tzinfo=UTC)
                    break
            assert updated_at_2_dt is not None, "API did not register failure 2"

            # Sleep ~2.5s into the 10s delay, then SIGKILL Supervisor container
            await asyncio.sleep(2.5)
            old_sup_cid = sup_proc.container_id
            await asyncio.to_thread(sup_proc.sigkill)
            logger.info("Supervisor container %s killed with SIGKILL 137", old_sup_cid)

            # Resurrect Supervisor with new container identity
            await asyncio.to_thread(sup_proc.start)
            new_sup_cid = sup_proc.container_id
            logger.info("Supervisor restarted with new container ID %s", new_sup_cid)
            assert new_sup_cid != old_sup_cid

            # Wait for instance 2 to be launched
            inst_2 = None
            b2_created_dt = None
            b2_cid = None
            for _ in range(160):
                await asyncio.sleep(0.25)
                r_rt = await api_client.get(
                    f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime"
                )
                rt_val = r_rt.json()
                curr_inst = rt_val.get("runtime_instance_id")
                if (
                    curr_inst
                    and curr_inst != inst_1
                    and rt_val.get("observed_state") == "running"
                ):
                    inst_2 = curr_inst
                    active_containers = d_client.containers.list(
                        filters={"label": f"com.cbrowser.prefix={prefix}"}
                    )
                    for c in active_containers:
                        if (
                            c.labels.get("com.cbrowser.instance-id") == inst_2
                            and c.labels.get("com.cbrowser.role") == "browser"
                        ):
                            b2_cid = c.id
                            c.reload()
                            b2_created_dt = parse_docker_timestamp(c.attrs["Created"])
                            break
                    if b2_created_dt is not None:
                        break

            assert inst_2 is not None and b2_created_dt is not None
            tracked_cids.append(b2_cid)
            delay_2 = (b2_created_dt - updated_at_2_dt).total_seconds()
            logger.info(
                "Strike 2 across crash: updated_at=%s, created_at=%s, "
                "delta=%.3fs (expected >= 10.0s)",
                updated_at_2_dt,
                b2_created_dt,
                delay_2,
            )
            assert 10.0 <= delay_2 <= 10.0 + max(5.0, 10.0 * 0.5), (
                f"Strike 2 delay outside tolerant window: {delay_2:.3f}s"
            )
            evidence_records.append(
                {
                    "strike": 2,
                    "target_delay_sec": 10.0,
                    "actual_delay_sec": delay_2,
                    "updated_at": updated_at_2_dt.isoformat(),
                    "container_created_at": b2_created_dt.isoformat(),
                    "instance_id": inst_2,
                    "supervisor_sigkill_verified": True,
                }
            )

            # ------------------------------------------------------------------
            # Strike 3: Kill Browser -> 30.0s delay interval backoff
            # ------------------------------------------------------------------
            b2_c = d_client.containers.get(b2_cid)
            t_kill_3 = time.monotonic()
            b2_c.kill(signal=signal.SIGKILL)
            logger.info("Killed container %s at mono=%.3f", b2_cid, t_kill_3)

            updated_at_3_dt = None
            for _ in range(40):
                await asyncio.sleep(0.25)
                r_rt = await api_client.get(
                    f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime"
                )
                rt_val = r_rt.json()
                if (
                    rt_val.get("failure_count") == 3
                    and rt_val.get("runtime_instance_id") is None
                ):
                    updated_at_3_dt = datetime.fromisoformat(
                        rt_val["updated_at"]
                    ).replace(tzinfo=UTC)
                    break
            assert updated_at_3_dt is not None, "API did not register failure 3"

            inst_3 = None
            b3_created_dt = None
            b3_cid = None
            for _ in range(240):
                await asyncio.sleep(0.5)
                r_rt = await api_client.get(
                    f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime"
                )
                rt_val = r_rt.json()
                curr_inst = rt_val.get("runtime_instance_id")
                if (
                    curr_inst
                    and curr_inst != inst_2
                    and rt_val.get("observed_state") == "running"
                ):
                    inst_3 = curr_inst
                    active_containers = d_client.containers.list(
                        filters={"label": f"com.cbrowser.prefix={prefix}"}
                    )
                    for c in active_containers:
                        if (
                            c.labels.get("com.cbrowser.instance-id") == inst_3
                            and c.labels.get("com.cbrowser.role") == "browser"
                        ):
                            b3_cid = c.id
                            c.reload()
                            b3_created_dt = parse_docker_timestamp(c.attrs["Created"])
                            break
                    if b3_created_dt is not None:
                        break

            assert inst_3 is not None and b3_created_dt is not None
            tracked_cids.append(b3_cid)
            delay_3 = (b3_created_dt - updated_at_3_dt).total_seconds()
            logger.info(
                "Strike 3: updated_at=%s, created_at=%s, delta=%.3fs "
                "(expected >= 30.0s)",
                updated_at_3_dt,
                b3_created_dt,
                delay_3,
            )
            assert 30.0 <= delay_3 <= 30.0 + max(5.0, 30.0 * 0.5), (
                f"Strike 3 delay outside tolerant window: {delay_3:.3f}s"
            )
            evidence_records.append(
                {
                    "strike": 3,
                    "target_delay_sec": 30.0,
                    "actual_delay_sec": delay_3,
                    "updated_at": updated_at_3_dt.isoformat(),
                    "container_created_at": b3_created_dt.isoformat(),
                    "instance_id": inst_3,
                }
            )

            # ------------------------------------------------------------------
            # Strike 4: Fourth failure -> Blocks! restart_blocked=True, failure_count=4
            # ------------------------------------------------------------------
            b3_c = d_client.containers.get(b3_cid)
            b3_c.kill(signal=signal.SIGKILL)
            logger.info("Killed container %s for Strike 4 blocking", b3_cid)

            blocked_confirmed = False
            for _ in range(50):
                await asyncio.sleep(0.25)
                r_rt = await api_client.get(
                    f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime"
                )
                rt_val = r_rt.json()
                if (
                    rt_val.get("failure_count") == 4
                    and rt_val.get("restart_blocked") is True
                ):
                    blocked_confirmed = True
                    break
            assert blocked_confirmed, (
                "Profile did not reach restart_blocked=True after 4 failures"
            )

            # Assert no container created while blocked
            await asyncio.sleep(3.0)
            r_rt_check = await api_client.get(
                f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime"
            )
            assert r_rt_check.json().get("runtime_instance_id") is None

            # ------------------------------------------------------------------
            # Manual Unblock: reset_blocked clears block -> Immediate recovery
            # ------------------------------------------------------------------
            logger.info("Triggering manual reset_blocked via API...")
            r_unblock = await api_client.patch(
                f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime/desired-state",
                headers={"Idempotency-Key": f"unblock-{uuid.uuid4().hex[:6]}"},
                json={"desired_state": "running"},
            )
            assert r_unblock.status_code == 200
            assert r_unblock.json()["failure_count"] == 0
            assert r_unblock.json()["restart_blocked"] is False

            inst_4 = None
            b4_name = None
            for _ in range(60):
                await asyncio.sleep(0.25)
                r_rt = await api_client.get(
                    f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime"
                )
                rt_val = r_rt.json()
                curr_inst = rt_val.get("runtime_instance_id")
                if curr_inst and rt_val.get("observed_state") == "running":
                    inst_4 = curr_inst
                    active_containers = d_client.containers.list(
                        filters={"label": f"com.cbrowser.prefix={prefix}"}
                    )
                    for c in active_containers:
                        if (
                            c.labels.get("com.cbrowser.instance-id") == inst_4
                            and c.labels.get("com.cbrowser.role") == "browser"
                        ):
                            b4_name = c.name
                            tracked_cids.append(c.id)
                            break
                    if b4_name:
                        break

            assert inst_4 is not None and b4_name is not None
            logger.info(
                "Manual unblock successfully recovered instance %s (%s)",
                inst_4,
                b4_name,
            )

            # ------------------------------------------------------------------
            # Normal clean exit: via RealBrowserActionProbe -> desired_state stopped
            # ------------------------------------------------------------------
            logger.info("Triggering normal clean close on container %s", b4_name)
            RealBrowserActionProbe.trigger_clean_close(b4_name)

            stopped_confirmed = False
            for _ in range(60):
                await asyncio.sleep(0.25)
                r_rt = await api_client.get(
                    f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime"
                )
                rt_val = r_rt.json()
                if rt_val.get("desired_state") == "stopped":
                    stopped_confirmed = True
                    break
            assert stopped_confirmed, "API desired_state did not converge to stopped"

            # Assert no restart after normal exit
            await asyncio.sleep(3.0)
            r_rt_final = await api_client.get(
                f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime"
            )
            assert r_rt_final.json().get("desired_state") == "stopped"
            assert r_rt_final.json().get("runtime_instance_id") is None

        # Write evidence JSON to scratch
        scratch_evidence_path = tmp_path / "retry_timeline_evidence.json"
        scratch_evidence_path.parent.mkdir(parents=True, exist_ok=True)
        scratch_evidence_path.write_text(
            json.dumps(
                {
                    "test_run_id": test_run_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "records": evidence_records,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info("Evidence successfully recorded to %s", scratch_evidence_path)

    finally:
        await asyncio.to_thread(sup_proc.stop)
        await gateway.stop()
        await asyncio.to_thread(api_proc.stop)
        cleanup_prefixed_resources(d_client, prefix)
        d_client.close()
