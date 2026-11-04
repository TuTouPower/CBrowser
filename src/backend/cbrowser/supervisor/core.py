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
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from cbrowser.domain.models import ConfigVersionSnapshot, ProfileConfig
from cbrowser.gateway.endpoint import DEFAULT_GATEWAY_PORT, GatewayEndpoint
from cbrowser.runtime_agent.protocol import (
    ControlRequest,
    HealthResponse,
    RuntimeEventRecord,
    SearchDefaultsStatus,
)
from cbrowser.secret_files import read_secret_file
from cbrowser.supervisor.agent_credentials import AgentCredentials
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.event_forwarder import (
    DELIVERED,
    REJECTED,
    EventForwarder,
)
from cbrowser.supervisor.file_storage import atomic_write_text
from cbrowser.supervisor.gateway_client import GatewayControlClient
from cbrowser.supervisor.operation_journal import OperationJournal
from cbrowser.supervisor.path_validator import PathSecurityError
from cbrowser.supervisor.port_allocator import PortAllocator
from cbrowser.supervisor.protocol import (
    ProfileReadiness,
    ReadinessResponse,
    ReconcileAllResponse,
    TransportObservation,
)
from cbrowser.supervisor.recovery_rules import (
    is_error_exit_health,
    is_normal_exit_health,
)
from cbrowser.supervisor.resource_monitor import ProfileResourceTarget, ResourceMonitor
from cbrowser.supervisor.selkies_tokens import SelkiesTokens
from docker.errors import APIError, DockerException, NotFound
from pydantic import ValidationError

logger = logging.getLogger("cbrowser.supervisor.core")

UNPROTECTED_SANDBOX_GRACE_SEC = 60.0


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


class LifecycleConflictError(RuntimeError):
    """The requested lifecycle transition conflicts with current state.

    Mapped to HTTP 409 by the control server based on this type alone —
    never on exception message text — and carries no internal details.
    """


class RuntimeUnavailableError(RuntimeError):
    """The runtime agent for a profile cannot be reached right now.

    Mapped to HTTP 503 by the control server based on this type alone.
    """


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
        gateway_url: str | None = None,
        token_file: Path | str | None = None,
        agent_key_file: Path | str | None = None,
        gateway_control: GatewayControlClient | None = None,
        gateway_container_id: str | None = None,
        gateway_port: int | None = None,
    ):
        self.docker = docker_adapter
        self.ports = port_allocator
        self.events = event_forwarder
        self.api = api_client
        configured_port = (
            gateway_port if gateway_port is not None else DEFAULT_GATEWAY_PORT
        )
        endpoint = GatewayEndpoint.from_url(
            gateway_url or GatewayEndpoint(port=configured_port).ws_url
        )
        if gateway_port is not None and endpoint.port != gateway_port:
            raise ValueError(
                "Gateway URL port does not match the configured Gateway port"
            )
        self.gateway_endpoint = GatewayEndpoint(
            host=endpoint.host, port=endpoint.port, secure=endpoint.secure
        )
        self.gateway_url = gateway_url or self.gateway_endpoint.ws_url
        self.gateway_port = self.gateway_endpoint.port
        self._token_file = Path(token_file) if token_file else None
        self.agent_credentials = (
            AgentCredentials(agent_key_file) if agent_key_file else None
        )
        self.gateway_control = gateway_control
        self.resource_monitor: ResourceMonitor | None = None
        self.gateway_container_id = gateway_container_id

        self._sessions: dict[str, ActiveSession] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self._native_exit_instances: set[tuple[str, str, int]] = set()
        self._terminal_observations: set[tuple[str, str, int]] = set()
        # t026 convergence state (in-memory only; a restart re-derives it
        # from the same scans that rebuild sessions).
        self._transport: dict[str, TransportObservation] = {}
        self._registration_known: dict[str, bool] = {}
        self._stream_replace_attempts: dict[str, list[float]] = {}
        self._policy_fail_closed: set[tuple[str, str]] = set()
        self._unprotected_since: dict[str, float] = {}
        self._event_cursors: dict[str, dict[str, list]] = self._load_event_cursors()
        self._event_cursor_file = (
            self.docker.validator.data_root / "control" / "event_cursors.json"
        )
        self.operations = OperationJournal(
            self.docker.validator.validate_safe_path(
                self.docker.validator.data_root / "control" / "operations",
                allow_create=True,
            )
        )

    def _get_bearer_token(self) -> str | None:
        if self._token_file and self._token_file.is_file():
            return read_secret_file(
                self._token_file, label="Supervisor service token"
            )
        return None

    def _auth_headers(self) -> dict[str, str]:
        token = self._get_bearer_token()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def get_session(self, profile_id: str) -> ActiveSession | None:
        """Read-only session lookup for health checks and tests."""
        return self._sessions.get(profile_id)

    def terminal_observation_acknowledged(
        self, profile_id: str, runtime_instance_id: str, config_version: int
    ) -> bool:
        """Whether the API already acknowledged this terminal observation."""
        return (
            profile_id,
            runtime_instance_id,
            config_version,
        ) in self._terminal_observations

    async def query_agent_health(self, profile_id: str):
        """Public health probe used by tests and diagnostics."""
        return await self._query_agent_health(profile_id)

    def _get_profile_lock(self, profile_id: str) -> asyncio.Lock:
        if profile_id not in self._locks:
            self._locks[profile_id] = asyncio.Lock()
        return self._locks[profile_id]

    # ---------------- t026 convergence & observation ----------------

    _NON_FIXABLE_REJECTION_CODES = frozenset(
        {
            "unsupported_version",
            "unauthorized",
            "identity_mismatch",
            "invalid_payload",
            "instance_not_bound",
        }
    )
    _STREAM_REPLACE_WINDOW_SEC = 300.0
    _STREAM_REPLACE_MAX = 3

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    def _update_transport(self, profile_id: str, **fields: Any) -> None:
        current = self._transport.get(profile_id)
        if current is None:
            current = TransportObservation(profile_id=profile_id)
            self._transport[profile_id] = current
        for key, value in fields.items():
            setattr(current, key, value)

    def get_transport_observation(self, profile_id: str) -> TransportObservation:
        cached = self._transport.get(profile_id)
        if cached is not None:
            return cached
        return TransportObservation(profile_id=profile_id)

    def _resolve_gateway_id(self) -> str | None:
        resolver = getattr(self.docker, "resolve_gateway_container_id", None)
        resolved = resolver() if resolver is not None else None
        return resolved or self.gateway_container_id

    def _stream_replacement_allowed(self, profile_id: str, instance_id: str) -> bool:
        key = f"{profile_id}:{instance_id}"
        now = time.monotonic()
        attempts = [
            stamp
            for stamp in self._stream_replace_attempts.get(key, [])
            if now - stamp <= self._STREAM_REPLACE_WINDOW_SEC
        ]
        self._stream_replace_attempts[key] = attempts
        return len(attempts) < self._STREAM_REPLACE_MAX

    def _record_stream_replacement(self, profile_id: str, instance_id: str) -> None:
        key = f"{profile_id}:{instance_id}"
        self._stream_replace_attempts.setdefault(key, []).append(time.monotonic())

    async def _converge_session(
        self,
        profile_id: str,
        session: ActiveSession,
        scan_roles: dict[str, Any],
    ) -> None:
        """Steady-state convergence for a running pair (t026 AC-002..008).

        Runs inside the existing reconciliation pass while the profile is
        not operation-locked. Only the drifted layer is repaired: media
        attachment and Stream policy/registration problems are Stream-only
        fixes; a Browser policy drift fails closed and is reported, never
        torn down from here.
        """
        instance_id = session.runtime_instance_id
        self._update_transport(
            profile_id,
            runtime_instance_id=instance_id,
            browser_state=(
                "running" if scan_roles["browser"]["status"] == "running" else "error"
            ),
            stream_state=(
                "running" if scan_roles["stream"]["status"] == "running" else "error"
            ),
            config_version=session.config_version,
            protocol_version="v2",
        )
        objects = await asyncio.to_thread(
            self.docker.get_profile_containers, profile_id
        )
        browser_c = objects.get("browser")
        stream_c = objects.get("stream")
        if browser_c is None or stream_c is None:
            return
        try:
            media = await asyncio.to_thread(
                self.docker.inspect_media_network, profile_id
            )
        except DockerSandboxError:
            self._update_transport(
                profile_id,
                transport_state="failed",
                last_error="media_inspect_failed",
                last_error_at=self._now_iso(),
            )
            return
        plan = media.get("plan")
        if plan is not None:
            self._update_transport(
                profile_id, gateway_endpoint=plan.gateway_endpoint
            )
        if not media["exists"] or not media["conforms"]:
            if self._stream_replacement_allowed(profile_id, instance_id):
                await self._replace_stream_only(
                    profile_id, session, rebuild_network=True
                )
            else:
                self._update_transport(
                    profile_id,
                    transport_state="failed",
                    last_error="media_network_drift",
                    last_error_at=self._now_iso(),
                )
            return
        gateway_id = await asyncio.to_thread(self._resolve_gateway_id)
        if gateway_id is None:
            self._registration_known.pop(profile_id, None)
            self._update_transport(
                profile_id,
                transport_state="recovering",
                last_error="gateway_missing",
                last_error_at=self._now_iso(),
            )
            return
        if media["gateway_attached_id"] != gateway_id:
            try:
                attach = await asyncio.to_thread(
                    self.docker.attach_profile_infrastructure,
                    profile_id,
                    gateway_id,
                    self.gateway_port,
                )
            except DockerSandboxError:
                # Includes the fixed endpoint being held by another
                # container (AC-003): explicit degraded state, not a
                # scan-level warning only.
                self._update_transport(
                    profile_id,
                    transport_state="failed",
                    last_error="media_attach_failed",
                    last_error_at=self._now_iso(),
                )
                return
            self._update_transport(
                profile_id,
                transport_state="recovering",
                gateway_endpoint=attach["gateway_ip"],
                last_attached_at=self._now_iso(),
            )
        stream_spec = self.docker.stream_policy_spec(
            plan, self.gateway_port, session.udp_mux_port
        )
        try:
            stream_policy_ok = await asyncio.to_thread(
                self.docker.verify_container_policy, stream_c, stream_spec
            )
        except DockerSandboxError:
            self._update_transport(
                profile_id,
                transport_state="recovering",
                last_error="policy_verify_unavailable",
                last_error_at=self._now_iso(),
            )
            return
        if not stream_policy_ok:
            if self._stream_replacement_allowed(profile_id, instance_id):
                await self._replace_stream_only(
                    profile_id, session, rebuild_network=False
                )
            else:
                self._update_transport(
                    profile_id,
                    transport_state="failed",
                    last_error="stream_policy_drift",
                    last_error_at=self._now_iso(),
                )
            return
        browser_spec = await asyncio.to_thread(
            self.docker.browser_policy_spec, profile_id, browser_c
        )
        try:
            browser_policy_ok = await asyncio.to_thread(
                self.docker.verify_container_policy, browser_c, browser_spec
            )
        except DockerSandboxError:
            self._update_transport(
                profile_id,
                transport_state="recovering",
                last_error="policy_verify_unavailable",
                last_error_at=self._now_iso(),
            )
            return
        if not browser_policy_ok:
            key = (profile_id, instance_id)
            if key not in self._policy_fail_closed:
                try:
                    await asyncio.to_thread(
                        self.docker.fail_close_container, browser_c
                    )
                except DockerSandboxError:
                    # Not marked as handled: the Browser is still
                    # unmitigated, so the next cycle retries and the
                    # observation must not claim a completed fail-close.
                    logger.warning(
                        "Browser fail-close failed: profile=%s", profile_id
                    )
                    self._update_transport(
                        profile_id,
                        transport_state="recovering",
                        last_error="browser_policy_drift_unmitigated",
                        last_error_at=self._now_iso(),
                    )
                    return
                self._policy_fail_closed.add(key)
            self._update_transport(
                profile_id,
                transport_state="failed",
                last_error="browser_policy_drift",
                last_error_at=self._now_iso(),
            )
            return
        if self.gateway_control is None:
            self._update_transport(profile_id, transport_state="unknown")
            return
        registered = await self.gateway_control.agent_registered(
            profile_id, instance_id
        )
        if registered is None:
            self._registration_known.pop(profile_id, None)
            self._update_transport(
                profile_id,
                transport_state="recovering",
                last_error="gateway_unreachable",
                last_error_at=self._now_iso(),
            )
            return
        status = await self.gateway_control.registration_status(profile_id)
        if status is not None:
            self._update_transport(
                profile_id,
                agent_build_id=status.get("agent_build_id"),
                gateway_build_id=status.get("gateway_build_id"),
                selkies_version=status.get("selkies_version"),
            )
        if registered:
            self._registration_known[profile_id] = True
            self._update_transport(
                profile_id,
                transport_state="ready",
                last_registered_at=self._now_iso(),
                last_error=None,
                rejection_code=None,
            )
            return
        self._registration_known[profile_id] = False
        rejection = (status or {}).get("rejection") or {}
        rejection_code = rejection.get("code")
        if (status or {}).get("rejection_runtime_instance_id") != instance_id:
            rejection_code = None
        if rejection_code in self._NON_FIXABLE_REJECTION_CODES:
            self._update_transport(
                profile_id,
                transport_state="failed",
                last_error=f"registration_rejected:{rejection_code}",
                rejection_code=rejection_code,
                last_error_at=self._now_iso(),
            )
            return
        if self._stream_replacement_allowed(profile_id, instance_id):
            await self._replace_stream_only(
                profile_id, session, rebuild_network=False
            )
        else:
            self._update_transport(
                profile_id,
                transport_state="failed",
                last_error="stream_unregistered",
                rejection_code=rejection_code,
                last_error_at=self._now_iso(),
            )

    async def _replace_stream_only(
        self,
        profile_id: str,
        session: ActiveSession,
        *,
        rebuild_network: bool,
    ) -> bool:
        """Rebuild only the Stream layer of a running pair.

        The Browser container, IPC/X11 endpoints, Profile data, runtime
        instance and ports are untouched. When the media network itself
        drifted from the fixed-endpoint spec it is rebuilt first (which
        briefly detaches the Gateway); the Stream is then recreated
        against the same instance secret and Selkies credential files.
        """
        instance_id = session.runtime_instance_id
        # AC-008: a missing Gateway is never a reason to tear down the
        # Stream. Resolve it before touching anything; only a reachable
        # replacement target justifies the rebuild below.
        gateway_id = await asyncio.to_thread(self._resolve_gateway_id)
        if gateway_id is None:
            self._update_transport(
                profile_id,
                transport_state="recovering",
                last_error="gateway_missing",
                last_error_at=self._now_iso(),
            )
            return False
        self._record_stream_replacement(profile_id, instance_id)
        self._update_transport(
            profile_id,
            transport_state="recovering",
            stream_state="stopped",
            last_error="stream_replacement",
            last_error_at=self._now_iso(),
        )
        validator = self.docker.validator
        try:
            stream_name = self.docker.get_stream_container_name(profile_id)
            await asyncio.to_thread(
                self.docker.cleanup_container_by_name, stream_name
            )
            if rebuild_network:
                # The Browser stays attached throughout: the adapter
                # disconnects/reconnects endpoints around the rebuild
                # (cleanup_network_by_name rightly refuses this with
                # runtime containers attached).
                await asyncio.to_thread(
                    self.docker.rebuild_media_network, profile_id
                )
            attach = await asyncio.to_thread(
                self.docker.attach_profile_infrastructure,
                profile_id,
                gateway_id,
                self.gateway_port,
            )
            dirs = {
                "runtime": validator.get_runtime_dir(profile_id),
                "secret": validator.get_secret_dir(profile_id),
            }
            secret_file = dirs["secret"] / "agent_secret.txt"
            if not secret_file.exists():
                token = self.agent_credentials.token_for(profile_id, instance_id)
                atomic_write_text(secret_file, token, mode=0o600)
            selkies_tokens = SelkiesTokens.generate()
            selkies_file = selkies_tokens.provision_credentials_file(
                validator.get_secret_dir(profile_id), instance_id
            )
            objects = await asyncio.to_thread(
                self.docker.get_profile_containers, profile_id
            )
            browser_container = objects.get("browser")
            if browser_container is None:
                self._update_transport(
                    profile_id,
                    transport_state="failed",
                    last_error="browser_missing",
                    last_error_at=self._now_iso(),
                )
                return False
            stream_container = await self.docker.start_stream_container(
                profile_id=profile_id,
                runtime_instance_id=instance_id,
                browser_container_name=browser_container.name,
                udp_mux_port=session.udp_mux_port,
                gateway_url=attach["gateway_url"],
                agent_secret_path=secret_file,
                selkies_tokens_path=selkies_file,
                snapshot_json_path=dirs["runtime"] / "snapshot.json",
                gateway_port=self.gateway_port,
            )
            session.stream_container_id = stream_container.id
            self._update_transport(
                profile_id,
                stream_state="running",
                gateway_endpoint=attach["gateway_ip"],
                last_attached_at=self._now_iso(),
            )
            return True
        except (DockerSandboxError, OSError, ValueError) as exc:
            logger.warning(
                "Stream-only replacement failed: profile=%s error_type=%s",
                profile_id,
                type(exc).__name__,
            )
            self._update_transport(
                profile_id,
                transport_state="failed",
                last_error=f"stream_replacement_failed:{type(exc).__name__}",
                last_error_at=self._now_iso(),
            )
            return False

    async def _recover_attachment_offline(
        self, profile_id: str, scan_instance_id: str | None = None
    ) -> None:
        """API-offline recovery (t026 AC-006): re-attach media only.

        Lifecycle and session state are never touched here; the profile
        is re-attached by label/instance consistency so viewers recover
        once the Gateway path is whole again. Instance consistency
        comes from the tracked session when one exists, otherwise from
        the scan's label-verified pair the caller already
        integrity-checked — a Supervisor restart must not strand
        existing sandboxes.
        """
        session = self._sessions.get(profile_id)
        instance_id = (
            session.runtime_instance_id
            if session is not None
            else scan_instance_id
        )
        if instance_id is None:
            return
        media = await asyncio.to_thread(
            self.docker.inspect_media_network, profile_id
        )
        if not media["exists"] or not media["conforms"]:
            return
        gateway_id = await asyncio.to_thread(self._resolve_gateway_id)
        if gateway_id is None or media["gateway_attached_id"] == gateway_id:
            return
        try:
            attach = await asyncio.to_thread(
                self.docker.attach_profile_infrastructure,
                profile_id,
                gateway_id,
                self.gateway_port,
            )
        except DockerSandboxError:
            return
        self._update_transport(
            profile_id,
            runtime_instance_id=instance_id,
            transport_state="recovering",
            gateway_endpoint=attach["gateway_ip"],
            last_attached_at=self._now_iso(),
        )

    async def reconcile_all(self) -> ReconcileAllResponse:
        """One full convergence pass over every live pair (t026 AC-009)."""
        scanned = await self.scan_and_reconcile_existing()
        return ReconcileAllResponse(
            scanned=len(scanned),
            profiles=sorted({item["profile_id"] for item in scanned}),
        )

    async def readiness(self) -> ReadinessResponse:
        """Deployment readiness over every desired=running Profile.

        Any unknown (API unreachable, no session, unverifiable policy or
        registration) makes the result not ready; the response carries
        per-Profile redacted diagnostics instead of a bare boolean.
        """
        try:
            list_resp = await self.api.get(
                "/api/v1/internal/supervisor/profiles",
                headers=self._auth_headers(),
            )
            list_resp.raise_for_status()
            profiles = list_resp.json()
        except Exception as exc:  # noqa: BLE001 - readiness must degrade to unknown, never crash
            return ReadinessResponse(
                ready=False,
                reason=f"api_unavailable:{type(exc).__name__}",
            )
        results: list[ProfileReadiness] = []
        for entry in profiles:
            profile_id = entry.get("id") or entry.get("profile_id")
            if not profile_id:
                continue
            try:
                rt_resp = await self.api.get(
                    f"/api/v1/internal/supervisor/profiles/{quote(profile_id, safe='')}/runtime",
                    headers=self._auth_headers(),
                )
                rt_resp.raise_for_status()
                runtime = rt_resp.json()
            except Exception as exc:  # noqa: BLE001 - per-profile unknown
                results.append(
                    ProfileReadiness(
                        profile_id=profile_id,
                        ready=False,
                        checks={"runtime": None},
                        diagnostics=[f"runtime_unavailable:{type(exc).__name__}"],
                    )
                )
                continue
            if runtime.get("desired_state") != "running":
                continue
            try:
                results.append(
                    await self._profile_readiness(profile_id, runtime)
                )
            except Exception as exc:  # noqa: BLE001 - one Profile's Docker failure must not 500 the whole readiness view (AC-009)
                results.append(
                    ProfileReadiness(
                        profile_id=profile_id,
                        ready=False,
                        checks={"instance": None},
                        diagnostics=[
                            f"readiness_check_failed:{type(exc).__name__}"
                        ],
                    )
                )
        return ReadinessResponse(
            ready=all(item.ready for item in results),
            profiles=results,
        )

    async def _profile_readiness(
        self, profile_id: str, runtime: dict[str, Any]
    ) -> ProfileReadiness:
        instance_id = runtime.get("runtime_instance_id")
        checks: dict[str, bool | None] = {}
        diagnostics: list[str] = []
        session = self._sessions.get(profile_id)
        checks["instance"] = bool(
            session is not None and session.runtime_instance_id == instance_id
        )
        if not checks["instance"]:
            diagnostics.append("session_instance_mismatch")
        roles: dict[str, Any] | None = None
        if session is not None:
            roles = await asyncio.to_thread(
                self.docker.get_profile_containers, profile_id
            )
        checks["browser"] = bool(
            roles
            and roles.get("browser") is not None
            and roles["browser"].status == "running"
        )
        checks["stream"] = bool(
            roles
            and roles.get("stream") is not None
            and roles["stream"].status == "running"
        )
        media = await asyncio.to_thread(
            self.docker.inspect_media_network, profile_id
        )
        gateway_id = await asyncio.to_thread(self._resolve_gateway_id)
        checks["attach"] = bool(
            media["conforms"]
            and gateway_id is not None
            and media["gateway_attached_id"] == gateway_id
        )
        if not checks["attach"]:
            diagnostics.append("gateway_not_attached_at_fixed_endpoint")
        plan = media.get("plan")
        if (
            roles
            and roles.get("browser") is not None
            and roles.get("stream") is not None
            and plan is not None
            and session is not None
        ):
            try:
                stream_spec = self.docker.stream_policy_spec(
                    plan, self.gateway_port, session.udp_mux_port
                )
                stream_ok = await asyncio.to_thread(
                    self.docker.verify_container_policy,
                    roles["stream"],
                    stream_spec,
                )
                browser_spec = await asyncio.to_thread(
                    self.docker.browser_policy_spec, profile_id, roles["browser"]
                )
                browser_ok = await asyncio.to_thread(
                    self.docker.verify_container_policy,
                    roles["browser"],
                    browser_spec,
                )
                checks["policy"] = bool(stream_ok and browser_ok)
            except DockerSandboxError:
                checks["policy"] = None
                diagnostics.append("policy_verify_unavailable")
        else:
            checks["policy"] = None
            diagnostics.append("policy_unverifiable")
        if self.gateway_control is not None and instance_id:
            registered = await self.gateway_control.agent_registered(
                profile_id, instance_id
            )
            checks["registration"] = registered
            if registered is None:
                diagnostics.append("registration_unverifiable")
            elif registered is not True:
                diagnostics.append("agent_not_registered")
        else:
            checks["registration"] = None
            diagnostics.append("registration_unverifiable")
        ready = all(value is True for value in checks.values())
        return ProfileReadiness(
            profile_id=profile_id,
            runtime_instance_id=instance_id,
            ready=ready,
            checks=checks,
            diagnostics=diagnostics,
        )

    async def scan_and_reconcile_existing(self) -> list[dict[str, Any]]:
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
            try:
                await self._reconcile_profile(pid, roles)
            except DockerException as exc:
                if not isinstance(exc, APIError):
                    raise
                logger.warning(
                    "Profile reconciliation failed: profile=%s error_type=%s",
                    pid,
                    type(exc).__name__,
                )
            except Exception as exc:  # noqa: BLE001 - one Profile failure must not block the others
                logger.warning(
                    "Profile reconciliation failed: profile=%s error_type=%s",
                    pid,
                    type(exc).__name__,
                )
        for item in containers:
            if item.get("role") == "stream":
                known = self._registration_known.get(item.get("profile_id"))
                if known is not None:
                    item["registered"] = known
        return containers

    async def _reconcile_profile(
        self, pid: str, roles: dict[str, Any]
    ) -> None:
        """Reconcile one Profile; callers isolate failures per Profile."""
        if self._get_profile_lock(pid).locked():
            return
        b_c = roles.get("browser")
        s_c = roles.get("stream")

        # Integrity check: the Browser anchors the pair. A missing
        # Stream is a convergence target (AC-008), not a reason to
        # retain silently — it is handled once the API confirms the
        # desired state and the tracked session below.
        if not b_c:
            logger.warning(
                "Incomplete sandbox retained: profile=%s browser=%s stream=%s",
                pid,
                bool(b_c),
                bool(s_c),
            )
            return

        # Integrity check: instance_id on both containers must match
        b_inst = b_c.get("instance_id")
        s_inst = s_c.get("instance_id") if s_c else b_inst
        if not b_inst or b_inst != s_inst:
            logger.warning(
                "Sandbox instance mismatch: profile=%s browser=%s stream=%s",
                pid,
                b_inst,
                s_inst,
            )
            return

        # Query API desired state with network/HTTP failure protection
        try:
            resp = await self.api.get(
                f"/api/v1/internal/supervisor/profiles/{quote(pid, safe='')}/runtime",
                headers=self._auth_headers(),
            )
        except Exception as e:  # noqa: BLE001 - API query transport failure safely retains profile without teardown
            logger.warning(
                "API unavailable; retaining profile=%s error_type=%s",
                pid,
                type(e).__name__,
            )
            # t026 AC-006: while the API is unreachable, only the media
            # attachment may be recovered; lifecycle is never touched.
            # The pair's labels/instance consistency was verified above,
            # so recovery does not depend on an in-memory session.
            await self._recover_attachment_offline(pid, b_inst)
            return

        if resp.status_code == 200:
            rt = resp.json()
            if self._get_profile_lock(pid).locked():
                return
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
                return

            session = self._sessions.get(pid)
            bound_version = int(
                rt.get("config_version", b_c.get("config_version", 1))
            )
            if (
                desired == "running"
                and s_c is None
                and session is not None
                and session.runtime_instance_id == b_inst
            ):
                # AC-008: the Stream container is gone while the pair
                # is tracked and desired running — rebuild only the
                # Stream; the Browser keeps running untouched. The
                # replacement budget bounds this path like every other
                # Stream-only replacement (no unbounded self-retry).
                if not self._stream_replacement_allowed(pid, b_inst):
                    self._update_transport(
                        pid,
                        transport_state="failed",
                        stream_state="missing",
                        last_error="stream_missing_budget_exhausted",
                        last_error_at=self._now_iso(),
                    )
                    return
                rebuild_network = False
                try:
                    media = await asyncio.to_thread(
                        self.docker.inspect_media_network, pid
                    )
                    rebuild_network = not (
                        media.get("exists") and media.get("conforms")
                    )
                except DockerSandboxError:
                    rebuild_network = False
                await self._replace_stream_only(
                    pid, session, rebuild_network=rebuild_network
                )
                return
            if s_c is None:
                # Without a tracked session the Stream's port binding
                # cannot be recovered safely; retain as before.
                logger.warning(
                    "Stream missing without tracked session; retained: "
                    "profile=%s",
                    pid,
                )
                return
            if desired == "running":
                obs = await self._reconcile_instance_observation(
                    pid, b_inst, bound_version, container_status=b_c.get("status")
                )
                if obs in ("stopped", "error"):
                    return
                if (
                    obs == "running"
                    and session is not None
                    and session.runtime_instance_id == b_inst
                    and session.observed_state == "error"
                ):
                    # Release a locally latched container_exit error:
                    # the authoritative observation (Browser running +
                    # Agent health for this very instance) supersedes
                    # it. Without the release, the same-instance branch
                    # below can neither report running nor converge
                    # again for this instance (t026_code_f014). The
                    # terminal-observation dedupe key goes with it: the
                    # generation demonstrably did not terminate, so a
                    # later terminal fact for this same instance must be
                    # reportable again (t026_code_f015).
                    session.observed_state = "running"
                    self._terminal_observations.discard(
                        (pid, b_inst, bound_version)
                    )

            if (
                desired == "running"
                and session is not None
                and session.runtime_instance_id == b_inst
            ):
                # Same generation is already tracked. Docker "running" must
                # never overwrite an error observation from the Agent.
                if any(item["status"] != "running" for item in (b_c, s_c)):
                    if (
                        b_c["status"] == "running"
                        and s_c["status"] != "running"
                        and self._stream_replacement_allowed(pid, b_inst)
                    ):
                        # AC-008: a stopped/exited Stream is repaired in
                        # place within the replacement budget; the
                        # running Browser and the pair are left alone
                        # instead of escalating to a whole-pair error.
                        await self._replace_stream_only(
                            pid, session, rebuild_network=False
                        )
                        return
                    if session.observed_state != "error":
                        session.observed_state = "error"
                        await self.report_terminal_observation(
                            pid,
                            b_inst,
                            int(rt.get("config_version", session.config_version)),
                            observed_state="error",
                            reason="container_exit",
                        )
                elif (
                    session.observed_state == "running"
                    and rt.get("observed_state") != "running"
                ):
                    await self._report_observed(
                        pid,
                        b_inst,
                        "running",
                        int(rt.get("config_version", session.config_version)),
                    )
                if (
                    session.observed_state == "running"
                    and all(item["status"] == "running" for item in (b_c, s_c))
                ):
                    await self._converge_session(pid, session, roles)
                return

            if desired == "running" and any(
                item["status"] != "running" for item in (b_c, s_c)
            ):
                await self.report_terminal_observation(
                    pid,
                    b_inst,
                    int(rt.get("config_version", b_c.get("config_version", 1))),
                    observed_state="error",
                    reason="container_exit",
                )
                return

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
                    first_seen = self._unprotected_since.setdefault(
                        pid, time.monotonic()
                    )
                    age = time.monotonic() - first_seen
                    if age < UNPROTECTED_SANDBOX_GRACE_SEC:
                        logger.warning(
                            "Unprotected sandbox awaiting policy: profile=%s "
                            "age=%.1fs",
                            pid,
                            age,
                        )
                        return
                    logger.error(
                        "Unprotected sandbox exceeded grace; tearing down: "
                        "profile=%s age=%.1fs",
                        pid,
                        age,
                    )
                    self._unprotected_since.pop(pid, None)
                    await self.disconnect_viewers(pid)
                    teardown_failed = False
                    try:
                        await self.docker.teardown_profile(pid)
                    except Exception as exc:  # noqa: BLE001 - unprotected sandbox teardown error isolated and logged
                        teardown_failed = True
                        logger.error(
                            "Unprotected sandbox teardown failed: profile=%s "
                            "error_type=%s",
                            pid,
                            type(exc).__name__,
                        )
                    finally:
                        await self.ports.release(pid)
                        self._sessions.pop(pid, None)
                        self.forget_instance_events(pid, b_inst)
                    if not teardown_failed:
                        await self._report_observed(
                            pid,
                            b_inst,
                            "error",
                            int(rt.get("config_version", 1)),
                            reason="unprotected_sandbox",
                        )
                    return
                if self.gateway_control is None:
                    raise RuntimeError(
                        "Gateway control RPC is required for readiness"
                    )
                try:
                    await self.gateway_control.has_foreground_viewers(pid, b_inst)
                except (httpx.HTTPError, OSError, ValueError):
                    return
                # Restore UDP port from Stream container HostConfig port bindings
                actual_port = None
                try:
                    s_inspect = await asyncio.to_thread(
                        self.docker.client.api.inspect_container, s_c["id"]
                    )
                    port_bindings = s_inspect.get("HostConfig", {}).get(
                        "PortBindings", {}
                    )
                    for k, v in port_bindings.items():
                        if k.endswith("/udp") and v:
                            actual_port = int(v[0]["HostPort"])
                            break
                except Exception as e:  # noqa: BLE001 - stream port inspection failure logged before raising sandbox error
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
                    return
                self._unprotected_since.pop(pid, None)
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
                if rt.get("observed_state") == "starting":
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

    def _quarantine_event_file(
        self, event_file: Path, profile_id: str, instance_id: str, reason: str
    ) -> bool:
        """Move an invalid journal file aside; True only when it landed.

        Callers advance the delivery cursor only on True: when the
        dead-letter move itself fails, the event stays pending (and keeps
        alarming on later scans) instead of being silently skipped past
        (review t022_code_f013).
        """
        try:
            target_dir = self.docker.validator.validate_safe_path(
                self.docker.validator.data_root
                / "quarantine"
                / "runtime-events"
                / profile_id
                / instance_id,
                allow_create=True,
            )
            target_dir.mkdir(parents=True, exist_ok=True)
            os.replace(event_file, target_dir / event_file.name)
            logger.warning(
                "Quarantined runtime event: profile=%s instance=%s reason=%s",
                profile_id,
                instance_id,
                reason,
            )
            return True
        except (OSError, PathSecurityError) as exc:
            logger.warning(
                "Runtime event quarantine failed: reason=%s error_type=%s",
                reason,
                type(exc).__name__,
            )
            return False

    @staticmethod
    def _parse_disk_event(data: Any, profile_id: str, instance_id: str) -> str | None:
        """Return a quarantine reason when the journal entry is not trustworthy."""
        if not isinstance(data, dict):
            return "not_object"
        try:
            record = RuntimeEventRecord.model_validate(data)
        except ValidationError:
            return "schema"
        if record.profile_id != profile_id:
            return "profile_mismatch"
        if record.runtime_instance_id != instance_id:
            return "instance_mismatch"
        if record.event_type == "exit" and record.exit_code is None:
            return "missing_exit_code"
        return None

    def _load_event_cursors(self) -> dict[str, dict[str, list]]:
        path = self.docker.validator.data_root / "control" / "event_cursors.json"
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {}
            cursors: dict[str, dict[str, list]] = {}
            for profile_id, instances in raw.items():
                if not isinstance(instances, dict):
                    continue
                for instance_id, marker in instances.items():
                    if (
                        isinstance(marker, list)
                        and len(marker) == 2
                        and type(marker[0]) is int
                        and isinstance(marker[1], str)
                    ):
                        cursors.setdefault(str(profile_id), {})[
                            str(instance_id)
                        ] = marker
            return cursors
        except (OSError, ValueError, UnicodeError):
            logger.warning("Event cursor file unreadable; rebuilding from archives")
            return {}

    def _save_event_cursors(self) -> None:
        try:
            atomic_write_text(
                self._event_cursor_file,
                json.dumps(self._event_cursors),
                mode=0o600,
            )
        except OSError as exc:
            logger.warning(
                "Event cursor persistence failed: error_type=%s", type(exc).__name__
            )

    def _advance_event_cursor(
        self, profile_id: str, instance_id: str, marker: tuple[int, str]
    ) -> None:
        self._event_cursors.setdefault(profile_id, {})[instance_id] = list(marker)

    def _archive_event_file(
        self, event_file: Path, profile_id: str, instance_id: str
    ) -> None:
        """Move handled journals into a bounded per-instance archive."""
        try:
            archive = self.docker.validator.validate_safe_path(
                self.docker.validator.data_root
                / "runtime-events"
                / profile_id
                / "archive"
                / instance_id,
                allow_create=True,
            )
            archive.mkdir(parents=True, exist_ok=True)
            os.replace(event_file, archive / event_file.name)
            archived = sorted(
                archive.glob("*.json"), key=lambda p: p.stat().st_mtime_ns
            )
            for stale in archived[:-200]:
                stale.unlink(missing_ok=True)
        except (OSError, PathSecurityError) as exc:
            logger.warning(
                "Event archive failed: error_type=%s", type(exc).__name__
            )

    def forget_instance_events(
        self, profile_id: str, runtime_instance_id: str
    ) -> None:
        """Drop per-instance memory when a runtime generation ends."""
        self._native_exit_instances = {
            item for item in self._native_exit_instances if item[0] != profile_id
        }
        self._terminal_observations = {
            item
            for item in self._terminal_observations
            if not (item[0] == profile_id and item[1] == runtime_instance_id)
        }
        instances = self._event_cursors.get(profile_id)
        if instances is not None:
            instances.pop(runtime_instance_id, None)
            if not instances:
                self._event_cursors.pop(profile_id, None)

    async def consume_disk_events(self) -> int:
        """Forward validated journals newer than the per-instance cursor."""
        total_forwarded = 0
        changed = False
        events_root = self.docker.validator.data_root / "runtime-events"
        if not events_root.is_dir():
            return 0
        for p_dir in events_root.iterdir():
            if not p_dir.is_dir():
                continue
            profile_id = p_dir.name
            runtime_events = p_dir / "events" / "runtime"

            def _marker(path: Path) -> tuple[int, str]:
                try:
                    return (path.stat().st_mtime_ns, path.name)
                except OSError:
                    return (0, path.name)

            for evt_file in sorted(runtime_events.glob("*/*.json"), key=_marker):
                instance_id = evt_file.parent.name
                try:
                    stat = evt_file.stat()
                except OSError:
                    continue
                marker = (stat.st_mtime_ns, evt_file.name)
                cursor = self._event_cursors.get(profile_id, {}).get(instance_id)
                if cursor is not None and marker <= (cursor[0], cursor[1]):
                    continue
                try:
                    self.docker.validator.validate_safe_path(evt_file)
                    data = json.loads(evt_file.read_text(encoding="utf-8"))
                except (OSError, ValueError, PathSecurityError, UnicodeError) as exc:
                    logger.warning(
                        "Disk event processing failed: error_type=%s",
                        type(exc).__name__,
                    )
                    if self._quarantine_event_file(
                        evt_file, profile_id, instance_id, "unreadable"
                    ):
                        self._advance_event_cursor(profile_id, instance_id, marker)
                        changed = True
                    continue

                invalid_reason = self._parse_disk_event(
                    data, profile_id, instance_id
                )
                if invalid_reason is not None:
                    if self._quarantine_event_file(
                        evt_file, profile_id, instance_id, invalid_reason
                    ):
                        self._advance_event_cursor(profile_id, instance_id, marker)
                        changed = True
                    continue

                etype = data["event_type"]
                ecode = data.get("exit_code")
                config_version = int(data.get("config_version", 1))

                evt_id = data.get("event_id", evt_file.stem)
                outcome = await self.events.emit_event_with_outcome(
                    event_id=evt_id,
                    profile_id=profile_id,
                    runtime_instance_id=instance_id,
                    event_type=etype,
                    exit_code=ecode,
                    exit_reason=data.get("exit_reason"),
                    config_version=config_version,
                    payload=data.get("payload", {}),
                    # Core owns the single dead letter (the journal
                    # original); the forwarder must not quarantine a
                    # second copy of the same event.
                    dead_letter_spool=False,
                )
                if outcome == REJECTED:
                    # Permanent semantic refusal: dead-letter the original
                    # file exactly once and persist the cursor past it, so it
                    # is never re-delivered. Diagnostic delivery must not
                    # advance business runtime state, so no observation
                    # reconciliation happens on this path. If the
                    # dead-letter move itself fails the cursor stays put
                    # and the event remains pending.
                    if self._quarantine_event_file(
                        evt_file, profile_id, instance_id, "rejected"
                    ):
                        self._advance_event_cursor(profile_id, instance_id, marker)
                        changed = True
                    continue
                if outcome != DELIVERED:
                    # Temporarily unavailable: stays pending for a later scan.
                    continue
                if etype == "exit":
                    self._native_exit_instances.add(
                        (profile_id, instance_id, config_version)
                    )
                total_forwarded += 1
                await self._reconcile_instance_observation(
                    profile_id, instance_id, config_version
                )
                self._archive_event_file(evt_file, profile_id, instance_id)
                self._advance_event_cursor(profile_id, instance_id, marker)
                changed = True
        if changed:
            self._save_event_cursors()
        return total_forwarded

    async def _reconcile_instance_observation(
        self,
        profile_id: str,
        instance_id: str,
        config_version: int,
        *,
        container_status: str | None = None,
    ) -> str | None:
        """Query actual Docker / Agent state and report authoritative observation.

        Returns 'stopped', 'error', 'running', or None if unresolved / unacknowledged.
        """
        if container_status is None:
            try:
                container = await asyncio.to_thread(
                    self.docker.client.containers.get,
                    self.docker.get_browser_container_name(profile_id),
                )
                labels = getattr(container, "labels", None) or {}
                if labels.get("com.cbrowser.instance-id") != instance_id:
                    logger.warning(
                        "Container instance mismatch: profile=%s docker=%s expected=%s",
                        profile_id,
                        labels.get("com.cbrowser.instance-id"),
                        instance_id,
                    )
                    return None
                container_status = getattr(container, "status", None)
            except NotFound:
                container_status = "not_found"
            except Exception:  # noqa: BLE001 - unexpected docker inspection error safely defaults status to None
                container_status = None

        if container_status in ("exited", "dead", "not_found"):
            delivered = await self.report_terminal_observation(
                profile_id,
                instance_id,
                config_version,
                observed_state="error",
                reason="container_exit",
            )
            return "error" if delivered else None

        if container_status == "running":
            health = await self._query_agent_health(profile_id)
            if health is None:
                return None
            if not (
                health.profile_id == profile_id
                and health.runtime_instance_id == instance_id
                and health.config_version == config_version
            ):
                logger.warning(
                    "Agent identity mismatch: profile=%s (expected %s) "
                    "instance=%s (expected %s) version=%s (expected %s)",
                    health.profile_id,
                    profile_id,
                    health.runtime_instance_id,
                    instance_id,
                    health.config_version,
                    config_version,
                )
                return None

            if is_normal_exit_health(health.details):
                logger.info(
                    "Normal Chrome exit verified via Agent UDS: profile=%s",
                    profile_id,
                )
                delivered = await self.report_terminal_observation(
                    profile_id,
                    instance_id,
                    config_version,
                    observed_state="stopped",
                    reason="normal_exit",
                )
                return "stopped" if delivered else None
            elif is_error_exit_health(health.details):
                reason = (
                    "process_lost"
                    if health.details.get("exit_reason")
                    == "process_observation_lost"
                    else "agent_exit"
                )
                delivered = await self.report_terminal_observation(
                    profile_id,
                    instance_id,
                    config_version,
                    observed_state="error",
                    reason=reason,
                )
                return "error" if delivered else None
            return "running"

        return None

    @asynccontextmanager
    async def _agent_uds_client(
        self, profile_id: str
    ) -> AsyncIterator[httpx.AsyncClient | None]:
        """Yield an HTTP client bound to the runtime agent's UDS socket.

        Yields None when the socket does not exist. The runtime path is
        validated exactly like the health probe; callers own error mapping.
        """
        runtime_dir = self.docker.validator.get_runtime_dir(profile_id)
        sock_path = self.docker.validator.validate_runtime_source(
            profile_id, runtime_dir / "agent.sock"
        )
        if not sock_path.is_socket():
            yield None
            return
        dir_fd: int | None = None
        try:
            proc_fd_dir = Path("/proc/self/fd")
            if proc_fd_dir.exists():
                dir_fd = os.open(
                    str(sock_path.parent),
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                )
                uds_target = f"/proc/self/fd/{dir_fd}/{sock_path.name}"
            else:
                uds_target = os.path.relpath(sock_path, os.getcwd())
            transport = httpx.AsyncHTTPTransport(uds=uds_target)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://uds", timeout=2.0
            ) as client:
                yield client
        finally:
            if dir_fd is not None:
                os.close(dir_fd)

    async def _query_agent_health(self, profile_id: str) -> HealthResponse | None:
        """Query Agent UDS /health; validate runtime path and reject if inaccessible."""
        try:
            async with self._agent_uds_client(profile_id) as client:
                if client is None:
                    return None
                resp = await client.get("/health")
                if resp.status_code == 200:
                    return HealthResponse.model_validate(resp.json())
                return None
        except Exception as exc:  # noqa: BLE001 - agent UDS health query failure safely returns None
            logger.debug(
                "Agent health query failed: profile=%s error_type=%s",
                profile_id,
                type(exc).__name__,
            )
            return None

    async def get_search_defaults(
        self, profile_id: str
    ) -> tuple[str | None, SearchDefaultsStatus | None]:
        """Current search-defaults status for the live instance, if any.

        Returns (live runtime_instance_id, status). The status is only
        surfaced when the agent's health identity matches the session's
        instance; anything else yields (instance, None).
        """
        session = self.get_session(profile_id)
        if session is None:
            return None, None
        health = await self._query_agent_health(profile_id)
        if health is None or health.runtime_instance_id != session.runtime_instance_id:
            return session.runtime_instance_id, None
        status = health.search_defaults
        # The status payload carries its own instance: only surface it when
        # it belongs to the same live instance as the health report itself.
        if status is not None and status.runtime_instance_id != session.runtime_instance_id:
            status = None
        return session.runtime_instance_id, status

    async def retry_search_defaults(
        self, profile_id: str, runtime_instance_id: str, request_id: str
    ) -> None:
        """Forward a fenced, idempotent search-defaults retry to the agent.

        The supervisor fences against its own live session first; the
        agent re-fences against its runner metadata and deduplicates by
        request_id, so retries never restart or disturb the browser.
        """
        session = self.get_session(profile_id)
        if session is None:
            raise RuntimeUnavailableError("No live runtime session")
        if session.runtime_instance_id != runtime_instance_id:
            raise LifecycleConflictError("Search defaults retry instance fence")
        request = ControlRequest(
            action="retry_search_defaults",
            params={
                "profile_id": profile_id,
                "runtime_instance_id": runtime_instance_id,
                "request_id": request_id,
            },
        )
        try:
            async with self._agent_uds_client(profile_id) as client:
                if client is None:
                    raise RuntimeUnavailableError("Runtime agent socket unavailable")
                resp = await client.post("/control", json=request.model_dump())
        except RuntimeUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - transport failure maps to 503 without internals
            raise RuntimeUnavailableError(
                f"Runtime agent control failed: {type(exc).__name__}"
            ) from None
        if resp.status_code == 403:
            raise LifecycleConflictError("Search defaults retry rejected by agent")
        if resp.status_code != 200:
            raise RuntimeUnavailableError("Runtime agent control unavailable")

    async def release_dialog_attendant(self, profile_id: str) -> bool:
        """Best-effort release of the Agent's resident dialog attendant.

        Called by the Supervisor close-tunnels cascade during a
        takeover (t031). Returns True only when the Agent acknowledges
        or when no Agent process exists (vacuous: a dead Agent holds no
        attendant state, so there is nothing to release -- without this
        case every close for a never-started profile would stay pending
        forever). False degrades to the attendant's own release-on-stop
        path and never blocks the tunnel close.
        """
        try:
            async with self._agent_uds_client(profile_id) as client:
                if client is None:
                    return True
                request = ControlRequest(
                    action="release_attendant",
                    params={"profile_id": profile_id},
                )
                resp = await client.post(
                    "/control", json=request.model_dump()
                )
        except Exception:  # noqa: BLE001 - release failure degrades, never blocks
            return False
        return resp.status_code == 200

    async def list_attendant_dialogs(
        self, profile_id: str
    ) -> list[dict] | None:
        """Peek held dialogs from the Agent's resident attendant.

        Returns None when the Agent is unreachable (the caller treats
        it as "no held dialog known"); an empty list means the
        attendant is reachable and holds nothing.
        """
        try:
            async with self._agent_uds_client(profile_id) as client:
                if client is None:
                    return None
                request = ControlRequest(
                    action="list_attendant_dialogs",
                    params={"profile_id": profile_id},
                )
                resp = await client.post(
                    "/control", json=request.model_dump()
                )
        except Exception:  # noqa: BLE001 - unreachable Agent degrades to unknown
            return None
        if resp.status_code != 200:
            return None
        try:
            body = resp.json()
        except ValueError:
            return None
        data = body.get("data") or {}
        dialogs = data.get("dialogs")
        return dialogs if isinstance(dialogs, list) else None

    async def answer_attendant_dialog(
        self,
        profile_id: str,
        target_id: str,
        accept: bool,
        prompt_text: str | None = None,
    ) -> dict | None:
        """Answer a held dialog through the attendant's session.

        Returns the answered dialog record, or None when no dialog is
        held for the target or the Agent is unreachable.
        """
        try:
            async with self._agent_uds_client(profile_id) as client:
                if client is None:
                    return None
                params: dict[str, Any] = {
                    "profile_id": profile_id,
                    "target_id": target_id,
                    "accept": accept,
                }
                if prompt_text is not None:
                    params["prompt_text"] = prompt_text
                request = ControlRequest(
                    action="answer_attendant_dialog",
                    params=params,
                )
                resp = await client.post(
                    "/control", json=request.model_dump()
                )
        except Exception:  # noqa: BLE001 - unreachable Agent degrades to unknown
            return None
        if resp.status_code != 200:
            return None
        try:
            body = resp.json()
        except ValueError:
            return None
        data = body.get("data") or {}
        dialog = data.get("dialog")
        return dialog if isinstance(dialog, dict) else None

    def has_native_exit(
        self, profile_id: str, instance_id: str, config_version: int
    ) -> bool:
        """A native exit awaiting delivery takes precedence over synthetic exits."""
        return (profile_id, instance_id, config_version) in self._native_exit_instances

    def _write_runtime_snapshot(
        self, snap_path: Path, snapshot: ConfigVersionSnapshot
    ) -> None:
        atomic_write_text(snap_path, snapshot.model_dump_json(indent=2), mode=0o600)
        if getattr(self.docker, "manage_ownership", False):
            try:
                os.chown(
                    snap_path,
                    self.docker.runtime_uid,
                    self.docker.runtime_gid,
                )
            except OSError as exc:
                raise DockerSandboxError(
                    "Cannot assign runtime snapshot ownership: "
                    f"{type(exc).__name__}"
                ) from None

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
                raise LifecycleConflictError(
                    "Existing runtime must finish cleanup before a new start"
                )

            if force:
                if not operation_id:
                    raise ValueError("Manual retry requires an idempotent operation ID")
                await self.reset_blocked(profile_id, operation_id)
            state_response = await self.api.get(
                f"/api/v1/internal/supervisor/profiles/{quote(profile_id, safe='')}/runtime",
                headers=self._auth_headers(),
            )
            state_response.raise_for_status()
            runtime = state_response.json()
            if runtime["desired_state"] != "running":
                raise LifecycleConflictError(
                    "API running intent is required before starting a runtime"
                )

            if runtime["restart_blocked"]:
                raise LifecycleConflictError(
                    "Automatic retries exhausted; manual retry required"
                )

            runtime_instance_id = f"inst_{uuid.uuid4().hex[:12]}"
            self._native_exit_instances = {
                item for item in self._native_exit_instances if item[0] != profile_id
            }
            dirs = self.docker.prepare_profile_directories(profile_id)

            snap_path = dirs["runtime"] / "snapshot.json"
            snapshot = ConfigVersionSnapshot(
                id=f"snap_{uuid.uuid4().hex[:12]}",
                profile_id=profile_id,
                version=config_version,
                config=config.model_dump(),
                created_at=datetime.now(UTC).isoformat(),
            )
            self._write_runtime_snapshot(snap_path, snapshot)

            # Bind runtime instance via internal supervisor API
            try:
                bind_resp = await self.api.post(
                    f"/api/v1/internal/supervisor/runtimes/bind?profile_id={quote(profile_id, safe='')}",
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
                port = await self.ports.allocate(profile_id)
                await self.docker.create_profile_network(profile_id)
                media_addresses = None
                resolved_gateway = await asyncio.to_thread(self._resolve_gateway_id)
                if resolved_gateway:
                    media_addresses = await asyncio.to_thread(
                        self.docker.attach_profile_infrastructure,
                        profile_id,
                        resolved_gateway,
                        gateway_port=self.gateway_endpoint.port,
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

                # Launch Stream. Agent credentials live outside the Browser
                # runtime mount and are readable only by the Stream container.
                (dirs["runtime"] / "agent_secret.txt").unlink(missing_ok=True)
                secret_dir = self.docker.validator.get_secret_dir(profile_id)
                secret_dir.mkdir(parents=True, exist_ok=True)
                secret_dir.chmod(0o700)
                agent_secret = secret_dir / "agent_secret.txt"
                atomic_write_text(
                    agent_secret,
                    self.agent_credentials.token_for(profile_id, runtime_instance_id),
                    mode=0o600,
                )
                selkies_tokens = SelkiesTokens.generate()
                selkies_dir = secret_dir
                selkies_tokens_file = selkies_tokens.provision_credentials_file(
                    selkies_dir, runtime_instance_id
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
                    selkies_tokens_path=selkies_tokens_file,
                    snapshot_json_path=snap_path,
                    gateway_port=self.gateway_endpoint.port,
                )

                if self.gateway_control is None:
                    raise RuntimeError("Gateway control RPC is required for readiness")
                async with asyncio.timeout(15):
                    while True:
                        await asyncio.to_thread(s_container.reload)
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
                self._registration_known[profile_id] = True
                self._update_transport(
                    profile_id,
                    runtime_instance_id=runtime_instance_id,
                    browser_state="running",
                    stream_state="running",
                    transport_state="ready",
                    config_version=config_version,
                    protocol_version="v2",
                    gateway_endpoint=(
                        media_addresses.get("gateway_ip")
                        if media_addresses
                        else None
                    ),
                    last_attached_at=self._now_iso(),
                    last_registered_at=self._now_iso(),
                    last_error=None,
                )
                return session

            except Exception as err:
                logger.error(
                    "Sandbox launch failed for %s: error_type=%s error=%s",
                    profile_id,
                    type(err).__name__,
                    err,
                )
                await self.report_terminal_observation(
                    profile_id,
                    runtime_instance_id,
                    config_version,
                    observed_state="error",
                    reason="startup_failure",
                )
                try:
                    try:
                        await self.docker.teardown_profile(profile_id)
                    except Exception as cleanup_exc:  # noqa: BLE001 - launch failure cleanup error logged without overriding original startup error
                        logger.error(
                            "Launch cleanup failed: profile=%s error_type=%s",
                            profile_id,
                            type(cleanup_exc).__name__,
                        )
                    finally:
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
                    "status": "already_absent",
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
                # The target instance was superseded by a newer one. The
                # command is a no-op result: the replacement is protected
                # and must not be reported as stopped.
                superseded = {
                    "profile_id": profile_id,
                    "runtime_instance_id": target,
                    "status": "superseded_noop",
                }
                self.operations.complete(command_id, request, superseded)
                return superseded
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
                    absent = {
                        "profile_id": profile_id,
                        "runtime_instance_id": target,
                        "status": "already_absent",
                    }
                    self.operations.complete(command_id, request, absent)
                    return absent
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

            await self._report_observed(
                profile_id, curr_inst, "stopping", cfg_ver, reason="stop_requested"
            )
            if session is not None:
                session.observed_state = "stopping"

            await self.disconnect_viewers(profile_id)

            teardown_error: Exception | None = None
            try:
                await self.docker.teardown_profile(profile_id)
            except Exception as exc:  # noqa: BLE001 - teardown failure recorded for controlled propagation
                teardown_error = exc
                logger.error(
                    "Sandbox teardown failed: profile=%s error_type=%s",
                    profile_id,
                    type(exc).__name__,
                )
            finally:
                # Port ownership ends with this operation regardless of teardown.
                # Any residue is reconciled by the pre-start orphan cleanup.
                if self._sessions.get(profile_id) is session:
                    await self.ports.release(profile_id)
                    self._sessions.pop(profile_id, None)
                    self._terminal_observations.discard(
                        (profile_id, curr_inst, cfg_ver)
                    )
                    self.forget_instance_events(profile_id, curr_inst)
            if teardown_error is not None:
                raise DockerSandboxError(
                    "Sandbox teardown failed; residual containers require cleanup"
                ) from teardown_error

            await self._report_observed(
                profile_id, curr_inst, "stopped", cfg_ver, reason="stop_requested"
            )
            self.operations.complete(command_id, request, result)
            self._registration_known.pop(profile_id, None)
            self._update_transport(
                profile_id,
                browser_state="stopped",
                stream_state="stopped",
                transport_state="unknown",
            )
            logger.info(
                f"Profile {profile_id} cleanly stopped and resources reclaimed."
            )
            return result

    async def disconnect_viewers(self, profile_id: str) -> None:
        """Best-effort viewer closure; teardown never depends on signaling."""
        session = self._sessions.get(profile_id)
        if session is None:
            return
        if self.gateway_control is None:
            logger.warning(
                "Viewer disconnect skipped: Gateway control is not configured "
                "(profile=%s)",
                profile_id,
            )
            return
        try:
            async with asyncio.timeout(2.0):
                await self.gateway_control.disconnect_viewers(
                    profile_id, session.runtime_instance_id
                )
        except (httpx.HTTPError, OSError, TimeoutError) as exc:
            logger.warning(
                "Viewer disconnect failed; continuing teardown: profile=%s "
                "error_type=%s",
                profile_id,
                type(exc).__name__,
            )

    async def reset_blocked(self, profile_id: str, operation_id: str) -> None:
        response = await self.api.patch(
            f"/api/v1/internal/supervisor/profiles/{quote(profile_id, safe='')}/runtime/desired-state",
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

    async def report_terminal_observation(
        self,
        profile_id: str,
        runtime_instance_id: str,
        config_version: int,
        *,
        observed_state: str,
        reason: str,
    ) -> bool:
        """Report a terminal Agent/Docker fact once per runtime generation."""
        key = (profile_id, runtime_instance_id, config_version)
        if key in self._terminal_observations:
            return False
        delivered = await self._report_observed(
            profile_id,
            runtime_instance_id,
            observed_state,
            config_version,
            reason=reason,
        )
        if delivered:
            self._terminal_observations.add(key)
            session = self._sessions.get(profile_id)
            if (
                session is not None
                and session.runtime_instance_id == runtime_instance_id
            ):
                session.observed_state = observed_state
                if observed_state == "stopped" and reason == "normal_exit":
                    session.desired_state = "stopped"
            return True
        return False

    async def _report_observed(
        self,
        profile_id: str,
        runtime_instance_id: str,
        state: str,
        config_version: int,
        *,
        reason: str | None = None,
    ) -> bool:
        try:
            resp = await self.api.post(
                f"/api/v1/internal/supervisor/runtimes/observed?profile_id={quote(profile_id, safe='')}",
                headers=self._auth_headers(),
                json={
                    "runtime_instance_id": runtime_instance_id,
                    "observed_state": state,
                    "config_version": config_version,
                    "reason": reason,
                },
            )
            return resp.status_code == 200
        except Exception as e:  # noqa: BLE001 - API state report network failure logged and returns False
            logger.warning(
                "Observed state report failed: state=%s error_type=%s",
                state,
                type(e).__name__,
            )
            return False
