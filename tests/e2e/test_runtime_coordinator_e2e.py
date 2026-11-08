"""Real Docker E2E test for Runtime Coordinator (AC-009).

Tests:
1. Setting running intent via API causes Browser & Stream to appear.
2. Setting stopped intent via API causes Browser & Stream to disappear.
3. Outage of Supervisor preserves intent, which converges upon recovery.
4. All Docker resources use standard FrontendAppTopologyHarness and cleanup_prefixed_resources.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest
from frontend_app_probe.harness import FrontendAppTopologyHarness
from gateway_probe.topology import wait_until_ready
from wait import poll_until, wait_until

pytestmark = pytest.mark.serial

logger = logging.getLogger("cbrowser.test_runtime_coordinator_e2e")


@pytest.mark.asyncio
async def test_runtime_coordinator_docker_e2e(tmp_path: Path):
    harness = FrontendAppTopologyHarness(tmp_path)
    await harness.start()

    try:
        async with await harness.api_client() as api_client:
            # 1. Create profile
            create_resp = await api_client.post(
                "/api/v1/profiles",
                json={"name": "e2e_coord_prof"},
            )
            assert create_resp.status_code == 201
            profile_id = create_resp.json()["id"]

            # A. Set running intent via API
            patch_resp = await api_client.patch(
                f"/api/v1/profiles/{profile_id}/runtime/desired-state",
                json={"desired_state": "running"},
            )
            assert patch_resp.status_code == 200
            assert patch_resp.json()["desired_state"] == "running"

            # Wait for Browser and Stream containers to actually appear in Docker
            await wait_until(
                lambda: harness.container_names(profile_id) is not None,
                timeout=180.0,
                interval=0.5,
                description=f"runtime containers for profile {profile_id}",
            )
            names = harness.container_names(profile_id)
            assert names is not None
            browser_c_name, stream_c_name = names
            assert (
                harness.docker_client.containers.get(browser_c_name).status
                == "running"
            )
            assert (
                harness.docker_client.containers.get(stream_c_name).status
                == "running"
            )

            # Verify API runtime status reports running
            rt = await harness.wait_runtime(
                profile_id, desired="running", observed="running", timeout=30.0
            )
            assert rt["desired_state"] == "running"
            assert rt["runtime_instance_id"] is not None
            assert rt["last_coordinator_error"] is None

            # B. Stop the profile via API
            stop_resp = await api_client.post(
                f"/api/v1/profiles/{profile_id}/stop"
            )
            assert stop_resp.status_code == 200
            assert stop_resp.json()["desired_state"] == "stopped"

            # Wait for Browser and Stream containers to disappear
            await wait_until(
                lambda: harness.container_names(profile_id) is None,
                timeout=60.0,
                interval=0.5,
                description="runtime containers terminated after stop",
            )

            # Verify API reports stopped
            rt_stopped = await harness.wait_runtime(
                profile_id, desired="stopped", observed="stopped", timeout=30.0
            )
            assert rt_stopped["desired_state"] == "stopped"

            # C. Simulate Supervisor outage: stop supervisor container
            harness.supervisor_container.stop(timeout=5)

            # Set running intent while Supervisor is down
            patch_down = await api_client.patch(
                f"/api/v1/profiles/{profile_id}/runtime/desired-state",
                json={"desired_state": "running"},
            )
            assert patch_down.status_code == 200
            assert patch_down.json()["desired_state"] == "running"

            # Coordinator sets last_coordinator_error
            rt_err = await poll_until(
                lambda: harness.get_runtime(profile_id),
                lambda value: bool(value.get("last_coordinator_error")),
                timeout=15.0,
                interval=0.3,
                description="coordinator error during supervisor outage",
            )
            assert rt_err["desired_state"] == "running"

            # D. Restore Supervisor container
            harness.supervisor_container.start()
            harness.supervisor_container.reload()
            sup_ports = harness.supervisor_container.attrs["NetworkSettings"][
                "Ports"
            ]["8005/tcp"]
            assert sup_ports, "Supervisor host port missing after restart"
            sup_host_port = sup_ports[0]["HostPort"]
            harness.supervisor_url = f"http://127.0.0.1:{sup_host_port}"

            await wait_until_ready(
                harness.supervisor_url,
                "/supervisor/v1/health",
                headers={"Authorization": f"Bearer {harness.keys['supervisor']}"},
                timeout=30.0,
            )

            # Wait for coordinator to converge automatically upon recovery
            rt_rec = await harness.wait_runtime(
                profile_id, desired="running", observed="running", timeout=120.0
            )
            assert rt_rec["last_coordinator_error"] is None

            # E. Cleanup: stop the running profile and wait for containers to terminate
            await api_client.post(f"/api/v1/profiles/{profile_id}/stop")
            await wait_until(
                lambda: harness.container_names(profile_id) is None,
                timeout=60.0,
                interval=0.5,
                description="runtime containers removed after final stop",
            )
    finally:
        await harness.cleanup()
