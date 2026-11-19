"""t091: preserve registration recovery grace across live Gateway restarts."""

from __future__ import annotations

import ipaddress
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.supervisor.address_pool import plan_for_subnet
from cbrowser.supervisor.core import (
    ActiveSession,
    RegistrationState,
    SupervisorCore,
)
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator

PROFILE = "prof_t091"
INSTANCE = "inst_t091"
PLAN = plan_for_subnet(ipaddress.ip_network("10.251.9.0/24"))


class _Container:
    def __init__(self, role: str) -> None:
        self.id = f"c_{role}"
        self.name = f"name_{role}"
        self.status = "running"
        self.labels = {"com.cbrowser.role": role}


class _Adapter:
    def __init__(self, root: Path) -> None:
        self.validator = PathValidator(root)
        self.plan = PLAN
        self.attached_gateway: str | None = "gw_1"
        self.gateway_id: str | None = "gw_1"
        self.calls: list[str] = []

    def inspect_media_network(self, profile_id: str) -> dict:
        return {
            "exists": True,
            "conforms": True,
            "plan": self.plan,
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
        return True

    def attach_profile_infrastructure(self, profile_id, gateway_id, gateway_port=None):
        self.calls.append(f"attach:{gateway_id}")
        self.attached_gateway = gateway_id
        return {
            "gateway_ip": self.plan.gateway_endpoint,
            "gateway_url": f"ws://{self.plan.gateway_endpoint}:8443",
            "browser_ip": "10.251.9.2",
        }

    async def start_stream_container(self, **kwargs):
        self.calls.append("start_stream")
        return SimpleNamespace(id="c_stream_new")

    def cleanup_container_by_name(self, name: str) -> None:
        self.calls.append(f"cleanup_container:{name}")

    def scan_active_containers(self) -> list:
        return []


class _GatewayControl:
    def __init__(self) -> None:
        self.registered: bool | None = True

    async def agent_registered(self, profile_id: str, instance_id: str):
        return self.registered

    async def registration_status(self, profile_id: str):
        return {
            "profile_id": profile_id,
            "gateway_build_id": "gw-build-1",
            "agent_build_id": "agent-build-1",
            "selkies_version": "2.2.1",
            "rejection": None,
            "rejection_runtime_instance_id": None,
        }


def _make_core(tmp_path: Path):
    adapter = _Adapter(tmp_path)
    secret_dir = adapter.validator.get_secret_dir(PROFILE)
    secret_dir.mkdir(parents=True, exist_ok=True)
    (secret_dir / "agent_secret.txt").write_text("x" * 40, encoding="utf-8")
    runtime_dir = adapter.validator.get_runtime_dir(PROFILE)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "snapshot.json").write_text("{}", encoding="utf-8")

    gateway = _GatewayControl()
    api = httpx.AsyncClient(
        base_url="http://api.invalid",
        transport=httpx.MockTransport(lambda r: httpx.Response(404)),
    )
    core = SupervisorCore(
        adapter,
        PortAllocator(),
        EventForwarder("http://api.invalid", tmp_path / "spool", client=api),
        api,
        gateway_control=gateway,
        gateway_container_id="gw_stale",
    )
    session = ActiveSession(
        PROFILE,
        INSTANCE,
        1,
        30005,
        "c_browser",
        "c_stream",
        desired_state="running",
        observed_state="running",
    )
    core._sessions[PROFILE] = session
    scan = {
        "browser": {"status": "running", "instance_id": INSTANCE},
        "stream": {"status": "running", "instance_id": INSTANCE},
    }
    return core, session, scan, adapter, gateway


@pytest.mark.asyncio
async def test_known_registration_survives_gateway_unreachable_and_enters_recovery_grace(
    tmp_path: Path,
) -> None:
    core, session, scan, adapter, gateway = _make_core(tmp_path)

    gateway.registered = True
    await core._converge_session(PROFILE, session, scan)
    assert core._registration[PROFILE].known is True

    # Gateway dies / restarts -> control RPC unreachable across two passes.
    gateway.registered = None
    await core._converge_session(PROFILE, session, scan)
    await core._converge_session(PROFILE, session, scan)
    assert core.get_transport_observation(PROFILE).last_error == "gateway_unreachable"
    assert "start_stream" not in adapter.calls

    # Gateway is back up; StreamAgent is still sleeping in reconnect backoff.
    gateway.registered = False
    await core._converge_session(PROFILE, session, scan)
    assert "start_stream" not in adapter.calls
    assert core.get_transport_observation(PROFILE).last_error == "registration_recovery_grace"

    # Once grace expires with no registration, Stream-only replacement runs.
    core._registration[PROFILE].lost_at = (
        time.monotonic() - SupervisorCore._REGISTRATION_LOSS_GRACE_SEC - 1.0
    )
    await core._converge_session(PROFILE, session, scan)
    assert "start_stream" in adapter.calls


@pytest.mark.asyncio
async def test_known_registration_survives_gateway_missing_and_enters_recovery_grace(
    tmp_path: Path,
) -> None:
    core, session, scan, adapter, gateway = _make_core(tmp_path)

    gateway.registered = True
    await core._converge_session(PROFILE, session, scan)
    assert core._registration[PROFILE].known is True

    # Gateway container missing during restart -> must retain recovery eligibility.
    adapter.gateway_id = None
    core.gateway_container_id = None
    await core._converge_session(PROFILE, session, scan)
    assert core.get_transport_observation(PROFILE).last_error == "gateway_missing"
    assert "start_stream" not in adapter.calls

    # Gateway container recreated under a new ID; StreamAgent hasn't reconnected yet.
    adapter.gateway_id = "gw_2"
    gateway.registered = False
    await core._converge_session(PROFILE, session, scan)
    assert "attach:gw_2" in adapter.calls
    assert "start_stream" not in adapter.calls
    assert core.get_transport_observation(PROFILE).last_error == "registration_recovery_grace"

    # Re-registering within grace settles back to ready without replacement.
    gateway.registered = True
    await core._converge_session(PROFILE, session, scan)
    assert core._registration[PROFILE].known is True
    assert core.get_transport_observation(PROFILE).transport_state == "ready"
    assert "start_stream" not in adapter.calls


@pytest.mark.asyncio
async def test_unconfirmed_registration_cleared_at_gateway_outage_boundaries(
    tmp_path: Path,
) -> None:
    core, session, scan, adapter, gateway = _make_core(tmp_path)

    # Known -> lost (unconfirmed) keeps one RegistrationState object, then
    # gateway_missing clears the unconfirmed grace entry.
    gateway.registered = True
    await core._converge_session(PROFILE, session, scan)
    state = core._registration[PROFILE]
    assert isinstance(state, RegistrationState)
    assert state.known is True
    gateway.registered = False
    await core._converge_session(PROFILE, session, scan)
    assert core._registration[PROFILE] is state
    assert state.known is False
    assert state.lost_at is not None

    adapter.gateway_id = None
    core.gateway_container_id = None
    await core._converge_session(PROFILE, session, scan)
    assert PROFILE not in core._registration

    # Same cleanup holds for gateway_unreachable after registration was already lost.
    adapter.gateway_id = "gw_1"
    core.gateway_container_id = "gw_stale"
    gateway.registered = True
    await core._converge_session(PROFILE, session, scan)
    gateway.registered = False
    await core._converge_session(PROFILE, session, scan)
    assert core._registration[PROFILE].known is False
    gateway.registered = None
    await core._converge_session(PROFILE, session, scan)
    assert PROFILE not in core._registration
