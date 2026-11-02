"""Recover abnormal Browser exits using API intent and durable retry deadlines.

After an initial failure, retry at 2/10/30 seconds; block on failure four.
API instance fencing prevents stale Docker scans from counting another exit.
Normal exits and stopped intent never restart. Cleanup failures are bounded.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import docker.errors
import httpx
from cbrowser.domain.models import ProfileConfig
from cbrowser.domain.runtime_policy import (
    AUTO_RETRY_DELAYS,
    BLOCK_AFTER_RUNTIME_FAILURES,
)
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.recovery_rules import (
    browser_terminated,
    exit_event_superseded,
    failure_budget_exhausted,
    index_containers_by_profile,
    is_brand_new_runtime,
    live_instance_ids,
    remaining_retry_seconds,
    retry_delay_for_failure,
    runtime_pair_active,
    stream_missing,
    terminal_observation,
)

logger = logging.getLogger("cbrowser.supervisor.recovery")

MAX_CLEANUP_ATTEMPTS = 3
INITIAL_CLEANUP_COOLDOWN = 5.0


class RecoveryCoordinator:
    """Coordinates abnormal exit detection and backoff-driven restarts."""

    def __init__(self, core: SupervisorCore) -> None:
        self.core = core
        self._in_flight_tasks: dict[str, asyncio.Task] = {}
        self._sleeping_tasks: set[asyncio.Task] = set()
        self._closing = False
        self._lock = asyncio.Lock()
        self._reported_dead_instances: set[str] = set()
        self._cleanup_failures: dict[str, int] = {}
        self._cleanup_cooldown_until: dict[str, float] = {}
        self._cleanup_attempt_keys: dict[str, tuple[str | None, int]] = {}

    async def close(self) -> None:
        """Cancel pending retries without terminating healthy containers."""
        self._closing = True
        async with self._lock:
            tasks = list(self._in_flight_tasks.values())
            self._in_flight_tasks.clear()
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("RecoveryCoordinator closed.")

    async def _cancel_waiting_retry(self, profile_id: str) -> None:
        task = self._in_flight_tasks.get(profile_id)
        if task is not None and task in self._sleeping_tasks:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def tick(
        self, *, containers: list[dict[str, Any]] | None = None
    ) -> None:
        """Detect exits and schedule retries from persisted API state.

        ``containers`` may carry the event-driven scan snapshot so the recovery
        loop does not rescan Docker every second.
        """
        if self._closing:
            return

        now_mono = time.monotonic()
        profiles_list = await self._observe_profiles()
        if profiles_list is None:
            return
        if containers is None:
            containers = await self._scan_containers()
            if containers is None:
                return

        docker_by_profile = index_containers_by_profile(containers)
        await self._classify_abnormal_exits(docker_by_profile)
        live_instances = live_instance_ids(docker_by_profile)
        known_profiles = await self._schedule_retries(
            profiles_list, docker_by_profile, live_instances, now_mono
        )
        self._prune_recovery_state(live_instances, known_profiles)

    async def _observe_profiles(self) -> list[dict[str, Any]] | None:
        try:
            resp = await self.core.api.get(
                "/api/v1/internal/supervisor/profiles",
                headers=self.core._auth_headers(),
            )
            if resp.status_code != 200:
                logger.warning(
                    "Recovery paused: API profiles status=%s",
                    resp.status_code,
                )
                return None
            return resp.json()
        except Exception as exc:  # noqa: BLE001 - API availability probe error pauses recovery iteration
            logger.warning(
                "Recovery paused: API error_type=%s",
                type(exc).__name__,
            )
            return None

    async def _scan_containers(self) -> list[dict[str, Any]] | None:
        try:
            return await asyncio.to_thread(
                self.core.docker.scan_active_containers
            )
        except Exception as exc:  # noqa: BLE001 - docker scan failure pauses recovery iteration
            logger.warning(
                "Recovery paused: Docker scan error_type=%s",
                type(exc).__name__,
            )
            return None

    async def _classify_abnormal_exits(
        self, docker_by_profile: dict[str, dict[str, dict[str, Any]]]
    ) -> None:
        for pid, roles in docker_by_profile.items():
            if self.core._get_profile_lock(pid).locked():
                continue

            b_c = roles.get("browser")
            s_c = roles.get("stream")
            if not b_c:
                continue

            b_status = b_c.get("status")
            b_inst = b_c.get("instance_id")
            if not b_inst:
                continue

            if stream_missing(b_status, s_c):
                logger.warning(
                    "Profile %s has healthy Browser %s but missing/failed Stream %s. "
                    "Keeping the Browser for this pass; the automatic retry "
                    "rebuilds the whole pair.",
                    pid,
                    b_c.get("id"),
                    s_c.get("id") if s_c else "none",
                )

            if browser_terminated(b_status, b_inst, self._reported_dead_instances):
                await self._report_browser_exit(pid, b_c, b_inst)
            elif b_status == "running" and b_inst not in self._reported_dead_instances:
                obs = await self.core._reconcile_instance_observation(
                    pid,
                    b_inst,
                    int(b_c.get("config_version", 1)),
                    container_status=b_status,
                )
                if obs in ("stopped", "error"):
                    self._reported_dead_instances.add(b_inst)

    async def _report_browser_exit(
        self, profile_id: str, browser: dict[str, Any], instance_id: str
    ) -> None:
        try:
            rt_resp = await self.core.api.get(
                f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime",
                headers=self.core._auth_headers(),
            )
        except (httpx.HTTPError, OSError) as exc:
            logger.debug(
                "Failed to query runtime before exit synthesis: error_type=%s",
                type(exc).__name__,
            )
            return

        if rt_resp.status_code != 200:
            return
        runtime = rt_resp.json()
        if exit_event_superseded(runtime, instance_id):
            return

        config_version_value = browser.get("config_version")
        if config_version_value is None:
            config_version_value = runtime.get("config_version")
        if config_version_value is None:
            return
        config_version = int(config_version_value)

        if self.core.has_native_exit(profile_id, instance_id, config_version):
            logger.info(
                "Native exit pending: profile=%s instance=%s version=%s; "
                "skipping synthetic Docker exit",
                profile_id,
                instance_id,
                config_version,
            )
            return

        exit_code = self._inspect_exit_code(browser)
        logger.warning(
            "Docker exit detected: container=%s profile=%s code=%s",
            browser["id"],
            profile_id,
            exit_code,
        )
        observed_state, reason = terminal_observation(exit_code)
        reported = await self.core.report_terminal_observation(
            profile_id,
            instance_id,
            config_version,
            observed_state=observed_state,
            reason=reason,
        )
        if reported:
            self._reported_dead_instances.add(instance_id)

    def _inspect_exit_code(self, browser: dict[str, Any]) -> int:
        exit_code = 137
        try:
            c_obj = self.core.docker.client.containers.get(browser["id"])
            inspect_state = c_obj.attrs.get("State", {})
            inspect_ec = inspect_state.get("ExitCode")
            if inspect_ec is not None:
                exit_code = int(inspect_ec)
        except (
            docker.errors.DockerException,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            logger.debug(
                "Failed to inspect container %s for ExitCode: error_type=%s",
                browser["id"],
                type(exc).__name__,
            )
        return exit_code

    async def _schedule_retries(
        self,
        profiles_list: list[dict[str, Any]],
        docker_by_profile: dict[str, dict[str, dict[str, Any]]],
        live_instances: set[str],
        now_mono: float,
    ) -> set[str]:
        known_profiles: set[str] = set()
        for p_info in profiles_list:
            pid = p_info["id"]
            known_profiles.add(pid)
            if self.core._get_profile_lock(pid).locked():
                continue
            runtime = await self._fetch_runtime(pid)
            if runtime is None:
                continue
            if runtime.get("runtime_instance_id"):
                live_instances.add(runtime["runtime_instance_id"])
            await self._schedule_profile_retry(
                pid, p_info, runtime, docker_by_profile, now_mono
            )
        return known_profiles

    async def _fetch_runtime(self, profile_id: str) -> dict[str, Any] | None:
        try:
            rt_resp = await self.core.api.get(
                f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime",
                headers=self.core._auth_headers(),
            )
            if rt_resp.status_code != 200:
                return None
            return rt_resp.json()
        except (httpx.HTTPError, OSError, ValueError) as exc:
            logger.debug(
                "Failed to fetch runtime for profile %s: error_type=%s",
                profile_id,
                type(exc).__name__,
            )
            return None

    async def _schedule_profile_retry(
        self,
        profile_id: str,
        profile_info: dict[str, Any],
        runtime: dict[str, Any],
        docker_by_profile: dict[str, dict[str, dict[str, Any]]],
        now_mono: float,
    ) -> None:
        desired_state = runtime.get("desired_state")
        observed_state = runtime.get("observed_state")
        restart_blocked = runtime.get("restart_blocked", False)
        failure_count = runtime.get("failure_count", 0)
        last_exit_event_id = runtime.get("last_exit_event_id")
        runtime_instance_id = runtime.get("runtime_instance_id")
        config_version_bound = runtime.get("config_version")
        roles = docker_by_profile.get(profile_id, {})
        browser = roles.get("browser")
        stream = roles.get("stream")

        if (
            desired_state == "running"
            and not restart_blocked
            and runtime_instance_id is not None
            and (not browser or browser.get("instance_id") != runtime_instance_id)
            and config_version_bound is not None
        ):
            runtime = await self._compensate_missing_runtime(
                profile_id, runtime, runtime_instance_id, config_version_bound
            )
            desired_state = runtime.get("desired_state")

        restart_blocked = runtime.get("restart_blocked", False)
        failure_count = runtime.get("failure_count", 0)
        last_exit_event_id = runtime.get("last_exit_event_id")
        runtime_instance_id = runtime.get("runtime_instance_id")
        attempt_key = (last_exit_event_id, failure_count)
        previous_key = self._cleanup_attempt_keys.get(profile_id)
        if previous_key is not None and previous_key != attempt_key:
            await self._cancel_waiting_retry(profile_id)
            self._cleanup_failures.pop(profile_id, None)
            self._cleanup_cooldown_until.pop(profile_id, None)
        self._cleanup_attempt_keys[profile_id] = attempt_key

        if desired_state != "running" or restart_blocked:
            await self._cancel_waiting_retry(profile_id)
            self._cleanup_failures.pop(profile_id, None)
            self._cleanup_cooldown_until.pop(profile_id, None)
            return

        if self._cleanup_failures.get(profile_id, 0) >= MAX_CLEANUP_ATTEMPTS:
            return
        if now_mono < self._cleanup_cooldown_until.get(profile_id, 0.0):
            return

        if is_brand_new_runtime(failure_count, last_exit_event_id):
            return

        if runtime_instance_id is not None and runtime_pair_active(
            observed_state, runtime_instance_id, browser, stream
        ):
            self._cleanup_failures.pop(profile_id, None)
            self._cleanup_cooldown_until.pop(profile_id, None)
            return

        if failure_budget_exhausted(failure_count, BLOCK_AFTER_RUNTIME_FAILURES):
            return

        delay_sec = retry_delay_for_failure(failure_count)
        remaining = remaining_retry_seconds(runtime.get("updated_at"), delay_sec)

        async with self._lock:
            existing_task = self._in_flight_tasks.get(profile_id)
            if existing_task is not None and not existing_task.done():
                return

            task = asyncio.create_task(
                self._execute_retry(profile_id, remaining, runtime, profile_info)
            )
            self._in_flight_tasks[profile_id] = task

    async def _compensate_missing_runtime(
        self,
        profile_id: str,
        runtime: dict[str, Any],
        instance_id: str,
        config_version_bound: int,
    ) -> dict[str, Any]:
        config_version = int(config_version_bound)
        if self.core.has_native_exit(profile_id, instance_id, config_version):
            logger.info(
                "Native exit pending: profile=%s instance=%s version=%s; "
                "skipping synthetic missing exit",
                profile_id,
                instance_id,
                config_version,
            )
            return runtime

        if instance_id in self._reported_dead_instances:
            return runtime

        logger.warning(
            "Missing runtime: profile=%s instance=%s cfg_version=%s",
            profile_id,
            instance_id,
            config_version,
        )
        reported = await self.core.report_terminal_observation(
            profile_id,
            instance_id,
            config_version,
            observed_state="error",
            reason="missing_runtime",
        )
        if reported:
            self._reported_dead_instances.add(instance_id)
        try:
            rt_resp = await self.core.api.get(
                f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime",
                headers=self.core._auth_headers(),
            )
            if rt_resp.status_code == 200:
                return rt_resp.json()
        except (httpx.HTTPError, OSError):
            pass
        return runtime

    def _prune_recovery_state(
        self, live_instances: set[str], known_profiles: set[str]
    ) -> None:
        self._reported_dead_instances.intersection_update(live_instances)
        for stale_pid in set(self._cleanup_attempt_keys) - known_profiles:
            self._cleanup_attempt_keys.pop(stale_pid, None)
            self._cleanup_failures.pop(stale_pid, None)
            self._cleanup_cooldown_until.pop(stale_pid, None)

    async def _execute_retry(
        self,
        profile_id: str,
        delay: float,
        initial_rt: dict[str, Any],
        profile_info: dict[str, Any],
    ) -> None:
        """Execute delayed restart with pre-wake intent and state validation."""
        try:
            if delay > 0:
                logger.info(
                    "Profile %s retry scheduled in %.2fs (attempt %s/%s).",
                    profile_id,
                    delay,
                    initial_rt.get("failure_count", 0),
                    len(AUTO_RETRY_DELAYS),
                )
                task = asyncio.current_task()
                self._sleeping_tasks.add(task)
                try:
                    await asyncio.sleep(delay)
                finally:
                    self._sleeping_tasks.discard(task)

            if self._closing:
                return

            # Re-read authoritative API state to prevent stale retry overriding new user
            # intent
            try:
                rt_resp = await self.core.api.get(
                    f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime",
                    headers=self.core._auth_headers(),
                )
                if rt_resp.status_code != 200:
                    logger.warning(
                        "Retry for %s aborted: API runtime query failed (%s).",
                        profile_id,
                        rt_resp.status_code,
                    )
                    return
                current_rt = rt_resp.json()
            except (httpx.HTTPError, OSError) as exc:
                logger.warning(
                    "Retry for %s aborted: API error: error_type=%s.",
                    profile_id,
                    type(exc).__name__,
                )
                return

            if current_rt.get("desired_state") != "running":
                logger.info(
                    "Retry for %s aborted: desired_state is %s.",
                    profile_id,
                    current_rt.get("desired_state"),
                )
                return

            if current_rt.get("restart_blocked"):
                logger.info(
                    "Retry for %s aborted: profile is restart_blocked.", profile_id
                )
                return

            if current_rt.get("last_exit_event_id") != initial_rt.get(
                "last_exit_event_id"
            ):
                logger.info(
                    "Retry for %s aborted: exit event was superseded.", profile_id
                )
                return

            if current_rt.get("failure_count") != initial_rt.get("failure_count"):
                logger.info("Retry for %s aborted: failure count changed.", profile_id)
                return

            if current_rt.get("runtime_instance_id") is not None and current_rt.get(
                "observed_state"
            ) not in ("error", "stopped"):
                logger.info(
                    "Retry for %s aborted: instance already active (%s).",
                    profile_id,
                    current_rt.get("runtime_instance_id"),
                )
                return

            # Clean up residual old pair if any
            containers = await asyncio.to_thread(
                self.core.docker.scan_active_containers
            )
            owned = [c for c in containers if c.get("profile_id") == profile_id]
            if owned:
                old_inst = owned[0].get("instance_id")
                event_id = initial_rt.get("last_exit_event_id") or "manual"
                try:
                    await self.core.stop_profile(
                        profile_id,
                        expected_instance=old_inst,
                        operation_id=f"retry_cleanup:{event_id}",
                    )
                    self._cleanup_failures.pop(profile_id, None)
                    self._cleanup_cooldown_until.pop(profile_id, None)
                except Exception as exc:  # noqa: BLE001 - retry cleanup failure records cooldown backoff
                    curr_fail = self._cleanup_failures.get(profile_id, 0) + 1
                    self._cleanup_failures[profile_id] = curr_fail
                    cooldown = min(30.0, INITIAL_CLEANUP_COOLDOWN * curr_fail)
                    self._cleanup_cooldown_until[profile_id] = (
                        time.monotonic() + cooldown
                    )
                    logger.warning(
                        "Cleanup failed: profile=%s attempt=%s/%s "
                        "cooldown=%.1fs error_type=%s",
                        profile_id,
                        curr_fail,
                        MAX_CLEANUP_ATTEMPTS,
                        cooldown,
                        type(exc).__name__,
                    )
                    return

            # Clear stale Chromium singleton locks left by killed instances
            try:
                user_data_dir = self.core.docker.validator.get_profile_data_dir(
                    profile_id
                )
                if user_data_dir.is_dir():
                    for lock_name in (
                        "SingletonLock",
                        "SingletonCookie",
                        "SingletonSocket",
                    ):
                        lock_path = user_data_dir / lock_name
                        if lock_path.is_symlink() or lock_path.exists():
                            lock_path.unlink(missing_ok=True)
            except OSError as exc:
                logger.debug(
                    "Error clearing singleton locks for %s: error_type=%s",
                    profile_id,
                    type(exc).__name__,
                )

            # Recover with the geometry the failed instance was actually bound
            # to; an unapplied edit must not silently take effect on restart.
            config_version = current_rt.get("config_version")
            if config_version is None:
                config_version = profile_info.get("current_config_version")
            if config_version is None:
                raise ValueError(
                    f"Profile {profile_id} lacks authoritative config_version"
                )

            profile_config = await self._load_profile_config(
                profile_id, int(config_version)
            )

            # Start new profile instance
            logger.info(
                "Executing recovery start for profile %s (v%s).",
                profile_id,
                config_version,
            )
            await self.core.start_profile(
                profile_id=profile_id,
                config=profile_config,
                config_version=int(config_version),
            )
            logger.info("Recovery start succeeded for profile %s.", profile_id)
            self._cleanup_failures.pop(profile_id, None)
            self._cleanup_cooldown_until.pop(profile_id, None)

        except asyncio.CancelledError:
            logger.info("Retry task for profile %s cancelled.", profile_id)
            raise
        except Exception as exc:  # noqa: BLE001 - background recovery retry task failure isolated per profile
            logger.error(
                "Recovery retry execution failed for profile %s: error_type=%s",
                profile_id,
                type(exc).__name__,
            )
        finally:
            async with self._lock:
                if self._in_flight_tasks.get(profile_id) is asyncio.current_task():
                    self._in_flight_tasks.pop(profile_id, None)

    async def _load_profile_config(
        self,
        profile_id: str,
        config_version: int,
        profile_info: dict[str, Any] | None = None,
    ) -> ProfileConfig:
        """Fetch and verify the immutable configuration snapshot."""
        ver_resp = await self.core.api.get(
            f"/api/v1/internal/supervisor/profiles/{profile_id}/versions/{config_version}",
            headers=self.core._auth_headers(),
        )
        ver_resp.raise_for_status()
        payload = ver_resp.json()
        if payload.get("profile_id") != profile_id:
            raise ValueError("Config version snapshot profile mismatch")
        if int(payload.get("version", 0)) != int(config_version):
            raise ValueError("Config version snapshot version mismatch")
        raw_config = payload.get("config")
        if not isinstance(raw_config, dict):
            raise TypeError("Invalid config payload in version snapshot")
        return ProfileConfig(**raw_config)
