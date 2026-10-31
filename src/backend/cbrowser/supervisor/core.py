"""CBrowser Runtime Supervisor Core Coordinator.

AC-001 - AC-006:
- Sole Docker socket holder.
- Dual-container lifecycle & port allocation.
- Idempotent lifecycle execution.
- Orderly stop: disconnect viewers, stop Stream/Browser, then release ports.
- Offline event queuing and recovery.
- Three retries with 2s/10s/30s backoff; block after four runtime failures.
- Crash recovery & existing container scanning on startup.
- Authenticated internal RPC to API (/api/v1/internal/supervisor) with Bearer token.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from cbrowser.domain.models import ConfigVersionSnapshot, ProfileConfig
from cbrowser.supervisor.agent_credentials import AgentCredentials
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.file_storage import atomic_write_text
from cbrowser.supervisor.gateway_client import GatewayControlClient
from cbrowser.supervisor.operation_journal import OperationJournal
from cbrowser.supervisor.port_allocator import PortAllocator
from cbrowser.supervisor.resource_monitor import ProfileResourceTarget, ResourceMonitor
from docker.errors import NotFound

logger = logging.getLogger("cbrowser.supervisor.core")


def browser_runtime_ready(
    runtime_dir: Path, profile_id: str, instance_id: str, config_version: int
) -> bool:
    """Require current-instance readiness, not files left by a prior Browser."""
    required = ("x11/X99", "pulse/pulse.sock", "Xauthority", "agent.sock")
    if not all((runtime_dir / path).exists() for path in required):
        return False
    try:
        info = json.loads((runtime_dir / "runner_info.json").read_text())
        return (
            info["profile_id"] == profile_id
            and info["runtime_instance_id"] == instance_id
            and info["config_version"] == config_version
            and isinstance(info["browser_pid"], int)
            and info["browser_pid"] > 0
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


@dataclass
class ActiveSession:
    profile_id: str
    runtime_instance_id: str
    config_version: int
    udp_mux_port: int
    browser_container_id: str
    stream_container_id: str
    desired_state: str = "running"
    observed_state: str = "running"


class SupervisorCore:
    def __init__(
        self,
        docker_adapter: DockerAdapter,
        port_allocator: PortAllocator,
        event_forwarder: EventForwarder,
        api_client: httpx.AsyncClient,
        gateway_url: str = "ws://host.docker.internal:18097",
        token_file: Optional[Path | str] = None,
        agent_key_file: Optional[Path | str] = None,
        gateway_control: GatewayControlClient | None = None,
        gateway_container_id: str | None = None,
        coturn_container_id: str | None = None,
    ):
        self.docker = docker_adapter
        self.ports = port_allocator
        self.events = event_forwarder
        self.api = api_client
        self.gateway_url = gateway_url
        self._token_file = Path(token_file) if token_file else None
        self.agent_credentials = (
            AgentCredentials(agent_key_file) if agent_key_file else None
        )
        self.gateway_control = gateway_control
        self.resource_monitor: ResourceMonitor | None = None
        self.gateway_container_id = gateway_container_id
        self.coturn_container_id = coturn_container_id

        self._sessions: Dict[str, ActiveSession] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self._native_exit_instances: set[tuple[str, str, int]] = set()
        self.operations = OperationJournal(
            self.docker.validator.validate_safe_path(
                self.docker.validator.data_root / "control" / "operations",
                allow_create=True,
            )
        )

    def _get_bearer_token(self) -> Optional[str]:
        if self._token_file and self._token_file.is_file():
            return self._token_file.read_text(encoding="utf-8").strip()
        return None

    def _auth_headers(self) -> dict[str, str]:
        token = self._get_bearer_token()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def _get_profile_lock(self, profile_id: str) -> asyncio.Lock:
        if profile_id not in self._locks:
            self._locks[profile_id] = asyncio.Lock()
        return self._locks[profile_id]

    async def scan_and_reconcile_existing(self) -> None:
        """Reconcile Docker labels and ports with authenticated API state."""
        containers = await asyncio.to_thread(self.docker.scan_active_containers)
        logger.info(f"Container scan found {len(containers)} containers.")

        profiles_found: dict[str, dict[str, Any]] = {}
        for c in containers:
            pid = c.get("profile_id")
            role = c.get("role")
            if pid and role:
                profiles_found.setdefault(pid, {})[role] = c

        for pid, roles in profiles_found.items():
            if self._get_profile_lock(pid).locked():
                continue
            b_c = roles.get("browser")
            s_c = roles.get("stream")

            # Integrity check: both browser and stream must exist
            if not b_c or not s_c:
                logger.warning(
                    "Incomplete sandbox retained: profile=%s browser=%s stream=%s",
                    pid,
                    bool(b_c),
                    bool(s_c),
                )
                continue

            # Integrity check: instance_id on both containers must match
            b_inst = b_c.get("instance_id")
            s_inst = s_c.get("instance_id")
            if not b_inst or b_inst != s_inst:
                logger.warning(
                    "Sandbox instance mismatch: profile=%s browser=%s stream=%s",
                    pid,
                    b_inst,
                    s_inst,
                )
                continue

            # Query API desired state with network/HTTP failure protection
            try:
                resp = await self.api.get(
                    f"/api/v1/internal/supervisor/profiles/{pid}/runtime",
                    headers=self._auth_headers(),
                )
            except Exception as e:
                logger.warning(
                    "API unavailable; retaining profile=%s error_type=%s",
                    pid,
                    type(e).__name__,
                )
                continue

            if resp.status_code == 200:
                rt = resp.json()
                if self._get_profile_lock(pid).locked():
                    continue
                desired = rt.get("desired_state", "stopped")
                api_inst = rt.get("runtime_instance_id")

                # Fence check: if API instance does not match container instance
                if desired == "running" and api_inst != b_inst:
                    logger.warning(
                        "Instance fence mismatch: profile=%s docker=%s api=%s",
                        pid,
                        b_inst,
                        api_inst,
                    )
                    continue

                if desired == "running" and any(
                    item["status"] != "running" for item in (b_c, s_c)
                ):
                    session = self._sessions.get(pid)
                    if session is not None and session.runtime_instance_id == b_inst:
                        session.observed_state = "error"
                    continue

                if desired == "stopped":
                    logger.info(
                        "Stopping sandbox for stopped intent: profile=%s",
                        pid,
                    )
                    if pid not in self._sessions:
                        self._sessions[pid] = ActiveSession(
                            pid,
                            b_inst,
                            rt.get("config_version", 1),
                            0,
                            b_c["id"],
                            s_c["id"],
                            desired_state="stopped",
                        )
                    await self.stop_profile(pid)
                else:
                    if not all(item.get("policy_ready") is True for item in (b_c, s_c)):
                        logger.warning(
                            "Unprotected sandbox not adopted: profile=%s", pid
                        )
                        continue
                    if self.gateway_control is None:
                        raise RuntimeError(
                            "Gateway control RPC is required for readiness"
                        )
                    try:
                        await self.gateway_control.has_foreground_viewers(pid, b_inst)
                    except (httpx.HTTPError, OSError, ValueError):
                        continue
                    # Restore UDP port from Stream container HostConfig port bindings
                    actual_port = None
                    try:
                        s_inspect = self.docker.client.api.inspect_container(s_c["id"])
                        port_bindings = s_inspect.get("HostConfig", {}).get(
                            "PortBindings", {}
                        )
                        for k, v in port_bindings.items():
                            if k.endswith("/udp") and v:
                                actual_port = int(v[0]["HostPort"])
                                break
                    except Exception as e:
                        logger.warning(
                            "Stream port inspection failed: container=%s error_type=%s",
                            s_c["id"],
                            type(e).__name__,
                        )

                    if actual_port:
                        port = await self.ports.restore(pid, actual_port)
                    else:
                        raise DockerSandboxError(
                            "Existing Stream has no verified UDP mux mapping"
                        )

                    if self._get_profile_lock(pid).locked():
                        continue
                    logger.info(
                        "Restoring running session: profile=%s port=%s",
                        pid,
                        port,
                    )
                    self._sessions[pid] = ActiveSession(
                        profile_id=pid,
                        runtime_instance_id=b_inst,
                        config_version=rt.get("config_version", 1),
                        udp_mux_port=port,
                        browser_container_id=b_c["id"],
                        stream_container_id=s_c["id"],
                        desired_state="running",
                        observed_state="running",
                    )
                    if rt.get("observed_state") != "running":
                        await self._report_observed(
                            pid, b_inst, "running", rt["config_version"]
                        )
            elif resp.status_code == 404:
                # Only 404 means Profile was deleted permanently from API
                logger.info(
                    "Cleaning orphan sandbox after API 404: profile=%s",
                    pid,
                )
                await self.docker.teardown_profile(pid)
                await self.ports.release(pid)
                self._sessions.pop(pid, None)
            else:
                # 401, 403, 429, 5xx, 503: Keep healthy containers, do NOT teardown
                logger.warning(
                    "Retaining sandbox: profile=%s api_status=%s",
                    pid,
                    resp.status_code,
                )

    async def consume_disk_events(self) -> int:
        """Forward instance-fenced native runtime journals to the API."""
        total_forwarded = 0
        events_root = self.docker.validator.data_root / "runtime-events"
        if not events_root.is_dir():
            return 0
        for p_dir in events_root.iterdir():
            if not p_dir.is_dir():
                continue
            profile_id = p_dir.name
            runtime_events = p_dir / "events" / "runtime"
            for evt_file in runtime_events.glob("*/*.json"):
                try:
                    self.docker.validator.validate_safe_path(evt_file)
                    data = json.loads(evt_file.read_text(encoding="utf-8"))
                    if (
                        data.get("profile_id") != profile_id
                        or data.get("runtime_instance_id") != evt_file.parent.name
                    ):
                        logger.warning(
                            "Rejected runtime event with mismatched directory identity"
                        )
                        continue
                    etype = data.get("event_type")
                    ecode = data.get("exit_code")
                    if not etype:
                        continue
                    if etype == "exit" and ecode is None:
                        continue

                    config_version = data.get("config_version")
                    if (
                        etype == "exit"
                        and type(ecode) is int
                        and type(config_version) is int
                        and config_version >= 1
                    ):
                        self._native_exit_instances.add(
                            (profile_id, data["runtime_instance_id"], config_version)
                        )

                    evt_id = data.get("event_id", evt_file.stem)
                    delivered = await self.events.emit_event(
                        event_id=evt_id,
                        profile_id=data.get("profile_id", profile_id),
                        runtime_instance_id=data.get("runtime_instance_id", "unknown"),
                        event_type=etype,
                        exit_code=ecode,
                        exit_reason=data.get("exit_reason"),
                        config_version=data.get("config_version", 1),
                        payload=data.get("payload", {}),
                    )
                    if delivered:
                        session = self._sessions.get(profile_id)
                        if (
                            ecode == 0
                            and data.get("exit_reason") == "normal"
                            and session is not None
                            and session.runtime_instance_id
                            == data.get("runtime_instance_id")
                        ):
                            logger.info(
                                "Normal Chrome exit: profile=%s",
                                profile_id,
                            )
                            session.observed_state = "stopped"
                        total_forwarded += 1
                except Exception as e:
                    logger.warning(
                        "Disk event processing failed: error_type=%s", type(e).__name__
                    )
        return total_forwarded

    def has_native_exit(
        self, profile_id: str, instance_id: str, config_version: int
    ) -> bool:
        """A native exit awaiting delivery takes precedence over synthetic exits."""
        return (profile_id, instance_id, config_version) in self._native_exit_instances

    async def start_profile(
        self,
        profile_id: str,
        config: ProfileConfig,
        config_version: int = 1,
        force: bool = False,
        operation_id: str | None = None,
    ) -> ActiveSession:
        """Idempotently start dual-container runtime for profile_id."""
        if self.agent_credentials is None:
            raise ValueError("Explicit Agent authentication key file is required")
        lock = self._get_profile_lock(profile_id)
        async with lock:
            if profile_id in self._sessions:
                session = self._sessions[profile_id]
                if session.observed_state == "running":
                    logger.info(
                        "Profile already active: profile=%s instance=%s",
                        profile_id,
                        session.runtime_instance_id,
                    )
                    return session
                raise RuntimeError(
                    "Existing runtime must finish cleanup before a new start"
                )

            if force:
                if not operation_id:
                    raise ValueError("Manual retry requires an idempotent operation ID")
                await self.reset_blocked(profile_id, operation_id)
            state_response = await self.api.get(
                f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime",
                headers=self._auth_headers(),
            )
            state_response.raise_for_status()
            runtime = state_response.json()
            if runtime["desired_state"] != "running":
                raise RuntimeError(
                    "API running intent is required before starting a runtime"
                )

            if runtime["restart_blocked"]:
                raise RuntimeError("Automatic retries exhausted; manual retry required")

            runtime_instance_id = f"inst_{uuid.uuid4().hex[:12]}"
            dirs = self.docker.prepare_profile_directories(profile_id)

            snap_path = dirs["runtime"] / "snapshot.json"
            snapshot = ConfigVersionSnapshot(
                id=f"snap_{uuid.uuid4().hex[:12]}",
                profile_id=profile_id,
                version=config_version,
                config=config.model_dump(),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            atomic_write_text(snap_path, snapshot.model_dump_json(indent=2), mode=0o644)

            # Bind runtime instance via internal supervisor API
            try:
                bind_resp = await self.api.post(
                    f"/api/v1/internal/supervisor/runtimes/bind?profile_id={profile_id}",
                    headers=self._auth_headers(),
                    json={
                        "runtime_instance_id": runtime_instance_id,
                        "config_version": config_version,
                    },
                )
                if bind_resp.status_code != 200:
                    raise RuntimeError(
                        f"API instance binding failed: status={bind_resp.status_code}"
                    )
            except Exception as e:
                logger.error("Instance binding failed: error_type=%s", type(e).__name__)
                raise

            try:
                # A bound attempt must report failure even before Docker creation.
                if not self.coturn_container_id:
                    raise DockerSandboxError(
                        "coturn infrastructure container is required to start runtime"
                    )
                port = await self.ports.allocate(profile_id)
                await self.docker.create_profile_network(profile_id)
                media_addresses = None
                if self.coturn_container_id:
                    media_addresses = await asyncio.to_thread(
                        self.docker.attach_profile_infrastructure,
                        profile_id,
                        self.gateway_container_id,
                        self.coturn_container_id,
                    )
                await self._report_observed(
                    profile_id, runtime_instance_id, "starting", config_version
                )

                b_container = await self.docker.start_browser_container(
                    profile_id=profile_id,
                    runtime_instance_id=runtime_instance_id,
                    snapshot_json_path=snap_path,
                )

                for _ in range(150):
                    if browser_runtime_ready(
                        dirs["runtime"], profile_id, runtime_instance_id, config_version
                    ):
                        break
                    await asyncio.sleep(0.2)
                if not browser_runtime_ready(
                    dirs["runtime"], profile_id, runtime_instance_id, config_version
                ):
                    raise DockerSandboxError(
                        "Timed out waiting for current Browser instance readiness"
                    )

                # Launch Stream
                agent_secret = dirs["runtime"] / "agent_secret.txt"
                atomic_write_text(
                    agent_secret,
                    self.agent_credentials.token_for(profile_id, runtime_instance_id),
                    mode=0o644,
                )
                s_container = await self.docker.start_stream_container(
                    profile_id=profile_id,
                    runtime_instance_id=runtime_instance_id,
                    browser_container_name=b_container.name,
                    udp_mux_port=port,
                    gateway_url=(
                        media_addresses.get("gateway_url") if media_addresses else None
                    )
                    or self.gateway_url,
                    agent_secret_path=agent_secret,
                    media_addresses=media_addresses,
                )

                if self.gateway_control is None:
                    raise RuntimeError("Gateway control RPC is required for readiness")
                async with asyncio.timeout(15):
                    while True:
                        s_container.reload()
                        if s_container.status != "running":
                            raise DockerSandboxError(
                                "Stream exited before registration"
                            )
                        try:
                            await self.gateway_control.has_foreground_viewers(
                                profile_id, runtime_instance_id
                            )
                            break
                        except httpx.HTTPStatusError as exc:
                            if exc.response.status_code != 503:
                                raise
                        except httpx.TransportError:
                            pass
                        await asyncio.sleep(0.1)

                await self._report_observed(
                    profile_id, runtime_instance_id, "running", config_version
                )
                # Startup does not clear persistent failure history.

                session = ActiveSession(
                    profile_id=profile_id,
                    runtime_instance_id=runtime_instance_id,
                    config_version=config_version,
                    udp_mux_port=port,
                    browser_container_id=b_container.id,
                    stream_container_id=s_container.id,
                    desired_state="running",
                    observed_state="running",
                )
                self._sessions[profile_id] = session
                return session

            except Exception as err:
                logger.error(
                    "Sandbox launch failed for %s: error_type=%s",
                    profile_id,
                    type(err).__name__,
                )
                try:
                    await self.docker.teardown_profile(profile_id)
                    await self.ports.release(profile_id)
                finally:
                    await self.events.emit_event(
                        event_id=f"startup_failure:{runtime_instance_id}",
                        profile_id=profile_id,
                        runtime_instance_id=runtime_instance_id,
                        event_type="exit",
                        exit_code=1,
                        exit_reason="startup_failure",
                        config_version=config_version,
                    )
                raise

    async def stop_profile(
        self,
        profile_id: str,
        *,
        expected_instance: str | None = None,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        """Orderly stop (AC-002):
        1. Mark stopping / unavailable.
        2. Disconnect Viewers via Gateway hook.
        3. Stop Stream container.
        4. Stop Browser container.
        5. Release UDP mux port.
        """
        lock = self._get_profile_lock(profile_id)
        async with self._global_lock, lock:
            session = self._sessions.get(profile_id)
            target = expected_instance or (
                session.runtime_instance_id if session else None
            )
            if target is None:
                return {
                    "profile_id": profile_id,
                    "status": "stopped",
                    "runtime_instance_id": None,
                }
            command_id = operation_id or f"reconcile_stop:{profile_id}:{target}"
            request = {"profile_id": profile_id, "runtime_instance_id": target}
            previous = self.operations.begin(command_id, request)
            if previous is not None:
                return previous
            result = {
                "profile_id": profile_id,
                "runtime_instance_id": target,
                "status": "stopped",
            }
            if session is not None and session.runtime_instance_id != target:
                self.operations.complete(command_id, request, result)
                return result
            if session is None:
                owned = [
                    item
                    for item in await asyncio.to_thread(
                        self.docker.scan_active_containers
                    )
                    if item["profile_id"] == profile_id
                ]
                matching = [item for item in owned if item["instance_id"] == target]
                if not matching:
                    self.operations.complete(command_id, request, result)
                    return result
                if len(matching) != len(owned):
                    raise DockerSandboxError(
                        "Mixed runtime instances require reconciliation"
                    )
                config_version = int(matching[0]["config_version"])
                session = ActiveSession(
                    profile_id,
                    target,
                    config_version,
                    0,
                    "",
                    "",
                    observed_state="stopping",
                )
                self._sessions[profile_id] = session
            curr_inst = session.runtime_instance_id if session else "unknown"
            cfg_ver = session.config_version if session else 1

            await self._report_observed(profile_id, curr_inst, "stopping", cfg_ver)
            if session is not None:
                session.observed_state = "stopping"

            await self.disconnect_viewers(profile_id)

            await self.docker.teardown_profile(profile_id)
            await self.ports.release(profile_id)
            self._sessions.pop(profile_id, None)

            await self._report_observed(profile_id, curr_inst, "stopped", cfg_ver)
            self.operations.complete(command_id, request, result)
            logger.info(
                f"Profile {profile_id} cleanly stopped and resources reclaimed."
            )
            return result

    async def disconnect_viewers(self, profile_id: str) -> None:
        session = self._sessions.get(profile_id)
        if session is None:
            return
        if self.gateway_control is None:
            raise RuntimeError("Gateway control RPC is not configured")
        try:
            await self.gateway_control.disconnect_viewers(
                profile_id, session.runtime_instance_id
            )
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            if (
                isinstance(exc, httpx.HTTPStatusError)
                and exc.response.status_code != 503
            ):
                raise
            # With no live Stream there is no surviving RTC media/input channel.
            # Authorization and instance-fence failures never use this path.
            try:
                stream = await asyncio.to_thread(
                    self.docker.client.containers.get,
                    self.docker.get_stream_container_name(profile_id),
                )
            except NotFound:
                return
            if stream.status != "running":
                return
            if self.gateway_container_id:
                gateway = await asyncio.to_thread(
                    self.docker.client.containers.get, self.gateway_container_id
                )
                if gateway.status != "running":
                    return
            raise

    async def reset_blocked(self, profile_id: str, operation_id: str) -> None:
        response = await self.api.patch(
            f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime/desired-state",
            headers=dict(self._auth_headers(), **{"Idempotency-Key": operation_id}),
            json={"desired_state": "running"},
        )
        response.raise_for_status()

    async def apply_profile_quota(self, profile_id: str, quota: dict[str, Any]) -> None:
        session = self._sessions.get(profile_id)
        if (
            session is None
            or session.runtime_instance_id != quota["runtime_instance_id"]
        ):
            return
        if self.gateway_control is None:
            raise RuntimeError("Gateway control RPC is not configured")
        await self.gateway_control.set_quota(
            profile_id,
            session.runtime_instance_id,
            quota["max_fps_cap"],
        )

    async def sample_resources(self) -> None:
        if self.gateway_control is None or self.resource_monitor is None:
            raise RuntimeError("Supervisor resource control is not configured")
        targets = []
        for session in list(self._sessions.values()):
            if session.observed_state != "running":
                continue
            try:
                visible = await self.gateway_control.has_foreground_viewers(
                    session.profile_id,
                    session.runtime_instance_id,
                )
            except (httpx.HTTPError, OSError, ValueError) as exc:
                logger.warning(
                    "Visibility unavailable: profile=%s error_type=%s",
                    session.profile_id,
                    type(exc).__name__,
                )
                visible = None
            if self._sessions.get(session.profile_id) is not session:
                continue
            targets.append(
                ProfileResourceTarget(
                    session.profile_id,
                    session.runtime_instance_id,
                    (session.browser_container_id, session.stream_container_id),
                    visible,
                )
            )
        await self.resource_monitor.sample(targets)

    async def _report_observed(
        self, profile_id: str, runtime_instance_id: str, state: str, config_version: int
    ) -> None:
        try:
            await self.api.post(
                f"/api/v1/internal/supervisor/runtimes/observed?profile_id={profile_id}",
                headers=self._auth_headers(),
                json={
                    "runtime_instance_id": runtime_instance_id,
                    "observed_state": state,
                    "config_version": config_version,
                },
            )
        except Exception as e:
            logger.warning(
                "Observed state report failed: state=%s error_type=%s",
                state,
                type(e).__name__,
            )
