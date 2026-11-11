"""t055: Supervisor runtime robustness (A4-A8).

Tests-first for adoption A4-A8 / A10-A13 (review_20261110_200842).
A10 has its own integration file; A11-A13 have their own unit files.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.runtime_agent.protocol import HealthResponse
from cbrowser.supervisor.address_pool import plan_for_subnet
from cbrowser.supervisor.core import (
    MEDIA_ATTACH_GATEWAY_MISSING,
    ActiveSession,
    RegistrationState,
    SupervisorCore,
)
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.gateway_client import GatewayControlClient
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator
from docker.errors import DockerException

pytestmark = pytest.mark.serial

PROFILE = "prof_t055"
INSTANCE = "inst_t055"
GATEWAY = "gw_t055"
PLAN = plan_for_subnet(ipaddress.ip_network("10.251.9.0/24"))
UDP_PORT = 30007
SECRET = "hunter2-secret-value"

BROWSER = "sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346"
STREAM = "sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531"


# ---------------------------------------------------------------------------
# A4: policy helper cleanup / install failure log capture
# ---------------------------------------------------------------------------


class _Helper:
    def __init__(self, *, wait_error=None, status=0, remove_error=None, logs=b""):
        self.wait_error = wait_error
        self.status = status
        self.remove_error = remove_error
        self._logs = logs
        self.removed = False

    def wait(self, timeout=None):
        if self.wait_error is not None:
            raise self.wait_error
        return {"StatusCode": self.status}

    def logs(self):
        if isinstance(self._logs, Exception):
            raise self._logs
        return self._logs

    def remove(self, force=False):
        if self.remove_error is not None:
            raise self.remove_error
        self.removed = True


def _policy_adapter(tmp_path, helper):
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    client = SimpleNamespace(
        containers=SimpleNamespace(run=lambda *a, **kw: helper)
    )
    return DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=client,
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
    )


def _install(adapter, gate):
    adapter._install_network_policy(
        SimpleNamespace(id="target-id"),
        {
            "role": "stream",
            "allowed_tcp": [],
            "allowed_udp": [],
            "udp_mux_port": 30005,
        },
        gate,
        "inst1",
        "stream",
    )


def _gate(tmp_path):
    gate = tmp_path / "gate"
    gate.mkdir()
    return gate


def test_run_policy_helper_remove_failure_keeps_exit_code(tmp_path):
    """AC-001: helper remove failure must not overwrite the exit code."""
    helper = _Helper(status=0, remove_error=DockerException("cleanup broke"))
    adapter = _policy_adapter(tmp_path, helper)

    assert adapter.verify_container_policy(
        SimpleNamespace(id="target-id"),
        {
            "role": "stream",
            "allowed_tcp": [],
            "allowed_udp": [],
            "udp_mux_port": 30005,
        },
    ) is True


def test_run_policy_helper_remove_failure_keeps_mismatch_code(tmp_path):
    """AC-001: exit 4 (definite mismatch) survives a remove failure too."""
    helper = _Helper(status=4, remove_error=DockerException("cleanup broke"))
    adapter = _policy_adapter(tmp_path, helper)

    assert adapter.verify_container_policy(
        SimpleNamespace(id="target-id"),
        {
            "role": "stream",
            "allowed_tcp": [],
            "allowed_udp": [],
            "udp_mux_port": 30005,
        },
    ) is False


def test_install_failure_logs_helper_output_redacted(tmp_path, caplog):
    """AC-001: install failure log carries the helper output, no secrets."""
    helper = _Helper(
        status=1,
        logs=(
            b"iptables: rule rejected\n"
            b"debug: password=" + SECRET.encode() + b"\n"
        ),
    )
    adapter = _policy_adapter(tmp_path, helper)
    gate = _gate(tmp_path)

    with caplog.at_level(logging.ERROR, logger="cbrowser.supervisor.docker_adapter"):
        with pytest.raises(DockerSandboxError):
            _install(adapter, gate)

    assert "iptables" in caplog.text
    assert SECRET not in caplog.text
    assert helper.removed is True


def test_install_failure_logs_only_helper_output_tail(tmp_path, caplog):
    """AC-001: a >2000-byte helper output is truncated to its tail in the log."""
    head = b"HEAD-MARKER-AAAA\n"
    tail = b"\nTAIL-MARKER-BBBB\n"
    logs = head + b"x" * 3000 + tail + b"debug: password=" + SECRET.encode() + b"\n"
    assert len(logs) > 2000
    helper = _Helper(status=1, logs=logs)
    adapter = _policy_adapter(tmp_path, helper)
    gate = _gate(tmp_path)

    with caplog.at_level(logging.ERROR, logger="cbrowser.supervisor.docker_adapter"):
        with pytest.raises(DockerSandboxError):
            _install(adapter, gate)

    assert "TAIL-MARKER-BBBB" in caplog.text
    assert "HEAD-MARKER-AAAA" not in caplog.text
    assert SECRET not in caplog.text
    assert helper.removed is True


def test_install_failure_logs_failure_when_helper_logs_raise(tmp_path):
    """AC-001: a failing logs() must not mask the install failure."""
    helper = _Helper(
        status=1, logs=DockerException("logs broke"),
    )
    adapter = _policy_adapter(tmp_path, helper)
    gate = _gate(tmp_path)

    with pytest.raises(DockerSandboxError):
        _install(adapter, gate)
    assert helper.removed is True


# ---------------------------------------------------------------------------
# Shared core fixture (A5/A6/A7/A8)
# ---------------------------------------------------------------------------


def _api_404() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    return httpx.AsyncClient(
        base_url="http://api.invalid",
        transport=httpx.MockTransport(handler),
    )


def _core(tmp_path, docker, api=None) -> SupervisorCore:
    return SupervisorCore(
        docker,
        PortAllocator(),
        EventForwarder("http://api.invalid", tmp_path / "spool", client=_api_404()),
        api or _api_404(),
    )


# ---------------------------------------------------------------------------
# A5: forget_instance_events precision
# ---------------------------------------------------------------------------


def test_forget_instance_events_removes_only_matching_instance(tmp_path):
    """AC-002: only the named instance's native-exit records are removed."""
    core = _core(
        tmp_path,
        SimpleNamespace(validator=PathValidator(tmp_path)),
    )
    core._native_exit_instances = {
        (PROFILE, "old-inst", 1): ("stopped", "normal_exit"),
        (PROFILE, "new-inst", 1): ("error", "agent_exit"),
        ("other-prof", "old-inst", 1): ("stopped", "normal_exit"),
    }
    core._terminal_observations = {(PROFILE, "new-inst", 1)}
    core._event_cursors = {PROFILE: {"old-inst": ["a"], "new-inst": ["b"]}}

    core.forget_instance_events(PROFILE, "old-inst")

    assert (PROFILE, "old-inst", 1) not in core._native_exit_instances
    assert core._native_exit_instances[(PROFILE, "new-inst", 1)] == (
        "error",
        "agent_exit",
    )
    assert core._native_exit_instances[("other-prof", "old-inst", 1)] == (
        "stopped",
        "normal_exit",
    )
    assert core._event_cursors[PROFILE] == {"new-inst": ["b"]}


# ---------------------------------------------------------------------------
# A6: media attach gateway parse failure / offline recovery consumption
# ---------------------------------------------------------------------------


class _MediaAdapter:
    """Adapter double whose gateway scan fails with DockerSandboxError."""

    def __init__(self, root: Path) -> None:
        self.validator = PathValidator(root)

    def inspect_media_network(self, profile_id: str) -> dict:
        return {
            "exists": True,
            "conforms": True,
            "plan": PLAN,
            "gateway_attached_id": None,
            "gateway_ip": None,
            "endpoints": {},
        }

    def resolve_gateway_container_id(self):
        raise DockerSandboxError("Gateway scan failed: daemon down")

    def attach_profile_infrastructure(self, *args, **kwargs):
        raise AssertionError("must not be reached when the scan fails")


@pytest.mark.asyncio
async def test_ensure_media_attachment_gateway_scan_failure_is_status(tmp_path):
    """AC-003: a gateway parse failure becomes a status, never an exception."""
    core = _core(tmp_path, _MediaAdapter(tmp_path))

    outcome = await core._ensure_media_attachment(PROFILE, INSTANCE)

    assert outcome.status == MEDIA_ATTACH_GATEWAY_MISSING


@pytest.mark.asyncio
async def test_recover_attachment_offline_logs_non_ok_status_rate_limited(
    tmp_path, caplog
):
    """AC-003: offline recovery consumes the status and logs it, rate-limited."""
    core = _core(tmp_path, _MediaAdapter(tmp_path))

    with caplog.at_level(logging.WARNING, logger="cbrowser.supervisor.core"):
        await core._recover_attachment_offline(PROFILE, INSTANCE)
        await core._recover_attachment_offline(PROFILE, INSTANCE)

    warnings = [
        r for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    assert PROFILE in warnings[0].getMessage()
    assert MEDIA_ATTACH_GATEWAY_MISSING in warnings[0].getMessage()

    # After the rate-limit window the warning fires again.
    core._offline_attach_log_at[PROFILE] -= 61.0
    with caplog.at_level(logging.WARNING, logger="cbrowser.supervisor.core"):
        await core._recover_attachment_offline(PROFILE, INSTANCE)
    warnings = [
        r for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert len(warnings) == 2


# ---------------------------------------------------------------------------
# A7: restore must not preset running; registration grace from restore time
# ---------------------------------------------------------------------------


class _Container:
    def __init__(self, role: str) -> None:
        self.id = f"c_{role}"
        self.name = f"name_{role}"
        self.status = "running"
        self.labels = {"com.cbrowser.role": role}


class _RestoreAdapter:
    """Docker adapter double for the restore path (trimmed t049 harness)."""

    def __init__(self, root: Path) -> None:
        self.validator = PathValidator(root)
        self.conforms = True
        self.attached_gateway: str | None = GATEWAY
        self.gateway_id: str | None = GATEWAY
        self.calls: list[str] = []
        self.torn_down = False
        self.client = SimpleNamespace(
            api=SimpleNamespace(inspect_container=self._inspect_container),
            containers=SimpleNamespace(list=self._list_containers),
        )

    def _inspect_container(self, container_id: str) -> dict:
        return {
            "HostConfig": {
                "PortBindings": {
                    f"{UDP_PORT}/udp": [{"HostPort": str(UDP_PORT)}]
                }
            }
        }

    def _list_containers(self, **kwargs):
        return [_Container("browser")]

    def scan_active_containers(self) -> list[dict]:
        return [
            {
                "id": "c_browser",
                "name": "name_browser",
                "status": "running",
                "profile_id": PROFILE,
                "instance_id": INSTANCE,
                "role": "browser",
                "config_version": 1,
                "policy_ready": True,
            },
            {
                "id": "c_stream",
                "name": "name_stream",
                "status": "running",
                "profile_id": PROFILE,
                "instance_id": INSTANCE,
                "role": "stream",
                "config_version": 1,
                "policy_ready": True,
            },
        ]

    def inspect_media_network(self, profile_id: str) -> dict:
        return {
            "exists": True,
            "conforms": self.conforms,
            "plan": PLAN if self.conforms else None,
            "gateway_attached_id": self.attached_gateway,
            "gateway_ip": (
                PLAN.gateway_endpoint if self.attached_gateway else None
            ),
            "endpoints": {},
        }

    def resolve_gateway_container_id(self) -> str | None:
        return self.gateway_id

    def attach_profile_infrastructure(
        self, profile_id: str, gateway_id: str, gateway_port=None
    ) -> dict:
        self.calls.append(f"attach:{gateway_id}")
        self.attached_gateway = gateway_id
        return {
            "gateway_ip": PLAN.gateway_endpoint,
            "gateway_url": f"ws://{PLAN.gateway_endpoint}:8443",
            "browser_ip": "10.251.9.2",
        }

    def get_profile_containers(self, profile_id: str) -> dict:
        return {"browser": _Container("browser"), "stream": _Container("stream")}

    def get_stream_container_name(self, profile_id: str) -> str:
        return "name_stream"

    def stream_policy_spec(self, plan, gateway_port: int, udp_mux_port: int) -> dict:
        return {"role": "stream"}

    def browser_policy_spec(self, profile_id: str, container) -> dict:
        return {"role": "browser"}

    def verify_container_policy(self, container, spec) -> bool:
        return True

    def rebuild_media_network(self, profile_id: str) -> None:
        self.calls.append("rebuild_network")
        self.conforms = True

    def cleanup_container_by_name(self, name: str) -> None:
        self.calls.append(f"cleanup_container:{name}")

    async def start_stream_container(self, **kwargs):
        self.calls.append("start_stream")
        return SimpleNamespace(id="c_stream_new")

    def teardown_profile(self, profile_id: str) -> None:
        self.torn_down = True

    def fail_close_container(self, container) -> None:
        self.calls.append("fail_close")


class _FakeGatewayControl:
    """agent_registered returns the scripted reading (True/False/None)."""

    def __init__(self) -> None:
        self.registered = None

    async def agent_registered(self, profile_id: str, instance_id: str):
        return self.registered

    async def registration_status(self, profile_id: str):
        return None


def _visibility_503() -> httpx.Response:
    return httpx.Response(
        503,
        json={"detail": "Agent unavailable for this instance"},
    )


def _gateway_control(tmp_path: Path) -> GatewayControlClient:
    token_file = tmp_path / "gateway_token"
    token_file.write_text("g" * 40, encoding="utf-8")
    token_file.chmod(0o600)
    client = GatewayControlClient("http://gateway.invalid", token_file)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/visibility"):
            return _visibility_503()
        if request.url.path.endswith("/registration"):
            return httpx.Response(200, json={})
        return httpx.Response(404)

    client._client = httpx.AsyncClient(
        base_url="http://gateway.invalid",
        transport=httpx.MockTransport(handler),
    )
    return client


def _recording_api(runtime: dict, recorded: list) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        try:
            body = request.content
            payload = json.loads(body) if body else None
        except Exception:  # noqa: BLE001 - a non-JSON body is recorded as-is
            payload = None
        recorded.append((request.method, str(request.url.path), payload))
        if request.url.path.endswith(f"/profiles/{PROFILE}/runtime"):
            return httpx.Response(200, json=runtime)
        return httpx.Response(200, json={})

    return httpx.AsyncClient(
        base_url="http://api.invalid",
        transport=httpx.MockTransport(handler),
    )


def _make_restore_core(tmp_path, adapter, gateway, api) -> SupervisorCore:
    return SupervisorCore(
        adapter,
        PortAllocator(),
        EventForwarder("http://api.invalid", tmp_path / "spool", client=_api_404()),
        api,
        gateway_control=gateway,
    )


def _runtime_starting(instance: str = INSTANCE) -> dict:
    return {
        "profile_id": PROFILE,
        "desired_state": "running",
        "observed_state": "starting",
        "runtime_instance_id": instance,
        "config_version": 1,
    }


def _roles() -> dict:
    return {
        "browser": {
            "id": "c_browser",
            "name": "name_browser",
            "status": "running",
            "profile_id": PROFILE,
            "instance_id": INSTANCE,
            "role": "browser",
            "config_version": 1,
            "policy_ready": True,
        },
        "stream": {
            "id": "c_stream",
            "name": "name_stream",
            "status": "running",
            "profile_id": PROFILE,
            "instance_id": INSTANCE,
            "role": "stream",
            "config_version": 1,
            "policy_ready": True,
        },
    }


def _health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        ready=True,
        display_ready=True,
        browser_ready=True,
        audio_ready=True,
        cdp_ready=True,
        profile_id=PROFILE,
        runtime_instance_id=INSTANCE,
        config_version=1,
        details={},
    )


def _observed_running_reports(recorded: list) -> list:
    return [
        payload
        for method, path, payload in recorded
        if method == "POST"
        and "observed" in path
        and isinstance(payload, dict)
        and payload.get("observed_state") == "running"
    ]


@pytest.mark.asyncio
async def test_restore_presets_starting_and_reports_nothing(tmp_path, monkeypatch):
    """AC-004: restore presets 'starting' and reports no 'running' to the API."""
    adapter = _RestoreAdapter(tmp_path)
    gateway = _gateway_control(tmp_path)
    recorded: list = []
    core = _make_restore_core(
        tmp_path, adapter, gateway, _recording_api(_runtime_starting(), recorded)
    )

    async def _no_health(profile_id: str):
        return None

    monkeypatch.setattr(core, "_query_agent_health", _no_health)

    await core.scan_and_reconcile_existing()

    session = core.get_session(PROFILE)
    assert isinstance(session, ActiveSession)
    assert session.observed_state == "starting"
    assert _observed_running_reports(recorded) == []
    assert core._registration[PROFILE].recovery_armed is True


@pytest.mark.asyncio
async def test_health_confirmation_upgrades_starting_to_running(
    tmp_path, monkeypatch
):
    """AC-004: Agent health confirmation upgrades 'starting' to 'running'."""
    adapter = _RestoreAdapter(tmp_path)
    gateway = _gateway_control(tmp_path)
    recorded: list = []
    core = _make_restore_core(
        tmp_path, adapter, gateway, _recording_api(_runtime_starting(), recorded)
    )

    async def _no_health(profile_id: str):
        return None

    monkeypatch.setattr(core, "_query_agent_health", _no_health)
    await core.scan_and_reconcile_existing()
    assert core.get_session(PROFILE).observed_state == "starting"

    async def _matching_health(profile_id: str):
        return _health()

    monkeypatch.setattr(core, "_query_agent_health", _matching_health)
    await core._reconcile_profile(PROFILE, _roles())

    session = core.get_session(PROFILE)
    assert session.observed_state == "running"
    assert len(_observed_running_reports(recorded)) == 1


@pytest.mark.asyncio
async def test_restore_armed_grace_survives_gateway_unreachable(tmp_path):
    """AC-005: restore grace is kept across gateway-unreachable passes."""
    adapter = _RestoreAdapter(tmp_path)
    gateway = _gateway_control(tmp_path)
    recorded: list = []
    core = _make_restore_core(
        tmp_path, adapter, gateway, _recording_api(_runtime_starting(), recorded)
    )
    fake_gateway = _FakeGatewayControl()
    core.gateway_control = fake_gateway

    await core.scan_and_reconcile_existing()
    state = core._registration[PROFILE]
    assert state.recovery_armed is True
    lost_at = state.lost_at
    assert lost_at is not None

    session = core.get_session(PROFILE)
    fake_gateway.registered = None
    await core._converge_session(PROFILE, session, _roles())

    # Retained, not reset: same object, same lost_at.
    assert core._registration[PROFILE] is state
    assert core._registration[PROFILE].lost_at == lost_at
    observation = core.get_transport_observation(PROFILE)
    assert observation.last_error == "gateway_unreachable"


@pytest.mark.asyncio
async def test_restore_grace_defers_stream_replacement_then_releases(tmp_path):
    """AC-005: unregistered Stream waits out the restore grace, then replaces."""
    adapter = _RestoreAdapter(tmp_path)
    gateway = _gateway_control(tmp_path)
    recorded: list = []
    core = _make_restore_core(
        tmp_path, adapter, gateway, _recording_api(_runtime_starting(), recorded)
    )
    fake_gateway = _FakeGatewayControl()
    core.gateway_control = fake_gateway

    await core.scan_and_reconcile_existing()
    session = core.get_session(PROFILE)

    fake_gateway.registered = False
    await core._converge_session(PROFILE, session, _roles())
    observation = core.get_transport_observation(PROFILE)
    assert observation.last_error == "registration_recovery_grace"
    assert "start_stream" not in adapter.calls

    # Grace expired: the same unregistered Stream takes the replacement path.
    # _replace_stream_only reuses the existing Agent secret (t026 pattern).
    secret_dir = adapter.validator.get_secret_dir(PROFILE)
    secret_dir.mkdir(parents=True, exist_ok=True)
    (secret_dir / "agent_secret.txt").write_text("x" * 40)
    core._registration[PROFILE].lost_at = time.monotonic() - 200.0
    await core._converge_session(PROFILE, session, _roles())
    assert "start_stream" in adapter.calls


@pytest.mark.asyncio
async def test_restore_grace_boundary_89s_still_defers(tmp_path):
    """AC-005: 89s into the 90s restore grace, replacement still defers."""
    adapter = _RestoreAdapter(tmp_path)
    gateway = _gateway_control(tmp_path)
    recorded: list = []
    core = _make_restore_core(
        tmp_path, adapter, gateway, _recording_api(_runtime_starting(), recorded)
    )
    fake_gateway = _FakeGatewayControl()
    core.gateway_control = fake_gateway

    await core.scan_and_reconcile_existing()
    session = core.get_session(PROFILE)

    fake_gateway.registered = False
    core._registration[PROFILE].lost_at = time.monotonic() - 89.0
    await core._converge_session(PROFILE, session, _roles())
    observation = core.get_transport_observation(PROFILE)
    assert observation.last_error == "registration_recovery_grace"
    assert "start_stream" not in adapter.calls


@pytest.mark.asyncio
async def test_restore_grace_boundary_91s_triggers_replacement(tmp_path):
    """AC-005: 91s into the 90s restore grace, replacement is triggered."""
    adapter = _RestoreAdapter(tmp_path)
    gateway = _gateway_control(tmp_path)
    recorded: list = []
    core = _make_restore_core(
        tmp_path, adapter, gateway, _recording_api(_runtime_starting(), recorded)
    )
    fake_gateway = _FakeGatewayControl()
    core.gateway_control = fake_gateway

    await core.scan_and_reconcile_existing()
    session = core.get_session(PROFILE)

    fake_gateway.registered = False
    # _replace_stream_only reuses the existing Agent secret (t026 pattern).
    secret_dir = adapter.validator.get_secret_dir(PROFILE)
    secret_dir.mkdir(parents=True, exist_ok=True)
    (secret_dir / "agent_secret.txt").write_text("x" * 40)
    core._registration[PROFILE].lost_at = time.monotonic() - 91.0
    await core._converge_session(PROFILE, session, _roles())
    assert "start_stream" in adapter.calls


@pytest.mark.asyncio
async def test_fresh_registration_replaces_restore_armed_state_at_once(tmp_path):
    """AC-005: a registration arriving inside the grace replaces immediately."""
    adapter = _RestoreAdapter(tmp_path)
    gateway = _gateway_control(tmp_path)
    recorded: list = []
    core = _make_restore_core(
        tmp_path, adapter, gateway, _recording_api(_runtime_starting(), recorded)
    )
    fake_gateway = _FakeGatewayControl()
    core.gateway_control = fake_gateway

    await core.scan_and_reconcile_existing()
    assert core._registration[PROFILE].recovery_armed is True

    session = core.get_session(PROFILE)
    fake_gateway.registered = True
    await core._converge_session(PROFILE, session, _roles())

    state = core._registration[PROFILE]
    assert state.known is True
    assert state.lost_at is None
    assert state.recovery_armed is False
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "ready"


# ---------------------------------------------------------------------------
# A8: Browser container lookup
# ---------------------------------------------------------------------------


def _lookup_container(instance: str, status: str = "running") -> SimpleNamespace:
    # Mirrors a production Browser container (p058 shape): the runtime
    # instance id is carried by the gated entrypoint / command, never labels.
    return SimpleNamespace(
        status=status,
        labels={
            "com.cbrowser.prefix": "cb",
            "com.cbrowser.profile-id": "p1",
            "com.cbrowser.role": "browser",
        },
        attrs={
            "Config": {
                "Entrypoint": [
                    "python3",
                    "-m",
                    "cbrowser.supervisor.gated_entrypoint",
                    "--instance-id",
                    instance,
                    "--role",
                    "browser",
                ],
                "Cmd": ["--runtime-instance-id", instance],
            }
        },
    )


class _LookupClient:
    def __init__(self, containers=None, error=None) -> None:
        self._containers = containers or []
        self._error = error

    def list(self, **kwargs):
        if self._error is not None:
            raise self._error
        return list(self._containers)


def _lookup_core(tmp_path, containers=None, *, error=None) -> SupervisorCore:
    docker = SimpleNamespace(
        validator=PathValidator(tmp_path),
        resource_prefix="cb",
        deployment_instance_id=None,
        client=SimpleNamespace(
            containers=_LookupClient(containers, error=error)
        ),
    )
    return SupervisorCore(
        docker,
        PortAllocator(),
        EventForwarder("http://api.invalid", tmp_path / "spool", client=_api_404()),
        _api_404(),
    )


@pytest.mark.asyncio
async def test_lookup_reports_all_foreign_instances(tmp_path):
    """AC-006: mismatch reports every foreign instance id, in order."""
    core = _lookup_core(
        tmp_path,
        [_lookup_container("other-a"), _lookup_container("other-b")],
    )

    lookup = await core._lookup_browser_container("p1", "inst1")

    assert lookup.outcome == "instance_mismatch"
    assert lookup.observed_instance_id == ("other-a", "other-b")


@pytest.mark.asyncio
async def test_lookup_reports_single_foreign_instance_as_one_tuple(tmp_path):
    """AC-006: successor of the deleted p058 single-id test (tuple form)."""
    core = _lookup_core(tmp_path, [_lookup_container("other")])

    lookup = await core._lookup_browser_container("p1", "inst1")

    assert lookup.outcome == "instance_mismatch"
    assert lookup.observed_instance_id == ("other",)


@pytest.mark.asyncio
async def test_lookup_non_docker_failure_is_logged(tmp_path, caplog):
    """AC-006: a non-NotFound lookup failure is logged, not swallowed."""
    core = _lookup_core(tmp_path, error=RuntimeError("docker down"))

    with caplog.at_level(logging.WARNING, logger="cbrowser.supervisor.core"):
        lookup = await core._lookup_browser_container("p1", "inst1")

    assert lookup.outcome == "unavailable"
    assert any(
        "p1" in r.getMessage() and "RuntimeError" in r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING
    )


@pytest.mark.asyncio
async def test_reconcile_returns_none_on_instance_mismatch(tmp_path, monkeypatch):
    """AC-006 (caller level): mismatch yields no observation."""
    core = _lookup_core(
        tmp_path,
        [_lookup_container("other-a"), _lookup_container("other-b")],
    )

    result = await core._reconcile_instance_observation("p1", "inst1", 1)

    assert result is None


@pytest.mark.asyncio
async def test_reconcile_reports_terminal_on_missing_container(tmp_path):
    """AC-006 (caller level): a missing container reports the terminal state."""
    core = _lookup_core(tmp_path, [])
    # _report_observed needs a 200 from the API to count as delivered.
    recorded: list = []
    core.api = _recording_api({}, recorded)

    result = await core._reconcile_instance_observation("p1", "inst1", 1)

    assert result == "error"
