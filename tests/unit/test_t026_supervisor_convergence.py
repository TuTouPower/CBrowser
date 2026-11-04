"""t026 convergence: production SupervisorCore against Docker doubles.

Each case drives ``_converge_session`` (the steady-state pass that runs
inside reconciliation) with a scripted adapter and Gateway control
double, and asserts the *layer* that was repaired: Gateway replacement
re-attaches only, Stream drift replaces only the Stream, Browser drift
fails closed without teardown, and protocol-level registration refusals
never trigger a rebuild.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.supervisor.address_pool import plan_for_subnet
from cbrowser.supervisor.core import ActiveSession, SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerSandboxError
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator

PROFILE = "prof_t026"
INSTANCE = "inst_1"
PLAN = plan_for_subnet(ipaddress.ip_network("10.251.7.0/24"))


class _Container:
    def __init__(self, role: str) -> None:
        self.id = f"c_{role}"
        self.name = f"name_{role}"
        self.status = "running"
        self.labels = {"com.cbrowser.role": role}


class _FakeAdapter:
    def __init__(self, root: Path) -> None:
        self.validator = PathValidator(root)
        self.plan = PLAN
        self.conforms = True
        self.attached_gateway: str | None = "gw_1"
        self.gateway_id: str | None = "gw_1"
        self.stream_policy_ok = True
        self.browser_policy_ok = True
        self.calls: list[str] = []

    # -- inspection -------------------------------------------------
    def inspect_media_network(self, profile_id: str) -> dict:
        return {
            "exists": True,
            "conforms": self.conforms,
            "plan": self.plan if self.conforms else None,
            "gateway_attached_id": self.attached_gateway,
            "gateway_ip": self.plan.gateway_endpoint,
            "endpoints": {},
        }

    def resolve_gateway_container_id(self) -> str | None:
        return self.gateway_id

    def get_profile_containers(self, profile_id: str) -> dict:
        return {"browser": _Container("browser"), "stream": _Container("stream")}

    def get_stream_container_name(self, profile_id: str) -> str:
        return "stream_name"

    def get_network_name(self, profile_id: str) -> str:
        return "media_name"

    def stream_policy_spec(self, plan, gateway_port: int, udp_mux_port: int) -> dict:
        return {"role": "stream"}

    def browser_policy_spec(self, profile_id: str, container) -> dict:
        return {"role": "browser"}

    def verify_container_policy(self, container, spec) -> bool:
        return self.stream_policy_ok if spec["role"] == "stream" else self.browser_policy_ok

    # -- mutation ---------------------------------------------------
    def attach_profile_infrastructure(self, profile_id, gateway_id, gateway_port=None):
        self.calls.append(f"attach:{gateway_id}")
        self.attached_gateway = gateway_id
        return {
            "gateway_ip": self.plan.gateway_endpoint,
            "gateway_url": f"ws://{self.plan.gateway_endpoint}:8443",
            "browser_ip": "10.251.7.2",
        }

    async def create_profile_network(self, profile_id: str):
        self.calls.append("create_network")
        self.conforms = True
        return None

    def rebuild_media_network(self, profile_id: str):
        # Mirrors the production contract: old network removed, new
        # conforming network created, live containers reconnected.
        self.calls.append("cleanup_network:media_name")
        self.calls.append("create_network")
        self.conforms = True
        return None

    async def start_stream_container(self, **kwargs):
        self.calls.append("start_stream")
        return SimpleNamespace(id="c_stream_new")

    def cleanup_container_by_name(self, name: str) -> None:
        self.calls.append(f"cleanup_container:{name}")

    def cleanup_network_by_name(self, name: str) -> None:
        self.calls.append(f"cleanup_network:{name}")

    def fail_close_container(self, container) -> None:
        self.calls.append("fail_close")
        if getattr(self, "fail_close_error", None) is not None:
            raise self.fail_close_error

    def scan_active_containers(self) -> list:
        return []


class _FakeGatewayControl:
    def __init__(self) -> None:
        self.registered: bool | None = True
        self.rejection: dict | None = None

    async def agent_registered(self, profile_id: str, instance_id: str):
        return self.registered

    async def registration_status(self, profile_id: str):
        return {
            "profile_id": profile_id,
            "gateway_build_id": "gw-build-1",
            "agent_build_id": "agent-build-1",
            "selkies_version": "2.1.0",
            "rejection": self.rejection,
            "rejection_runtime_instance_id": INSTANCE if self.rejection else None,
        }


def _make_core(tmp_path: Path, adapter: _FakeAdapter, gateway: _FakeGatewayControl):
    api = httpx.AsyncClient(base_url="http://api.invalid", transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    core = SupervisorCore(
        adapter,
        PortAllocator(),
        EventForwarder("http://api.invalid", tmp_path / "spool", client=api),
        api,
        gateway_control=gateway,
        gateway_container_id="gw_stale",
    )
    session = ActiveSession(
        PROFILE, INSTANCE, 1, 30005, "c_browser", "c_stream",
        desired_state="running", observed_state="running",
    )
    core._sessions[PROFILE] = session
    scan = {
        "browser": {"status": "running", "instance_id": INSTANCE},
        "stream": {"status": "running", "instance_id": INSTANCE},
    }
    return core, session, scan


@pytest.mark.asyncio
async def test_gateway_replacement_reattaches_without_rebuild(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    adapter.gateway_id = "gw_2"  # Gateway was replaced; session points at gw_1
    adapter.attached_gateway = "gw_1"
    gateway = _FakeGatewayControl()
    core, session, scan = _make_core(tmp_path, adapter, gateway)

    await core._converge_session(PROFILE, session, scan)

    assert adapter.calls == ["attach:gw_2"]
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "ready"
    assert observation.gateway_endpoint == PLAN.gateway_endpoint
    assert observation.last_attached_at is not None


@pytest.mark.asyncio
async def test_healthy_pair_converges_to_ready_without_mutation(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    gateway = _FakeGatewayControl()
    core, session, scan = _make_core(tmp_path, adapter, gateway)

    await core._converge_session(PROFILE, session, scan)

    assert adapter.calls == []
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "ready"
    assert observation.agent_build_id == "agent-build-1"
    assert observation.gateway_build_id == "gw-build-1"
    assert core._registration_known[PROFILE] is True


@pytest.mark.asyncio
async def test_stream_policy_drift_replaces_stream_only(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    adapter.stream_policy_ok = False
    gateway = _FakeGatewayControl()
    core, session, scan = _make_core(tmp_path, adapter, gateway)
    secret_dir = adapter.validator.get_secret_dir(PROFILE)
    secret_dir.mkdir(parents=True, exist_ok=True)
    (secret_dir / "agent_secret.txt").write_text("x" * 40)

    await core._converge_session(PROFILE, session, scan)

    assert "start_stream" in adapter.calls
    assert "cleanup_container:stream_name" in adapter.calls
    assert not any(c.startswith("cleanup_network") for c in adapter.calls)
    # Browser identity is untouched by a Stream-only replacement.
    assert session.browser_container_id == "c_browser"
    assert session.stream_container_id == "c_stream_new"


@pytest.mark.asyncio
async def test_browser_policy_drift_fails_closed_without_teardown(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    adapter.browser_policy_ok = False
    gateway = _FakeGatewayControl()
    core, session, scan = _make_core(tmp_path, adapter, gateway)

    await core._converge_session(PROFILE, session, scan)
    await core._converge_session(PROFILE, session, scan)

    assert adapter.calls == ["fail_close"]  # applied once per instance
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "failed"
    assert observation.last_error == "browser_policy_drift"


@pytest.mark.asyncio
async def test_nonconformant_network_rebuilds_network_and_stream(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    adapter.conforms = False
    gateway = _FakeGatewayControl()
    core, session, scan = _make_core(tmp_path, adapter, gateway)
    secret_dir = adapter.validator.get_secret_dir(PROFILE)
    secret_dir.mkdir(parents=True, exist_ok=True)
    (secret_dir / "agent_secret.txt").write_text("x" * 40)

    await core._converge_session(PROFILE, session, scan)

    assert "cleanup_network:media_name" in adapter.calls
    assert "create_network" in adapter.calls
    assert "start_stream" in adapter.calls
    assert session.browser_container_id == "c_browser"


@pytest.mark.asyncio
async def test_nonfixable_rejection_never_replaces_stream(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    gateway = _FakeGatewayControl()
    gateway.registered = False
    gateway.rejection = {
        "code": "unsupported_version",
        "message": "Registration payload rejected",
        "gateway_build_id": "gw-build-1",
        "agent_build_id": "agent-old",
    }
    core, session, scan = _make_core(tmp_path, adapter, gateway)

    await core._converge_session(PROFILE, session, scan)

    assert "start_stream" not in adapter.calls
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "failed"
    assert observation.rejection_code == "unsupported_version"


@pytest.mark.asyncio
async def test_unregistered_without_rejection_replaces_stream_with_budget(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    gateway = _FakeGatewayControl()
    gateway.registered = False
    core, session, scan = _make_core(tmp_path, adapter, gateway)
    secret_dir = adapter.validator.get_secret_dir(PROFILE)
    secret_dir.mkdir(parents=True, exist_ok=True)
    (secret_dir / "agent_secret.txt").write_text("x" * 40)

    for _ in range(4):
        await core._converge_session(PROFILE, session, scan)

    starts = [c for c in adapter.calls if c == "start_stream"]
    assert len(starts) == SupervisorCore._STREAM_REPLACE_MAX
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "failed"
    assert observation.last_error == "stream_unregistered"


@pytest.mark.asyncio
async def test_gateway_unreachable_never_rebuilds(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    gateway = _FakeGatewayControl()
    gateway.registered = None  # Gateway itself unreachable
    core, session, scan = _make_core(tmp_path, adapter, gateway)

    await core._converge_session(PROFILE, session, scan)

    assert adapter.calls == []
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "recovering"
    assert observation.last_error == "gateway_unreachable"


@pytest.mark.asyncio
async def test_offline_recovery_only_reattaches(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    adapter.attached_gateway = None
    gateway = _FakeGatewayControl()
    core, session, scan = _make_core(tmp_path, adapter, gateway)

    await core._recover_attachment_offline(PROFILE)

    assert adapter.calls == ["attach:gw_1"]
    assert core._sessions[PROFILE] is session


@pytest.mark.asyncio
async def test_readiness_unknown_when_api_unavailable(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    gateway = _FakeGatewayControl()
    core, session, scan = _make_core(tmp_path, adapter, gateway)

    result = await core.readiness()

    assert result.ready is False
    assert result.reason is not None
    assert result.reason.startswith("api_unavailable")


def test_runtime_pair_active_requires_registration_when_known():
    from cbrowser.supervisor.recovery_rules import runtime_pair_active

    browser = {"status": "running", "instance_id": INSTANCE}
    stream = {"status": "running", "instance_id": INSTANCE}
    assert runtime_pair_active("running", INSTANCE, browser, stream) is True
    assert (
        runtime_pair_active(
            "running", INSTANCE, browser, stream, stream_registered=True
        )
        is True
    )
    # A Stream container that runs while its Agent is known to be
    # unregistered is not an active pair (t026 registration convergence).
    assert (
        runtime_pair_active(
            "running", INSTANCE, browser, stream, stream_registered=False
        )
        is False
    )


# --- Round-2 additions: review findings t026_code_f002/f003/f004/f005,
# --- t026_test_f002/f003/f005 ---------------------------------------


@pytest.mark.asyncio
async def test_gateway_missing_aborts_replacement_before_teardown(tmp_path):
    # AC-008 / code f002: with no Gateway to re-attach to, replacement
    # must not tear the Stream (or the network) down first.
    adapter = _FakeAdapter(tmp_path)
    adapter.gateway_id = None
    adapter.attached_gateway = None
    gateway = _FakeGatewayControl()
    core, session, _scan = _make_core(tmp_path, adapter, gateway)
    core.gateway_container_id = None  # no fallback ID either: truly absent

    replaced = await core._replace_stream_only(
        PROFILE, session, rebuild_network=False
    )

    assert replaced is False
    assert adapter.calls == []
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "recovering"
    assert observation.last_error == "gateway_missing"


@pytest.mark.asyncio
async def test_browser_fail_close_failure_is_retried_not_marked(tmp_path):
    # AC-005 / code f004: a failed fail-close is not "handled" — the
    # observation stays unmitigated and the next cycle retries.
    adapter = _FakeAdapter(tmp_path)
    adapter.browser_policy_ok = False
    adapter.fail_close_error = DockerSandboxError("helper unavailable")
    gateway = _FakeGatewayControl()
    core, session, scan = _make_core(tmp_path, adapter, gateway)

    await core._converge_session(PROFILE, session, scan)
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "recovering"
    assert observation.last_error == "browser_policy_drift_unmitigated"
    assert (PROFILE, INSTANCE) not in core._policy_fail_closed

    adapter.fail_close_error = None
    await core._converge_session(PROFILE, session, scan)
    observation = core.get_transport_observation(PROFILE)
    assert adapter.calls.count("fail_close") == 2
    assert observation.transport_state == "failed"
    assert observation.last_error == "browser_policy_drift"
    assert (PROFILE, INSTANCE) in core._policy_fail_closed


def _core_with_runtime_api(tmp_path, adapter, gateway, runtime_by_profile):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/internal/supervisor/profiles":
            return httpx.Response(
                200, json=[{"id": pid} for pid in runtime_by_profile]
            )
        for pid, payload in runtime_by_profile.items():
            if path.endswith(f"/profiles/{pid}/runtime"):
                if isinstance(payload, Exception):
                    raise payload
                return httpx.Response(200, json=payload)
        return httpx.Response(404)

    api = httpx.AsyncClient(
        base_url="http://api.invalid",
        transport=httpx.MockTransport(handler),
    )
    core = SupervisorCore(
        adapter,
        PortAllocator(),
        EventForwarder("http://api.invalid", tmp_path / "spool", client=api),
        api,
        gateway_control=gateway,
        gateway_container_id="gw_1",
    )
    return core


@pytest.mark.asyncio
async def test_missing_stream_with_session_routes_to_replacement(tmp_path):
    # AC-008 / code f003: Browser present, Stream gone, desired running
    # and a tracked session — reconcile rebuilds the Stream instead of
    # retaining the incomplete pair forever.
    adapter = _FakeAdapter(tmp_path)
    gateway = _FakeGatewayControl()
    runtime = {
        "desired_state": "running",
        "runtime_instance_id": INSTANCE,
        "config_version": 1,
    }
    core = _core_with_runtime_api(tmp_path, adapter, gateway, {PROFILE: runtime})
    session = ActiveSession(
        PROFILE, INSTANCE, 1, 30005, "c_browser", "c_stream",
        desired_state="running", observed_state="running",
    )
    core._sessions[PROFILE] = session
    replaced: list[str] = []

    async def _record_replace(profile_id, sess, **kwargs):
        replaced.append(profile_id)
        return True

    core._replace_stream_only = _record_replace
    roles = {"browser": {"status": "running", "instance_id": INSTANCE}}
    await core._reconcile_profile(PROFILE, roles)
    assert replaced == [PROFILE]


@pytest.mark.asyncio
async def test_missing_stream_without_session_is_retained(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    gateway = _FakeGatewayControl()
    runtime = {
        "desired_state": "running",
        "runtime_instance_id": INSTANCE,
        "config_version": 1,
    }
    core = _core_with_runtime_api(tmp_path, adapter, gateway, {PROFILE: runtime})
    replaced: list[str] = []

    async def _record_replace(profile_id, sess, **kwargs):
        replaced.append(profile_id)
        return True

    core._replace_stream_only = _record_replace
    roles = {"browser": {"status": "running", "instance_id": INSTANCE}}
    await core._reconcile_profile(PROFILE, roles)
    assert replaced == []


@pytest.mark.asyncio
async def test_offline_recovery_without_session_uses_scan_instance(tmp_path):
    # AC-006 / code f005: after a Supervisor restart there is no
    # in-memory session; the label-verified scan instance still
    # authorizes attachment-only recovery.
    adapter = _FakeAdapter(tmp_path)
    adapter.attached_gateway = None  # drifted: nothing attached
    gateway = _FakeGatewayControl()
    core, _session, _scan = _make_core(tmp_path, adapter, gateway)
    core._sessions.clear()

    await core._recover_attachment_offline(PROFILE, INSTANCE)

    assert adapter.calls == ["attach:gw_1"]
    observation = core.get_transport_observation(PROFILE)
    assert observation.runtime_instance_id == INSTANCE
    assert observation.transport_state == "recovering"
    assert observation.last_attached_at is not None


@pytest.mark.asyncio
async def test_replacement_observes_recovering_mid_flight(tmp_path):
    # AC-004 / test f005: while a Stream-only replacement is in flight,
    # the transport observation reads recovering, not ready/failed.
    adapter = _FakeAdapter(tmp_path)
    adapter.stream_policy_ok = False
    gateway = _FakeGatewayControl()
    core, session, scan = _make_core(tmp_path, adapter, gateway)
    secret_dir = adapter.validator.get_secret_dir(PROFILE)
    secret_dir.mkdir(parents=True, exist_ok=True)
    (secret_dir / "agent_secret.txt").write_text("x" * 40)
    sampled: list[str] = []
    original_start = adapter.start_stream_container

    async def _sampling_start(**kwargs):
        sampled.append(
            core.get_transport_observation(PROFILE).transport_state
        )
        return await original_start(**kwargs)

    adapter.start_stream_container = _sampling_start
    await core._converge_session(PROFILE, session, scan)
    assert sampled == ["recovering"]


@pytest.mark.asyncio
async def test_concurrent_profiles_converge_without_cross_talk(tmp_path):
    # AC-007 / test f003: two Profiles converging in the same pass keep
    # their repairs separate — one re-attaches, the other replaces its
    # Stream; neither touches the other's state.
    import asyncio as _asyncio

    class _PerProfileAdapter(_FakeAdapter):
        def __init__(self, root):
            super().__init__(root)
            self.attached = {"prof_a": None, "prof_b": "gw_1"}
            self.policy = {"prof_a": True, "prof_b": False}
            self.per_profile_calls: list[str] = []

        def inspect_media_network(self, profile_id):
            body = super().inspect_media_network(profile_id)
            body["gateway_attached_id"] = self.attached[profile_id]
            return body

        def attach_profile_infrastructure(
            self, profile_id, gateway_id, gateway_port=None
        ):
            self.per_profile_calls.append(f"attach:{profile_id}")
            self.attached[profile_id] = gateway_id
            return {
                "gateway_ip": self.plan.gateway_endpoint,
                "gateway_url": f"ws://{self.plan.gateway_endpoint}:8443",
            }

        def verify_container_policy(self, container, spec):
            return self.policy[container.profile_id]

    adapter = _PerProfileAdapter(tmp_path)
    gateway = _FakeGatewayControl()
    core, _s, _scan = _make_core(tmp_path, adapter, gateway)
    sessions = {}
    scans = {}
    for pid in ("prof_a", "prof_b"):
        sessions[pid] = ActiveSession(
            pid, INSTANCE, 1, 30005, "c_browser", "c_stream",
            desired_state="running", observed_state="running",
        )
        core._sessions[pid] = sessions[pid]
        scans[pid] = {
            "browser": {"status": "running", "instance_id": INSTANCE},
            "stream": {"status": "running", "instance_id": INSTANCE},
        }
    secret_dir = adapter.validator.get_secret_dir("prof_b")
    secret_dir.mkdir(parents=True, exist_ok=True)
    (secret_dir / "agent_secret.txt").write_text("x" * 40)

    class _TaggedContainer(_Container):
        def __init__(self, role, profile_id):
            super().__init__(role)
            self.profile_id = profile_id

    adapter.get_profile_containers = lambda pid: {
        "browser": _TaggedContainer("browser", pid),
        "stream": _TaggedContainer("stream", pid),
    }

    await _asyncio.gather(
        core._converge_session("prof_a", sessions["prof_a"], scans["prof_a"]),
        core._converge_session("prof_b", sessions["prof_b"], scans["prof_b"]),
    )

    # prof_a was re-attached by convergence; prof_b was re-attached by
    # its Stream-only replacement. Each attach carried its own Profile.
    assert sorted(adapter.per_profile_calls) == [
        "attach:prof_a",
        "attach:prof_b",
    ]
    # Only prof_b's Stream was replaced; prof_a kept its container id.
    assert sessions["prof_a"].stream_container_id == "c_stream"
    assert sessions["prof_b"].stream_container_id == "c_stream_new"
    assert (
        core.get_transport_observation("prof_a").transport_state == "ready"
    )


@pytest.mark.asyncio
async def test_readiness_all_checks_green_is_ready(tmp_path):
    # AC-009 / test f002: per-Profile readiness evaluates instance,
    # containers, attachment, policy and registration — all green here.
    adapter = _FakeAdapter(tmp_path)
    gateway = _FakeGatewayControl()
    runtime = {
        "desired_state": "running",
        "runtime_instance_id": INSTANCE,
        "config_version": 1,
    }
    core = _core_with_runtime_api(tmp_path, adapter, gateway, {PROFILE: runtime})
    core._sessions[PROFILE] = ActiveSession(
        PROFILE, INSTANCE, 1, 30005, "c_browser", "c_stream",
        desired_state="running", observed_state="running",
    )

    result = await core.readiness()

    assert result.ready is True
    assert len(result.profiles) == 1
    entry = result.profiles[0]
    assert entry.ready is True
    assert entry.checks["registration"] is True
    assert entry.checks["policy"] is True


@pytest.mark.asyncio
async def test_readiness_registration_unverifiable_is_not_ready(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    gateway = _FakeGatewayControl()
    gateway.registered = None  # Gateway unreachable: unknown, not ready
    runtime = {
        "desired_state": "running",
        "runtime_instance_id": INSTANCE,
        "config_version": 1,
    }
    core = _core_with_runtime_api(tmp_path, adapter, gateway, {PROFILE: runtime})
    core._sessions[PROFILE] = ActiveSession(
        PROFILE, INSTANCE, 1, 30005, "c_browser", "c_stream",
        desired_state="running", observed_state="running",
    )

    result = await core.readiness()

    assert result.ready is False
    entry = result.profiles[0]
    assert entry.ready is False
    assert entry.checks["registration"] is None
    assert "registration_unverifiable" in entry.diagnostics


@pytest.mark.asyncio
async def test_readiness_one_profile_runtime_failure_isolated(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    gateway = _FakeGatewayControl()
    runtime = {
        "desired_state": "running",
        "runtime_instance_id": INSTANCE,
        "config_version": 1,
    }
    core = _core_with_runtime_api(
        tmp_path,
        adapter,
        gateway,
        {PROFILE: runtime, "prof_bad": httpx.ConnectError("down")},
    )
    core._sessions[PROFILE] = ActiveSession(
        PROFILE, INSTANCE, 1, 30005, "c_browser", "c_stream",
        desired_state="running", observed_state="running",
    )

    result = await core.readiness()

    assert result.ready is False
    by_id = {entry.profile_id: entry for entry in result.profiles}
    assert by_id[PROFILE].ready is True
    assert by_id["prof_bad"].ready is False
    assert by_id["prof_bad"].diagnostics[0].startswith("runtime_unavailable")


# --- Round-3 additions: t026_code_f003(residual)/f009/f011,
# --- t026_test_f006/f007 --------------------------------------------


@pytest.mark.asyncio
async def test_exited_stream_repaired_in_place_not_pair_error(tmp_path):
    # AC-008 / code f003 residual: Browser running, Stream exited —
    # reconcile repairs the Stream layer instead of escalating to a
    # whole-pair container_exit error.
    adapter = _FakeAdapter(tmp_path)
    gateway = _FakeGatewayControl()
    runtime = {
        "desired_state": "running",
        "runtime_instance_id": INSTANCE,
        "config_version": 1,
    }
    core = _core_with_runtime_api(tmp_path, adapter, gateway, {PROFILE: runtime})
    session = ActiveSession(
        PROFILE, INSTANCE, 1, 30005, "c_browser", "c_stream",
        desired_state="running", observed_state="running",
    )
    core._sessions[PROFILE] = session

    async def _observation_ok(*args, **kwargs):
        return "running"

    core._reconcile_instance_observation = _observation_ok
    replaced: list[str] = []
    terminal: list[str] = []

    async def _record_replace(profile_id, sess, **kwargs):
        replaced.append(profile_id)
        return True

    async def _record_terminal(*args, **kwargs):
        terminal.append("container_exit")
        return True

    core._replace_stream_only = _record_replace
    core.report_terminal_observation = _record_terminal
    roles = {
        "browser": {"status": "running", "instance_id": INSTANCE},
        "stream": {"status": "exited", "instance_id": INSTANCE},
    }
    await core._reconcile_profile(PROFILE, roles)
    assert replaced == [PROFILE]
    assert terminal == []


@pytest.mark.asyncio
async def test_missing_stream_budget_exhausted_never_replaces(tmp_path):
    # AC-008 / code f011: the missing-Stream route honors the same
    # bounded replacement budget as every other Stream-only repair.
    import time as _time

    adapter = _FakeAdapter(tmp_path)
    gateway = _FakeGatewayControl()
    runtime = {
        "desired_state": "running",
        "runtime_instance_id": INSTANCE,
        "config_version": 1,
    }
    core = _core_with_runtime_api(tmp_path, adapter, gateway, {PROFILE: runtime})
    session = ActiveSession(
        PROFILE, INSTANCE, 1, 30005, "c_browser", "c_stream",
        desired_state="running", observed_state="running",
    )
    core._sessions[PROFILE] = session
    now = _time.monotonic()
    core._stream_replace_attempts[f"{PROFILE}:{INSTANCE}"] = [now, now, now]
    replaced: list[str] = []

    async def _record_replace(profile_id, sess, **kwargs):
        replaced.append(profile_id)
        return True

    core._replace_stream_only = _record_replace
    roles = {"browser": {"status": "running", "instance_id": INSTANCE}}
    await core._reconcile_profile(PROFILE, roles)
    assert replaced == []
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "failed"
    assert observation.last_error == "stream_missing_budget_exhausted"


@pytest.mark.asyncio
async def test_readiness_docker_failure_isolated_per_profile(tmp_path):
    # AC-009 / code f009: a Docker error inside one Profile's
    # evaluation degrades that Profile to not-ready with a diagnostic;
    # readiness() itself never raises.
    adapter = _FakeAdapter(tmp_path)

    def _boom(profile_id):
        raise DockerSandboxError("daemon gone")

    adapter.inspect_media_network = _boom
    gateway = _FakeGatewayControl()
    runtime = {
        "desired_state": "running",
        "runtime_instance_id": INSTANCE,
        "config_version": 1,
    }
    core = _core_with_runtime_api(tmp_path, adapter, gateway, {PROFILE: runtime})
    core._sessions[PROFILE] = ActiveSession(
        PROFILE, INSTANCE, 1, 30005, "c_browser", "c_stream",
        desired_state="running", observed_state="running",
    )

    result = await core.readiness()

    assert result.ready is False
    entry = result.profiles[0]
    assert entry.ready is False
    assert entry.diagnostics[0].startswith("readiness_check_failed")


@pytest.mark.asyncio
async def test_readiness_missing_stream_policy_unverifiable(tmp_path):
    # code f006 guard branch / test f006: with the Stream container
    # missing, policy is unknown (None) with the unverifiable
    # diagnostic — never an exception, never a guessed pass.
    adapter = _FakeAdapter(tmp_path)
    adapter.get_profile_containers = lambda pid: {
        "browser": _Container("browser"),
        "stream": None,
    }
    gateway = _FakeGatewayControl()
    runtime = {
        "desired_state": "running",
        "runtime_instance_id": INSTANCE,
        "config_version": 1,
    }
    core = _core_with_runtime_api(tmp_path, adapter, gateway, {PROFILE: runtime})
    core._sessions[PROFILE] = ActiveSession(
        PROFILE, INSTANCE, 1, 30005, "c_browser", "c_stream",
        desired_state="running", observed_state="running",
    )

    result = await core.readiness()

    assert result.ready is False
    entry = result.profiles[0]
    assert entry.checks["policy"] is None
    assert "policy_unverifiable" in entry.diagnostics


@pytest.mark.asyncio
async def test_converge_inspect_failure_records_degraded_observation(tmp_path):
    # code f007 / test f007: media inspection failure surfaces as a
    # named degraded observation, not just a scan-level warning.
    adapter = _FakeAdapter(tmp_path)

    def _boom(profile_id):
        raise DockerSandboxError("daemon gone")

    adapter.inspect_media_network = _boom
    gateway = _FakeGatewayControl()
    core, session, scan = _make_core(tmp_path, adapter, gateway)

    await core._converge_session(PROFILE, session, scan)

    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "failed"
    assert observation.last_error == "media_inspect_failed"


@pytest.mark.asyncio
async def test_converge_attach_failure_records_degraded_observation(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    adapter.attached_gateway = "gw_old"  # drift forces an attach attempt

    def _boom(profile_id, gateway_id, gateway_port=None):
        raise DockerSandboxError("endpoint held by another container")

    adapter.attach_profile_infrastructure = _boom
    gateway = _FakeGatewayControl()
    core, session, scan = _make_core(tmp_path, adapter, gateway)

    await core._converge_session(PROFILE, session, scan)

    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "failed"
    assert observation.last_error == "media_attach_failed"


@pytest.mark.asyncio
async def test_latched_container_exit_error_releases_on_authoritative_running(
    tmp_path,
):
    # code f014: the container_exit fallback latches
    # session.observed_state="error"; once the pair is healthy again,
    # the authoritative observation ("running") must release the latch
    # or the same-instance branch can never report running or converge
    # again for this instance.
    import time as _time

    adapter = _FakeAdapter(tmp_path)
    gateway = _FakeGatewayControl()
    runtime = {
        "desired_state": "running",
        "runtime_instance_id": INSTANCE,
        "config_version": 1,
    }
    core = _core_with_runtime_api(tmp_path, adapter, gateway, {PROFILE: runtime})
    session = ActiveSession(
        PROFILE, INSTANCE, 1, 30005, "c_browser", "c_stream",
        desired_state="running", observed_state="running",
    )
    core._sessions[PROFILE] = session

    # The production terminal-observation path runs against a
    # recording API (code f015: a stub without dedupe semantics hid
    # the latch/dedupe interaction this test exists to catch).
    observed_posts: list[dict] = []

    def _recording_handler(request: httpx.Request) -> httpx.Response:
        if "runtimes/observed" in request.url.path:
            import json as _json

            observed_posts.append(_json.loads(request.content))
            return httpx.Response(200, json={})
        if request.url.path.endswith(f"/profiles/{PROFILE}/runtime"):
            return httpx.Response(200, json=runtime)
        return httpx.Response(404)

    core.api = httpx.AsyncClient(
        base_url="http://api.invalid",
        transport=httpx.MockTransport(_recording_handler),
    )

    async def _observation_ok(*args, **kwargs):
        return "running"

    core._reconcile_instance_observation = _observation_ok
    converged: list[str] = []

    async def _record_converge(profile_id, sess, roles):
        converged.append(profile_id)

    core._converge_session = _record_converge

    # Stage 1: Stream exited, replacement budget exhausted -> the
    # fallback latches the pair error and reports it exactly once.
    now = _time.monotonic()
    core._stream_replace_attempts[f"{PROFILE}:{INSTANCE}"] = [now, now, now]
    roles_down = {
        "browser": {"status": "running", "instance_id": INSTANCE},
        "stream": {"status": "exited", "instance_id": INSTANCE},
    }
    await core._reconcile_profile(PROFILE, roles_down)
    assert session.observed_state == "error"
    exits = [p for p in observed_posts if p.get("reason") == "container_exit"]
    assert len(exits) == 1
    assert (PROFILE, INSTANCE, 1) in core._terminal_observations

    # Stage 2: budget window slid, both containers running again ->
    # the latch releases, the dedupe key is discarded with it, and
    # convergence resumes for this instance.
    core._stream_replace_attempts.clear()
    roles_up = {
        "browser": {"status": "running", "instance_id": INSTANCE},
        "stream": {"status": "running", "instance_id": INSTANCE},
    }
    await core._reconcile_profile(PROFILE, roles_up)
    assert session.observed_state == "running"
    assert converged == [PROFILE]
    assert (PROFILE, INSTANCE, 1) not in core._terminal_observations

    # Stage 3: the Stream dies again with the budget exhausted again.
    # The generation demonstrably recovered, so this new terminal fact
    # must be reported again — not swallowed by the old dedupe key.
    core._stream_replace_attempts[f"{PROFILE}:{INSTANCE}"] = [now, now, now]
    await core._reconcile_profile(PROFILE, roles_down)
    assert session.observed_state == "error"
    exits = [p for p in observed_posts if p.get("reason") == "container_exit"]
    assert len(exits) == 2


@pytest.mark.asyncio
async def test_latch_release_clears_terminal_keys_across_versions(tmp_path):
    # t026_code_f016 / p036: the release path derives bound_version
    # from the container label when the runtime payload omits
    # config_version. A dedupe key written under the session version
    # must still be cleared; clearing only the derived version would
    # leave the old key behind and swallow the next terminal fact.
    adapter = _FakeAdapter(tmp_path)
    gateway = _FakeGatewayControl()
    runtime = {
        "desired_state": "running",
        "runtime_instance_id": INSTANCE,
    }
    core = _core_with_runtime_api(tmp_path, adapter, gateway, {PROFILE: runtime})
    session = ActiveSession(
        PROFILE, INSTANCE, 1, 30005, "c_browser", "c_stream",
        desired_state="running", observed_state="error",
    )
    core._sessions[PROFILE] = session
    core._terminal_observations.add((PROFILE, INSTANCE, 1))

    async def _observation_ok(*args, **kwargs):
        return "running"

    core._reconcile_instance_observation = _observation_ok
    converged: list[str] = []

    async def _record_converge(profile_id, sess, roles):
        converged.append(profile_id)

    core._converge_session = _record_converge

    roles_up = {
        "browser": {
            "status": "running",
            "instance_id": INSTANCE,
            "config_version": 2,
        },
        "stream": {"status": "running", "instance_id": INSTANCE},
    }
    await core._reconcile_profile(PROFILE, roles_up)

    assert session.observed_state == "running"
    assert converged == [PROFILE]
    # Both the label-derived version (2) and the session-version key
    # (1) are gone; no stale key survives this instance generation.
    assert not [
        item for item in core._terminal_observations
        if item[0] == PROFILE and item[1] == INSTANCE
    ]


@pytest.mark.asyncio
async def test_readiness_failure_in_one_profile_still_evaluates_others(tmp_path):
    # test f011: the f009 isolation is per-Profile — a Docker failure
    # for one Profile must not skip evaluating the healthy one.
    adapter = _FakeAdapter(tmp_path)
    real_inspect = adapter.inspect_media_network

    def _selective_boom(profile_id):
        if profile_id == "prof_bad":
            raise DockerSandboxError("daemon gone")
        return real_inspect(profile_id)

    adapter.inspect_media_network = _selective_boom
    gateway = _FakeGatewayControl()
    runtime = {
        "desired_state": "running",
        "runtime_instance_id": INSTANCE,
        "config_version": 1,
    }
    # The failing Profile comes FIRST in the API list: a regression
    # that short-circuits on the first failure would never evaluate
    # the healthy Profile and this test must catch that (test f012).
    core = _core_with_runtime_api(
        tmp_path, adapter, gateway, {"prof_bad": runtime, PROFILE: runtime}
    )
    for pid in ("prof_bad", PROFILE):
        core._sessions[pid] = ActiveSession(
            pid, INSTANCE, 1, 30005, "c_browser", "c_stream",
            desired_state="running", observed_state="running",
        )

    result = await core.readiness()

    assert result.ready is False
    by_id = {entry.profile_id: entry for entry in result.profiles}
    assert by_id[PROFILE].ready is True
    assert by_id["prof_bad"].ready is False
    assert by_id["prof_bad"].diagnostics[0].startswith("readiness_check_failed")
