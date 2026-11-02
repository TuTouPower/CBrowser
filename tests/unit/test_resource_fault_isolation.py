"""One Profile's diagnostics failure must not suspend another Profile's quota."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from cbrowser.supervisor.core import ActiveSession, SupervisorCore
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.resource_monitor import ProfileResourceTarget, ResourceMonitor
from cbrowser.supervisor.resource_policy import ResourcePolicyService
from docker.errors import NotFound


@pytest.mark.asyncio
async def test_visibility_failure_keeps_other_profile_in_sampling(tmp_path):
    async def visibility(profile, instance):
        if profile == "a":
            raise httpx.ConnectError("gateway unavailable")
        return True

    monitor = SimpleNamespace(sample=AsyncMock())
    core = SupervisorCore(
        SimpleNamespace(validator=PathValidator(tmp_path)),
        None,
        None,
        None,
        gateway_control=SimpleNamespace(has_foreground_viewers=visibility),
    )
    core.resource_monitor = monitor
    for profile in ("a", "b"):
        core._sessions[profile] = ActiveSession(profile, "i", 1, 30000, "b", "s")
    await core.sample_resources()
    targets = monitor.sample.call_args.args[0]
    assert {target.profile_id for target in targets} == {"a", "b"}
    assert (
        next(t for t in targets if t.profile_id == "a").has_foreground_viewers is None
    )
    assert (
        next(t for t in targets if t.profile_id == "b").has_foreground_viewers is True
    )


class Containers:
    def __init__(self):
        self.unavailable = set()

    def get(self, container_id):
        if container_id in self.unavailable:
            raise NotFound("container gone")
        return SimpleNamespace(attrs={"HostConfig": {}}, stats=lambda **_: {})


@pytest.mark.asyncio
async def test_missing_stats_and_failed_delivery_do_not_stop_healthy_profile(tmp_path):
    containers = Containers()
    containers.unavailable.add("ca")
    sent = []

    async def send(target, decision):
        if target.profile_id == "b":
            raise httpx.ConnectError("gateway unavailable")
        sent.append(target.profile_id)

    monitor = ResourceMonitor(
        ResourcePolicyService(SimpleNamespace(containers=containers)),
        send,
        host_stat_path=tmp_path / "absent_proc_stat",
    )
    targets = [ProfileResourceTarget(p, "i", ("c" + p,), True) for p in ("a", "b", "c")]
    await monitor.sample(targets)
    assert sent == ["c"]
    containers.unavailable.clear()
    await monitor.sample(targets)
    assert sent == ["c", "a"]


@pytest.mark.asyncio
async def test_malformed_stats_are_isolated_per_profile(tmp_path):
    class MalformedContainers:
        def get(self, container_id):
            if container_id == "ca":
                return SimpleNamespace(
                    attrs={"HostConfig": {}},
                    stats=lambda **_: (_ for _ in ()).throw(ValueError("bad stats")),
                )
            return SimpleNamespace(attrs={"HostConfig": {}}, stats=lambda **_: {})

    sent = []

    async def send(target, decision):
        sent.append(target.profile_id)

    monitor = ResourceMonitor(
        ResourcePolicyService(SimpleNamespace(containers=MalformedContainers())),
        send,
        host_stat_path=tmp_path / "absent_proc_stat",
    )
    targets = [ProfileResourceTarget(p, "i", ("c" + p,), True) for p in ("a", "b")]
    result = await monitor.sample(targets)
    assert sent == ["b"]
    assert result["failed_profiles"] == ["a"]


@pytest.mark.asyncio
async def test_unknown_visibility_or_missing_stats_cannot_clear_overload(tmp_path):
    from cbrowser.supervisor.resource_policy import ResourcePolicyConfig

    step = 1
    unavailable = False

    def get(container_id):
        if unavailable:
            raise NotFound("temporarily unavailable")
        raw = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": step * 900_000_000},
                "system_cpu_usage": step * 10_000_000_000,
                "online_cpus": 10,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": (step - 1) * 900_000_000},
                "system_cpu_usage": (step - 1) * 10_000_000_000,
            },
        }
        return SimpleNamespace(
            attrs={"HostConfig": {"NanoCpus": 1_000_000_000}},
            stats=lambda **_: raw,
        )

    policy = ResourcePolicyService(
        SimpleNamespace(containers=SimpleNamespace(get=get)),
        config=ResourcePolicyConfig(min_measurement_interval_sec=0),
    )
    caps = []

    async def send(target, decision):
        caps.append(decision.max_fps_cap)

    monitor = ResourceMonitor(policy, send, host_stat_path=tmp_path / "absent")
    target = ProfileResourceTarget("p", "i", ("c",), True)
    for value in (2, 3):
        step = value
        await monitor.sample([target])
    assert policy.get_decision("p").max_fps_cap == 8
    await monitor.sample([ProfileResourceTarget("p", "i", ("c",), None)])
    unavailable = True
    await monitor.sample([target])
    assert policy.get_decision("p").max_fps_cap == 8
    assert caps == [None, 8]
