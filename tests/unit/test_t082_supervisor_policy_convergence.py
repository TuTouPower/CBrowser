"""t082 convergence: Policy Agent recovery, isolation and resume ownership.

Drives ``SupervisorCore._converge_session`` with a scripted adapter
double (same shape as the t026 suite) and asserts the new semantics:
unconfirmed policy state repairs the Agent in place, isolates the
exact target inside the 30 s budget when confirmation stays
impossible, and resumes only targets this mechanism paused, only
while they are still the current desired=running instance with
re-verified rules.
"""

from __future__ import annotations

import ipaddress
import time
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

pytestmark = pytest.mark.serial

PROFILE = "prof_t082"
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
        self.stream_policy_ok = True
        self.browser_policy_ok = True
        self.stream_verify_error: Exception | None = None
        self.browser_verify_error: Exception | None = None
        self.fail_close_error: Exception | None = None
        self.repair_fixes_browser = False
        self.reinstall_fixes_browser = False
        self.calls: list[str] = []

    def inspect_media_network(self, profile_id: str) -> dict:
        return {
            "exists": True,
            "conforms": True,
            "plan": self.plan,
            "gateway_attached_id": "gw_1",
            "gateway_ip": self.plan.gateway_endpoint,
            "endpoints": {},
        }

    def resolve_gateway_container_id(self) -> str | None:
        return "gw_1"

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
        if spec["role"] == "stream":
            if self.stream_verify_error is not None:
                raise self.stream_verify_error
            return self.stream_policy_ok
        if self.browser_verify_error is not None:
            raise self.browser_verify_error
        return self.browser_policy_ok

    def ensure_policy_agent_for_container(self, container) -> None:
        self.calls.append(f"repair_agent:{container.id}")
        if container.id == "c_browser" and self.repair_fixes_browser:
            self.browser_verify_error = None

    def fail_close_container(self, container) -> None:
        self.calls.append("fail_close")
        if self.fail_close_error is not None:
            raise self.fail_close_error

    def reinstall_container_policy(self, container, spec) -> None:
        self.calls.append("reinstall")
        if self.reinstall_fixes_browser:
            self.browser_policy_ok = True

    def pause_container(self, container) -> None:
        self.calls.append(f"pause:{container.id}")

    def unpause_container(self, container) -> None:
        self.calls.append(f"unpause:{container.id}")

    def attach_profile_infrastructure(self, profile_id, gateway_id, gateway_port=None):
        self.calls.append(f"attach:{gateway_id}")
        return {
            "gateway_ip": self.plan.gateway_endpoint,
            "gateway_url": f"ws://{self.plan.gateway_endpoint}:8443",
            "browser_ip": "10.251.7.2",
        }

    async def start_stream_container(self, **kwargs):
        self.calls.append("start_stream")
        return SimpleNamespace(id="c_stream_new")

    def cleanup_container_by_name(self, name: str) -> None:
        self.calls.append(f"cleanup_container:{name}")

    def cleanup_network_by_name(self, name: str) -> None:
        self.calls.append(f"cleanup_network:{name}")


class _FakeGatewayControl:
    async def agent_registered(self, profile_id: str, instance_id: str):
        return True

    async def registration_status(self, profile_id: str):
        return {
            "profile_id": profile_id,
            "gateway_build_id": "gw-build-1",
            "agent_build_id": "agent-build-1",
            "selkies_version": "2.2.1",
            "rejection": None,
            "rejection_runtime_instance_id": None,
        }


def _make_core(tmp_path: Path, adapter: _FakeAdapter):
    key_file = tmp_path / "agent_key"
    key_file.write_text("k" * 64, encoding="utf-8")
    key_file.chmod(0o600)
    api = httpx.AsyncClient(
        base_url="http://api.invalid",
        transport=httpx.MockTransport(lambda r: httpx.Response(404)),
    )
    core = SupervisorCore(
        adapter,
        PortAllocator(),
        EventForwarder("http://api.invalid", tmp_path / "spool", client=api),
        api,
        gateway_control=_FakeGatewayControl(),
        gateway_container_id="gw_1",
        agent_key_file=key_file,
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
async def test_browser_drift_fail_close_success_never_pauses(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    adapter.browser_policy_ok = False
    core, session, scan = _make_core(tmp_path, adapter)

    await core._converge_session(PROFILE, session, scan)

    assert adapter.calls == ["fail_close"]
    assert core._policy_paused == {}
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "failed"
    assert observation.last_error == "browser_policy_drift"


@pytest.mark.asyncio
async def test_browser_drift_unconfirmed_closure_pauses_exact_target(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    adapter.browser_policy_ok = False
    adapter.fail_close_error = DockerSandboxError("agent gone")
    core, session, scan = _make_core(tmp_path, adapter)

    await core._converge_session(PROFILE, session, scan)

    assert adapter.calls == ["fail_close", "pause:c_browser"]
    assert (PROFILE, INSTANCE) in core._policy_paused
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "failed"
    assert observation.last_error == "browser_policy_drift"


@pytest.mark.asyncio
async def test_mechanism_paused_browser_resumes_after_reverification(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    adapter.browser_policy_ok = False
    adapter.fail_close_error = DockerSandboxError("agent gone")
    core, session, scan = _make_core(tmp_path, adapter)
    await core._converge_session(PROFILE, session, scan)
    assert (PROFILE, INSTANCE) in core._policy_paused

    # Rules verify again (the drift is gone): resume without reinstall.
    adapter.browser_policy_ok = True
    adapter.calls.clear()
    await core._converge_session(PROFILE, session, scan)
    assert adapter.calls == ["unpause:c_browser"]
    assert core._policy_paused == {}
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "ready"


@pytest.mark.asyncio
async def test_paused_browser_reinstalls_then_resumes(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    core, session, scan = _make_core(tmp_path, adapter)
    core._policy_paused[(PROFILE, INSTANCE)] = time.monotonic()
    adapter.browser_policy_ok = False
    adapter.reinstall_fixes_browser = True

    await core._converge_session(PROFILE, session, scan)

    assert adapter.calls == ["reinstall", "unpause:c_browser"]
    assert core._policy_paused == {}


@pytest.mark.asyncio
async def test_paused_browser_stays_paused_while_rules_unverified(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    core, session, scan = _make_core(tmp_path, adapter)
    core._policy_paused[(PROFILE, INSTANCE)] = time.monotonic()
    adapter.browser_policy_ok = False  # reinstall does not fix it

    await core._converge_session(PROFILE, session, scan)

    assert "unpause:c_browser" not in adapter.calls
    assert (PROFILE, INSTANCE) in core._policy_paused
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "failed"
    assert observation.last_error == "browser_policy_isolated"


@pytest.mark.asyncio
async def test_agent_unavailable_repairs_then_isolates_after_budget(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    adapter.browser_verify_error = DockerSandboxError("agent unavailable")
    core, session, scan = _make_core(tmp_path, adapter)

    await core._converge_session(PROFILE, session, scan)
    # Repair was attempted in place; budget not yet expired: no pause.
    assert adapter.calls == ["repair_agent:c_browser"]
    assert core._policy_paused == {}
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "recovering"
    assert observation.last_error == "policy_verify_unavailable"

    # Age the unconfirmed state past the 30 s budget: isolate.
    key = (PROFILE, INSTANCE, "browser")
    core._policy_unknown_since[key] = time.monotonic() - 31.0
    adapter.calls.clear()
    await core._converge_session(PROFILE, session, scan)
    assert "pause:c_browser" in adapter.calls
    assert (PROFILE, INSTANCE) in core._policy_paused
    observation = core.get_transport_observation(PROFILE)
    assert observation.last_error == "browser_policy_unverifiable"


@pytest.mark.asyncio
async def test_agent_repair_restores_verification_without_isolation(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    adapter.browser_verify_error = DockerSandboxError("agent unavailable")
    adapter.repair_fixes_browser = True
    core, session, scan = _make_core(tmp_path, adapter)

    await core._converge_session(PROFILE, session, scan)

    assert adapter.calls == ["repair_agent:c_browser"]
    assert core._policy_paused == {}
    assert core._policy_unknown_since == {}
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "ready"


@pytest.mark.asyncio
async def test_stream_agent_unavailable_replaces_stream_only_after_budget(
    tmp_path,
):
    adapter = _FakeAdapter(tmp_path)
    adapter.stream_verify_error = DockerSandboxError("agent unavailable")
    adapter.validator.get_secret_dir(PROFILE).mkdir(parents=True, exist_ok=True)
    adapter.validator.get_runtime_dir(PROFILE).mkdir(parents=True, exist_ok=True)
    core, session, scan = _make_core(tmp_path, adapter)
    key = (PROFILE, INSTANCE, "stream")
    core._policy_unknown_since[key] = time.monotonic() - 31.0

    await core._converge_session(PROFILE, session, scan)

    # Stream isolation is the bounded Stream-only replacement; the
    # Browser is never paused, fail-closed or rebuilt from here.
    assert "start_stream" in adapter.calls
    assert "pause:c_browser" not in adapter.calls
    assert "fail_close" not in adapter.calls


@pytest.mark.asyncio
async def test_other_instances_pause_record_is_never_resumed(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    core, session, scan = _make_core(tmp_path, adapter)
    # A pause record for a replaced instance must not leak into the
    # current instance's convergence: no unpause is ever issued.
    core._policy_paused[(PROFILE, "inst_old")] = time.monotonic()

    await core._converge_session(PROFILE, session, scan)

    assert not any(call.startswith("unpause") for call in adapter.calls)
    assert (PROFILE, "inst_old") in core._policy_paused


@pytest.mark.asyncio
async def test_policy_agent_event_repairs_only_that_profile(tmp_path):
    adapter = _FakeAdapter(tmp_path)
    core, session, scan = _make_core(tmp_path, adapter)

    await core.note_policy_agent_event(PROFILE)
    assert adapter.calls == ["repair_agent:c_browser", "repair_agent:c_stream"]

    adapter.calls.clear()
    await core.note_policy_agent_event("prof_unknown")
    assert adapter.calls == []


# --- wiring-level cases (review round 1) --------------------------------
#
# The cases above drive _converge_session directly with a scan that
# always reports "running".  The cases below drive the production
# entry (_reconcile_profile with the API runtime payload) so the
# scan-state routing itself is under test.


def _core_with_runtime_api(tmp_path: Path, adapter: _FakeAdapter, runtime: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        # t083: the Supervisor reads intent through the minimal batch
        # snapshot; the per-profile runtime payload maps onto it.
        if path.endswith("/state/snapshot"):
            state = {
                "profile_id": PROFILE,
                "display_number": 1,
                "desired_state": runtime["desired_state"],
                "observed_state": runtime.get("observed_state", "running"),
                "runtime_instance_id": runtime.get("runtime_instance_id"),
                "config_version": runtime.get("config_version", 1),
                "failure_count": runtime.get("failure_count", 0),
                "restart_blocked": runtime.get("restart_blocked", False),
                "last_exit_event_id": runtime.get("last_exit_event_id"),
                "backoff_started_at": runtime.get("backoff_started_at"),
                "next_retry_at": runtime.get("next_retry_at"),
                "updated_at": "2026-01-01T00:00:00+00:00",
                "state_revision": runtime.get("state_revision", 1),
            }
            return httpx.Response(
                200,
                json={
                    "api_epoch": "t082-test-epoch",
                    "profiles": [state],
                    "next_cursor": None,
                },
            )
        return httpx.Response(404)

    api = httpx.AsyncClient(
        base_url="http://api.invalid",
        transport=httpx.MockTransport(handler),
    )
    key_file = tmp_path / "agent_key"
    key_file.write_text("k" * 64, encoding="utf-8")
    key_file.chmod(0o600)
    core = SupervisorCore(
        adapter,
        PortAllocator(),
        EventForwarder("http://api.invalid", tmp_path / "spool", client=api),
        api,
        gateway_control=_FakeGatewayControl(),
        gateway_container_id="gw_1",
        agent_key_file=key_file,
    )
    session = ActiveSession(
        PROFILE, INSTANCE, 1, 30005, "c_browser", "c_stream",
        desired_state="running", observed_state="running",
    )
    core._sessions[PROFILE] = session
    return core, session


@pytest.mark.asyncio
async def test_reconcile_routes_paused_browser_to_verified_resume(tmp_path):
    # code f001: after this mechanism pauses the Browser, the Docker
    # scan reports it "paused" — reconcile must route the pair into
    # convergence (which re-verifies and resumes), never report the
    # pause as a container exit and never strand the isolation.
    adapter = _FakeAdapter(tmp_path)
    runtime = {
        "desired_state": "running",
        "runtime_instance_id": INSTANCE,
        "config_version": 1,
        "observed_state": "running",
    }
    core, session = _core_with_runtime_api(tmp_path, adapter, runtime)
    core._policy_paused[(PROFILE, INSTANCE)] = time.monotonic()
    roles = {
        "browser": {
            "status": "paused",
            "instance_id": INSTANCE,
            "id": "c_browser",
            "config_version": 1,
            "policy_ready": True,
        },
        "stream": {
            "status": "running",
            "instance_id": INSTANCE,
            "id": "c_stream",
            "config_version": 1,
            "policy_ready": True,
        },
    }

    await core._reconcile_profile(PROFILE, roles)

    assert "unpause:c_browser" in adapter.calls
    assert core._policy_paused == {}
    # The pause was never reported as a terminal container exit.
    assert core._terminal_observations == set()
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "ready"


@pytest.mark.asyncio
async def test_stream_agent_unavailable_budget_exhausted_fails(tmp_path):
    # test f002: with the Stream replacement budget already spent,
    # an unconfirmable Stream policy is a bounded failed state, not
    # another replacement.
    adapter = _FakeAdapter(tmp_path)
    adapter.stream_verify_error = DockerSandboxError("agent unavailable")
    core, session, scan = _make_core(tmp_path, adapter)
    key = (PROFILE, INSTANCE, "stream")
    core._policy_unknown_since[key] = time.monotonic() - 31.0
    budget_key = f"{PROFILE}:{INSTANCE}"
    core._stream_replace_attempts[budget_key] = [time.monotonic()] * (
        core._STREAM_REPLACE_MAX
    )

    await core._converge_session(PROFILE, session, scan)

    assert "start_stream" not in adapter.calls
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "failed"
    assert observation.last_error == "stream_policy_agent_unavailable"


@pytest.mark.asyncio
async def test_paused_target_with_stopped_intent_is_never_resumed(tmp_path):
    # test f003 / AC-008: the mechanism's resume fence includes the
    # current intent — a paused record for an instance whose desired
    # state is no longer "running" stays isolated even when its rules
    # would verify.
    adapter = _FakeAdapter(tmp_path)
    core, session, scan = _make_core(tmp_path, adapter)
    session.desired_state = "stopped"
    core._policy_paused[(PROFILE, INSTANCE)] = time.monotonic()
    adapter.browser_policy_ok = True

    await core._converge_session(PROFILE, session, scan)

    assert "unpause:c_browser" not in adapter.calls
    assert (PROFILE, INSTANCE) in core._policy_paused
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "failed"
    assert observation.last_error == "browser_policy_isolated"


@pytest.mark.asyncio
async def test_reconcile_restores_paused_browser_after_supervisor_restart(
    tmp_path,
):
    # code f005: after a Supervisor restart there is no session and
    # no in-memory pause record; the scan shows the Browser paused.
    # Reconcile must fall through to restore, re-register the
    # isolation ownership, and resume only after re-verification —
    # never report the pause as a container exit.
    from types import SimpleNamespace

    adapter = _FakeAdapter(tmp_path)
    adapter.client = SimpleNamespace(
        api=SimpleNamespace(
            inspect_container=lambda cid: {
                "HostConfig": {
                    "PortBindings": {"30005/udp": [{"HostPort": "30005"}]}
                }
            }
        )
    )
    runtime = {
        "desired_state": "running",
        "runtime_instance_id": INSTANCE,
        "config_version": 1,
        "observed_state": "running",
    }
    core, _session = _core_with_runtime_api(tmp_path, adapter, runtime)
    core._sessions.clear()  # the restart: nothing is tracked
    assert core._policy_paused == {}
    roles = {
        "browser": {
            "status": "paused",
            "instance_id": INSTANCE,
            "id": "c_browser",
            "config_version": 1,
            "policy_ready": True,
        },
        "stream": {
            "status": "running",
            "instance_id": INSTANCE,
            "id": "c_stream",
            "config_version": 1,
            "policy_ready": True,
        },
    }

    await core._reconcile_profile(PROFILE, roles)

    assert PROFILE in core._sessions  # restore created the session
    assert "unpause:c_browser" in adapter.calls
    assert core._policy_paused == {}  # resumed and ownership cleared
    assert core._terminal_observations == set()  # never an exit report
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "ready"


@pytest.mark.asyncio
async def test_stream_loss_during_browser_isolation_repairs_stream_only(
    tmp_path,
):
    # code f006: while the Browser is policy-isolated (paused), a
    # Stream exit still gets the bounded Stream-only repair; the
    # Browser stays paused and is not reported as exited.
    adapter = _FakeAdapter(tmp_path)
    runtime = {
        "desired_state": "running",
        "runtime_instance_id": INSTANCE,
        "config_version": 1,
        "observed_state": "running",
    }
    core, session = _core_with_runtime_api(tmp_path, adapter, runtime)
    core._policy_paused[(PROFILE, INSTANCE)] = time.monotonic()
    replaced: list[str] = []

    async def _record_replace(profile_id, sess, **kwargs):
        replaced.append(profile_id)
        return True

    core._replace_stream_only = _record_replace
    roles = {
        "browser": {
            "status": "paused",
            "instance_id": INSTANCE,
            "id": "c_browser",
            "config_version": 1,
            "policy_ready": True,
        },
        "stream": {
            "status": "exited",
            "instance_id": INSTANCE,
            "id": "c_stream",
            "config_version": 1,
            "policy_ready": True,
        },
    }

    await core._reconcile_profile(PROFILE, roles)

    assert replaced == [PROFILE]
    assert "unpause:c_browser" not in adapter.calls
    assert (PROFILE, INSTANCE) in core._policy_paused
    assert core._terminal_observations == set()
