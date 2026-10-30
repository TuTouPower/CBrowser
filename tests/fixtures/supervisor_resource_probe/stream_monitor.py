"""Measure CPU-triggered policy against the real Stream and Chrome decoder."""

import asyncio
import json
import time
from dataclasses import asdict, is_dataclass

import docker
from cbrowser.supervisor.resource_monitor import ProfileResourceTarget, ResourceMonitor
from cbrowser.supervisor.resource_policy import (
    ResourcePolicyConfig,
    ResourcePolicyService,
)


async def verify_stream_cpu_policy(
    stream_name, profile_id, gateway, frame_window, work_dir
):
    client = docker.from_env()
    stream = client.containers.get(stream_name)
    assert stream.labels.get("cbrowser-t004-e2e"), (
        "Only this E2E's sandbox may change quota"
    )
    original_limit = stream.attrs["HostConfig"].get("NanoCpus", 0)
    original_quota = stream.attrs["HostConfig"].get("CpuQuota", 0) or -1
    original_period = stream.attrs["HostConfig"].get("CpuPeriod", 0) or 100_000
    instance = gateway.agent_instances[profile_id]
    target = ProfileResourceTarget(profile_id, instance, (stream.id,), True)
    windows = []
    deliveries = []

    async def send_quota(current, decision):
        session, socket = gateway.registered_agents[current.profile_id]
        assert (
            gateway.agent_instances[current.profile_id] == current.runtime_instance_id
        )
        await socket.send_json(
            {
                "version": "v2",
                "action": "supervisor_quota",
                "profile_id": current.profile_id,
                "runtime_instance_id": current.runtime_instance_id,
                "agent_session_id": session,
                "payload": {"max_fps_cap": decision.max_fps_cap},
            }
        )
        deliveries.append(asdict(decision))

    policy = ResourcePolicyService(
        client,
        ResourcePolicyConfig(
            overload_cpu_threshold_pct=70,
            recovery_cpu_threshold_pct=40,
            overload_window_samples=2,
            recovery_window_samples=2,
        ),
    )
    monitor = ResourceMonitor(
        policy, send_quota, host_stat_path=work_dir / "not_linux_host"
    )
    proof = {"original_nano_cpus": original_limit}
    try:
        proof["baseline_frames_2s"] = await frame_window()
        await asyncio.to_thread(stream.update, cpu_quota=100_000, cpu_period=100_000)
        await asyncio.to_thread(
            stream.exec_run,
            [
                "python3",
                "-c",
                (
                    "import time\nend=time.monotonic()+12\n"
                    "while time.monotonic()<end: sum(x*x for x in range(20000))"
                ),
            ],
            detach=True,
        )
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            windows.append(await monitor.sample([target]))
            if windows[-1]["decisions"][profile_id].is_throttled:
                break
            await asyncio.sleep(0.65)
        assert windows[-1]["decisions"][profile_id].max_fps_cap == 8
        await asyncio.sleep(1)
        proof["capped_frames_2s"] = await frame_window()
        assert 0 < proof["capped_frames_2s"] <= 24
        # Restoring the actual cgroup budget makes recovery independent of the
        # short-lived load process, while its work still counts in host share.
        await asyncio.to_thread(
            stream.update, cpu_quota=original_quota, cpu_period=original_period
        )
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            await asyncio.sleep(0.65)
            windows.append(await monitor.sample([target]))
            if not windows[-1]["decisions"][profile_id].is_throttled:
                break
        assert windows[-1]["decisions"][profile_id].max_fps_cap is None
        await asyncio.sleep(1)
        proof["restored_frames_2s"] = await frame_window()
        assert proof["restored_frames_2s"] > proof["capped_frames_2s"]
        assert proof["restored_frames_2s"] > 30
    finally:
        await asyncio.to_thread(
            stream.update, cpu_quota=original_quota, cpu_period=original_period
        )
        proof.update(windows=windows, deliveries=deliveries)
        (work_dir / "supervisor_cpu_stream_proof.json").write_text(
            json.dumps(
                proof,
                indent=2,
                default=lambda value: (
                    asdict(value) if is_dataclass(value) else str(value)
                ),
            )
        )
        client.close()
