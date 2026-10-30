"""Collect Docker measurements off the event loop; compose policy serially."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from cbrowser.supervisor.resource_policy import (
    ProfileQuotaDecision,
    ResourcePolicyService,
    container_cpu_limit,
    parse_linux_proc_stat_cpu,
)
from docker.errors import DockerException

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProfileResourceTarget:
    profile_id: str
    runtime_instance_id: str
    container_ids: tuple[str, ...]
    has_foreground_viewers: bool | None


class ResourceMonitor:
    def __init__(
        self,
        policy: ResourcePolicyService,
        send_quota: Callable[
            [ProfileResourceTarget, ProfileQuotaDecision], Awaitable[None]
        ],
        host_stat_path: Path = Path("/proc/stat"),
    ) -> None:
        self.policy = policy
        self.send_quota = send_quota
        self.host_stat_path = host_stat_path
        self._lock = asyncio.Lock()
        self._delivered: dict[tuple[str, str], float | None] = {}
        self._instances: dict[str, str] = {}

    def _collect(
        self, targets: Sequence[ProfileResourceTarget]
    ) -> tuple[str | None, list, set[str]]:
        try:
            host = (
                self.host_stat_path.read_text()
                if self.host_stat_path.is_file()
                else None
            )
        except OSError as exc:
            logger.warning("Host sampling failed: error_type=%s", type(exc).__name__)
            host = None
        samples = []
        failed = set()
        for target in targets:
            if target.has_foreground_viewers is None:
                failed.add(target.profile_id)
                continue
            current = []
            try:
                for container_id in target.container_ids:
                    container = self.policy.docker_client.containers.get(container_id)
                    limit = container_cpu_limit(container.attrs.get("HostConfig", {}))
                    raw = container.stats(stream=False, one_shot=True)
                    current.append((target, container_id, raw, limit))
            except (DockerException, OSError) as exc:
                logger.warning(
                    "Profile sampling failed: profile=%s error_type=%s",
                    target.profile_id,
                    type(exc).__name__,
                )
                failed.add(target.profile_id)
                continue
            samples.extend(current)
        return host, samples, failed

    async def sample(self, targets: Sequence[ProfileResourceTarget]) -> dict[str, Any]:
        """Return the exact raw observations used by each resulting decision.

        No policy state is mutated in a worker thread. A failed delivery stays
        pending for the next window; instance replacement always receives a cap.
        """
        async with self._lock:
            host, samples, failed = await asyncio.to_thread(self._collect, targets)
            active = {target.profile_id for target in targets}
            for profile_id in set(self._instances) - active:
                self.policy.reset_profile(profile_id)
            active_instances = {
                (target.profile_id, target.runtime_instance_id) for target in targets
            }
            self._delivered = {
                key: cap
                for key, cap in self._delivered.items()
                if key in active_instances
            }
            for target in targets:
                if self._instances.get(target.profile_id) != target.runtime_instance_id:
                    self.policy.reset_profile(target.profile_id)
                if target.profile_id in failed:
                    continue
                state = self.policy.get_profile_state(target.profile_id)
                state.containers = {
                    key: value
                    for key, value in state.containers.items()
                    if key in target.container_ids
                }
                self.policy.evaluate_profile(
                    target.profile_id, target.has_foreground_viewers
                )
            self._instances = {
                target.profile_id: target.runtime_instance_id for target in targets
            }
            if host is not None:
                try:
                    self.policy.record_host_sample(parse_linux_proc_stat_cpu(host))
                except ValueError:
                    logger.warning("Host sampling returned invalid CPU counters")
            for target, container_id, raw, limit in samples:
                self.policy.record_stats(
                    target.profile_id,
                    container_id,
                    raw,
                    limit,
                    target.has_foreground_viewers,
                )
            decisions = {}
            for target in targets:
                if target.profile_id in failed:
                    decisions[target.profile_id] = self.policy.get_decision(
                        target.profile_id
                    )
                    continue
                decision = self.policy.evaluate_profile(target.profile_id)
                decisions[target.profile_id] = decision
                key = (target.profile_id, target.runtime_instance_id)
                if (
                    key not in self._delivered
                    or self._delivered[key] != decision.max_fps_cap
                ):
                    try:
                        await self.send_quota(target, decision)
                    except (httpx.HTTPError, OSError, ValueError) as exc:
                        logger.warning(
                            "Quota delivery failed: profile=%s error_type=%s",
                            target.profile_id,
                            type(exc).__name__,
                        )
                        continue
                    self._delivered[key] = decision.max_fps_cap
            return {
                "host_proc_stat": host,
                "container_samples": samples,
                "decisions": decisions,
                "failed_profiles": sorted(failed),
            }
