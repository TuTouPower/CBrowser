"""Use actual cgroup-limited work, then idle, to exercise monitor delivery."""

import asyncio
import json
import os
import secrets
import uuid
from dataclasses import asdict, is_dataclass
from types import SimpleNamespace

import docker
import httpx
import pytest
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.resource_monitor import ProfileResourceTarget, ResourceMonitor
from cbrowser.supervisor.resource_policy import (
    ResourcePolicyConfig,
    ResourcePolicyService,
)


async def query_decision(app, token):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://supervisor"
    ) as client:
        denied = await client.get("/supervisor/v1/profiles/profile/resources")
        assert denied.status_code == 401
        response = await client.get(
            "/supervisor/v1/profiles/profile/resources",
            headers={"Authorization": "Bearer " + token},
        )
        assert response.status_code == 200
        return response.json()["decision"]


@pytest.mark.asyncio
async def test_monitor_samples_real_container_without_blocking_loop(tmp_path):
    stream_img = os.environ.get("CBROWSER_STREAM_TEST_IMAGE")
    if not stream_img:
        pytest.skip(
            "Missing required E2E environment variable: CBROWSER_STREAM_TEST_IMAGE"
        )
    assert stream_img.startswith("sha256:"), (
        f"CBROWSER_STREAM_TEST_IMAGE must be sha256 immutable digest, got {stream_img}"
    )

    client = docker.from_env()
    client.images.get(stream_img)
    container = None
    deliveries = []
    observed = []

    async def deliver(target, decision):
        deliveries.append((target.runtime_instance_id, decision.max_fps_cap))

    try:
        container = client.containers.run(
            stream_img,
            entrypoint="python3",
            command=[
                "-c",
                (
                    "import time\nend=time.monotonic()+9\n"
                    "while time.monotonic()<end: sum(x*x for x in range(10000))\n"
                    "time.sleep(60)"
                ),
            ],
            name=f"t005-monitor-{uuid.uuid4().hex[:12]}",
            detach=True,
            user="1000:1000",
            read_only=True,
            cap_drop=["ALL"],
            network_mode="none",
            nano_cpus=500_000_000,
        )
        policy = ResourcePolicyService(
            client,
            ResourcePolicyConfig(
                overload_cpu_threshold_pct=70,
                overload_window_samples=2,
            ),
        )
        monitor = ResourceMonitor(
            policy, deliver, host_stat_path=tmp_path / "no_linux_host"
        )
        token = secrets.token_urlsafe(32)
        bad_key = tmp_path / "bad_control_key"
        bad_key.write_text(token)
        bad_key.chmod(0o644)
        with pytest.raises(ValueError, match="group or others"):
            create_control_app(
                SimpleNamespace(resource_monitor=monitor), bad_key
            )

        control_key = tmp_path / "control_key"
        control_key.write_text(token)
        control_key.chmod(0o600)
        control = create_control_app(
            SimpleNamespace(resource_monitor=monitor), control_key
        )
        target = ProfileResourceTarget("profile", "runtime_a", (container.id,), True)
        for _ in range(5):
            sample = asyncio.create_task(monitor.sample([target]))
            # The event loop must still schedule while Docker collects stats.
            await asyncio.wait_for(asyncio.sleep(0.01), timeout=0.5)
            observed.append(await sample)
            await asyncio.sleep(0.65)
        assert ("runtime_a", 8.0) in deliveries
        assert observed[-1]["decisions"]["profile"].observed_scope == "container_quota"
        assert observed[-1]["container_samples"][0][3] == 500_000_000
        throttled = observed[-1]["decisions"]["profile"]
        queried = await query_decision(control, token)
        assert queried["max_fps_cap"] == 8.0 and queried["is_throttled"] is True
        assert queried["measurement_window_sec"] == throttled.measurement_window_sec
        assert queried["measurement_window_sec"] > 0
        assert queried["timestamp"] == throttled.timestamp
        assert queried["sample_count"] == throttled.sample_count >= 2
        deadline = asyncio.get_running_loop().time() + 20
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.65)
            window = await monitor.sample([target])
            observed.append(window)
            if not window["decisions"]["profile"].is_throttled:
                break
        assert deliveries[-1] == ("runtime_a", None)
        assert observed[-1]["decisions"]["profile"].sample_count >= 2
        recovered = await query_decision(control, token)
        assert recovered["max_fps_cap"] is None and recovered["is_throttled"] is False
        assert recovered["timestamp"] == observed[-1]["decisions"]["profile"].timestamp
        # An instance replacement must receive a decision even when cap is unchanged.
        replacement = ProfileResourceTarget(
            "profile", "runtime_b", (container.id,), True
        )
        await monitor.sample([replacement])
        assert deliveries[-1] == ("runtime_b", None)
    finally:
        (tmp_path / "measurements.json").write_text(
            json.dumps(
                {"windows": observed, "deliveries": deliveries},
                default=lambda value: (
                    asdict(value) if is_dataclass(value) else str(value)
                ),
                indent=2,
            )
        )
        if container is not None:
            container.remove(force=True)
        client.close()
