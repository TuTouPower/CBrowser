"""Recover abnormal Browser exits using API intent and durable retry deadlines.

After an initial failure, retry at 2/10/30 seconds; block on failure four.
API instance fencing prevents stale Docker scans from counting another exit.
Normal exits and stopped intent never restart. Cleanup failures are bounded.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

import docker.errors
import httpx
from cbrowser.domain.models import ProfileConfig
from cbrowser.domain.runtime_policy import (
    AUTO_RETRY_DELAYS,
    BLOCK_AFTER_RUNTIME_FAILURES,
)
from cbrowser.supervisor.core import SupervisorCore

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

    async def tick(self) -> None:
        """Detect exits and schedule retries from persisted API state."""
        if self._closing:
            return

        now_mono = time.monotonic()

        # 1. Verify API availability; on network/auth/HTTP failure, keep healthy
        # containers
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
                return
            profiles_list = resp.json()
        except Exception as exc:
            logger.warning(
                "Recovery paused: API error_type=%s",
                type(exc).__name__,
            )
            return

        # 2. Scan active Docker containers
        try:
            containers = await asyncio.to_thread(
                self.core.docker.scan_active_containers
            )
        except Exception as exc:
            logger.warning(
                "Recovery paused: Docker scan error_type=%s",
                type(exc).__name__,
            )
            return

        docker_by_profile: dict[str, dict[str, dict[str, Any]]] = {}
        for c in containers:
            pid = c.get("profile_id")
            role = c.get("role")
            if pid and role:
                docker_by_profile.setdefault(pid, {})[role] = c

        # 3. Detect abnormal terminations (with strict API fencing to prevent double
        # reporting)
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

            # Stream dead while Browser healthy: isolate without killing Browser
            if b_status == "running" and (not s_c or s_c.get("status") != "running"):
                logger.warning(
                    "Profile %s has healthy Browser %s but missing/failed Stream %s. "
                    "Retaining healthy browser.",
                    pid,
                    b_c.get("id"),
                    s_c.get("id") if s_c else "none",
                )

            # Check if Browser container terminated abnormally (only
            # exited/dead count as terminated)
            if (
                b_status in {"exited", "dead"}
                and b_inst not in self._reported_dead_instances
            ):
                # Query authoritative API state before synthesizing exit event
                try:
                    rt_resp = await self.core.api.get(
                        f"/api/v1/internal/supervisor/profiles/{pid}/runtime",
                        headers=self.core._auth_headers(),
                    )
                except (httpx.HTTPError, OSError) as exc:
                    logger.debug(
                        "Failed to query runtime before exit synthesis: error_type=%s",
                        type(exc).__name__,
                    )
                    continue

                if rt_resp.status_code != 200:
                    continue
                rt_data = rt_resp.json()
                # Fencing checks:
                # a) If API desired_state is stopped, normal termination already cleared
                # intent
                if rt_data.get("desired_state") == "stopped":
                    continue
                # b) If API runtime_instance_id is already None, native exit or prior
                # event applied
                if rt_data.get("runtime_instance_id") is None:
                    continue
                # c) If API runtime_instance_id is for a different instance, do not
                # report stale event
                if rt_data.get("runtime_instance_id") != b_inst:
                    continue
                cfg_ver_val = b_c.get("config_version")
                if cfg_ver_val is None:
                    cfg_ver_val = rt_data.get("config_version")
                if cfg_ver_val is None:
                    continue
                cfg_ver = int(cfg_ver_val)

                # Prioritize native exit: if core recorded a native
                # exit awaiting delivery, wait for replay
                if self.core.has_native_exit(pid, b_inst, cfg_ver):
                    logger.info(
                        "Native exit pending: profile=%s instance=%s version=%s; "
                        "skipping synthetic Docker exit",
                        pid,
                        b_inst,
                        cfg_ver,
                    )
                    continue

                # Query actual ExitCode from docker container inspect
                exit_code = 137
                try:
                    c_obj = self.core.docker.client.containers.get(b_c["id"])
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
                        b_c["id"],
                        type(exc).__name__,
                    )

                if exit_code == 0:
                    exit_code = 1

                stable_event_id = f"docker_exit:{b_c['id'][:12]}:{b_inst}"

                logger.warning(
                    "Docker exit detected: container=%s profile=%s code=%s event=%s",
                    b_c["id"],
                    pid,
                    exit_code,
                    stable_event_id,
                )

                delivered = await self.core.events.emit_event(
                    event_id=stable_event_id,
                    profile_id=pid,
                    runtime_instance_id=b_inst,
                    event_type="exit",
                    exit_code=exit_code,
                    exit_reason="container_terminated",
                    config_version=cfg_ver,
                    payload={"source": "docker_recovery_scan", "exit_code": exit_code},
                )
                if delivered:
                    self._reported_dead_instances.add(b_inst)

        # 4. Check API runtime state for each profile and schedule retries if due
        for p_info in profiles_list:
            pid = p_info["id"]
            if self.core._get_profile_lock(pid).locked():
                continue

            try:
                rt_resp = await self.core.api.get(
                    f"/api/v1/internal/supervisor/profiles/{pid}/runtime",
                    headers=self.core._auth_headers(),
                )
                if rt_resp.status_code != 200:
                    continue
                rt = rt_resp.json()
            except (httpx.HTTPError, OSError, ValueError) as exc:
                logger.debug(
                    "Failed to fetch runtime for profile %s: error_type=%s",
                    pid,
                    type(exc).__name__,
                )
                continue

            desired_state = rt.get("desired_state")
            restart_blocked = rt.get("restart_blocked", False)
            failure_count = rt.get("failure_count", 0)
            last_exit_event_id = rt.get("last_exit_event_id")
            runtime_instance_id = rt.get("runtime_instance_id")
            cfg_version_bound = rt.get("config_version")
            roles = docker_by_profile.get(pid, {})
            b_c = roles.get("browser")
            s_c = roles.get("stream")

            # Check for missing runtime container:
            # API is bound to an active runtime_instance_id with running intent,
            # but no Browser container exists for this profile or instance.
            if (
                desired_state == "running"
                and not restart_blocked
                and runtime_instance_id is not None
                and (not b_c or b_c.get("instance_id") != runtime_instance_id)
            ):
                if cfg_version_bound is not None:
                    cfg_ver = int(cfg_version_bound)
                    # Check native exit first
                    if self.core.has_native_exit(pid, runtime_instance_id, cfg_ver):
                        logger.info(
                            "Native exit pending: profile=%s instance=%s version=%s; "
                            "skipping synthetic missing exit",
                            pid,
                            runtime_instance_id,
                            cfg_ver,
                        )
                    elif runtime_instance_id not in self._reported_dead_instances:
                        missing_event_id = f"missing_runtime:{runtime_instance_id}"
                        logger.warning(
                            "Missing runtime: profile=%s instance=%s cfg_version=%s",
                            pid,
                            runtime_instance_id,
                            cfg_ver,
                        )
                        delivered = await self.core.events.emit_event(
                            event_id=missing_event_id,
                            profile_id=pid,
                            runtime_instance_id=runtime_instance_id,
                            event_type="exit",
                            exit_code=1,
                            exit_reason="missing_runtime",
                            config_version=cfg_ver,
                            payload={
                                "source": "missing_runtime_recovery_scan",
                                "instance_id": runtime_instance_id,
                            },
                        )
                        if delivered:
                            self._reported_dead_instances.add(runtime_instance_id)
                        # Re-read runtime from API after emitting missing event
                        try:
                            rt_resp = await self.core.api.get(
                                f"/api/v1/internal/supervisor/profiles/{pid}/runtime",
                                headers=self.core._auth_headers(),
                            )
                            if rt_resp.status_code == 200:
                                rt = rt_resp.json()
                                desired_state = rt.get("desired_state")
                                restart_blocked = rt.get("restart_blocked", False)
                                failure_count = rt.get("failure_count", 0)
                                last_exit_event_id = rt.get("last_exit_event_id")
                                runtime_instance_id = rt.get("runtime_instance_id")
                        except (httpx.HTTPError, OSError):
                            pass
            restart_blocked = rt.get("restart_blocked", False)
            failure_count = rt.get("failure_count", 0)
            last_exit_event_id = rt.get("last_exit_event_id")
            runtime_instance_id = rt.get("runtime_instance_id")
            attempt_key = (last_exit_event_id, failure_count)
            previous_key = self._cleanup_attempt_keys.get(pid)
            if previous_key is not None and previous_key != attempt_key:
                await self._cancel_waiting_retry(pid)
                self._cleanup_failures.pop(pid, None)
                self._cleanup_cooldown_until.pop(pid, None)
            self._cleanup_attempt_keys[pid] = attempt_key

            # Condition 0: Not desired running, or blocked -> cancel any pending task
            if desired_state != "running" or restart_blocked:
                await self._cancel_waiting_retry(pid)
                self._cleanup_failures.pop(pid, None)
                self._cleanup_cooldown_until.pop(pid, None)
                continue

            if self._cleanup_failures.get(pid, 0) >= MAX_CLEANUP_ATTEMPTS:
                continue
            if now_mono < self._cleanup_cooldown_until.get(pid, 0.0):
                continue

            # Condition 1: Brand new profile (count=0 and no exit event) -> explicit RPC
            # launch only
            if failure_count == 0 and last_exit_event_id is None:
                continue

            # Condition 2: Already running and active according to API
            if runtime_instance_id is not None:
                roles = docker_by_profile.get(pid, {})
                b_c = roles.get("browser")
                s_c = roles.get("stream")
                if (
                    b_c
                    and s_c
                    and b_c.get("status") == "running"
                    and s_c.get("status") == "running"
                    and b_c.get("instance_id") == runtime_instance_id
                ):
                    self._cleanup_failures.pop(pid, None)
                    self._cleanup_cooldown_until.pop(pid, None)
                    continue

            # Condition 3: Check failure count bounds
            if failure_count >= BLOCK_AFTER_RUNTIME_FAILURES:
                continue

            # Calculate retry delay and due timestamp based on API durable updated_at
            if failure_count == 0:
                delay_sec = 0.0
            else:
                delay_sec = AUTO_RETRY_DELAYS[failure_count - 1]

            updated_at_str = rt.get("updated_at")
            if updated_at_str and delay_sec > 0.0:
                try:
                    updated_dt = datetime.fromisoformat(updated_at_str)
                    if updated_dt.tzinfo is None:
                        updated_dt = updated_dt.replace(tzinfo=UTC)
                    elapsed = (datetime.now(UTC) - updated_dt).total_seconds()
                    remaining = max(0.0, delay_sec - elapsed)
                except (ValueError, TypeError):
                    remaining = delay_sec
            else:
                remaining = 0.0

            # Schedule retry task if not already in flight
            async with self._lock:
                existing_task = self._in_flight_tasks.get(pid)
                if existing_task is not None and not existing_task.done():
                    continue

                task = asyncio.create_task(
                    self._execute_retry(pid, remaining, rt, p_info)
                )
                self._in_flight_tasks[pid] = task

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

            if current_rt.get("runtime_instance_id") is not None:
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
                except Exception as exc:
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

            # Resolve current immutable config version strictly from API
            config_version = profile_info.get("current_config_version")
            if config_version is None:
                config_version = current_rt.get("config_version")
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
        except Exception as exc:
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
