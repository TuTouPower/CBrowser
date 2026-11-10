"""t049: Supervisor restore must not depend on Gateway visibility.

Drives the production ``scan_and_reconcile_existing`` /
``_recover_attachment_offline`` paths with a scripted adapter and the real
``GatewayControlClient`` wired to an ``httpx`` mock transport. The Gateway
visibility route answers a genuine 503 (Agent not registered), which is
exactly the reading that used to abort restore before any session existed.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.supervisor.address_pool import plan_for_subnet
from cbrowser.supervisor.core import ActiveSession, SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.gateway_client import GatewayControlClient
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator

pytestmark = pytest.mark.serial

PROFILE = "prof_t049"
INSTANCE = "inst_t049"
GATEWAY = "gw_t049"
PLAN = plan_for_subnet(ipaddress.ip_network("10.251.9.0/24"))
UDP_PORT = 30007


class _Container:
    def __init__(self, role: str) -> None:
        self.id = f"c_{role}"
        self.name = f"name_{role}"
        self.status = "running"
        self.labels = {"com.cbrowser.role": role}


class _RestoreAdapter:
    """Docker adapter double for the restore path only."""

    def __init__(self, root: Path) -> None:
        self.validator = PathValidator(root)
        self.conforms = True
        self.attached_gateway: str | None = None
        self.gateway_id: str | None = GATEWAY
        self.calls: list[str] = []
        self.torn_down = False
        self.client = SimpleNamespace(
            api=SimpleNamespace(inspect_container=self._inspect_container)
        )

    def _inspect_container(self, container_id: str) -> dict:
        return {
            "HostConfig": {
                "PortBindings": {
                    f"{UDP_PORT}/udp": [{"HostPort": str(UDP_PORT)}]
                }
            }
        }

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

    def start_stream_container(self, **kwargs):
        self.calls.append("start_stream")
        return SimpleNamespace(id="c_stream_new")

    def teardown_profile(self, profile_id: str) -> None:
        self.torn_down = True

    def fail_close_container(self, container) -> None:
        self.calls.append("fail_close")


def _runtime_api(runtime: dict | None = None, *, api_down: bool = False):
    def handler(request: httpx.Request) -> httpx.Response:
        if api_down:
            raise httpx.ConnectError("api offline", request=request)
        if request.url.path.endswith(
            f"/profiles/{PROFILE}/runtime"
        ):
            return httpx.Response(200, json=runtime)
        return httpx.Response(404)

    return httpx.AsyncClient(
        base_url="http://api.invalid",
        transport=httpx.MockTransport(handler),
    )


def _gateway_control(
    tmp_path: Path, *, visibility: httpx.Response | Exception, registration=None
) -> GatewayControlClient:
    token_file = tmp_path / "gateway_token"
    token_file.write_text("g" * 40, encoding="utf-8")
    token_file.chmod(0o600)
    client = GatewayControlClient("http://gateway.invalid", token_file)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/visibility"):
            if isinstance(visibility, Exception):
                raise visibility
            return visibility
        if request.url.path.endswith("/registration"):
            return httpx.Response(200, json=registration or {})
        return httpx.Response(404)

    client._client = httpx.AsyncClient(
        base_url="http://gateway.invalid",
        transport=httpx.MockTransport(handler),
    )
    return client


def _visibility_503() -> httpx.Response:
    return httpx.Response(
        503,
        json={"detail": "Agent unavailable for this instance"},
    )


def _make_core(
    tmp_path: Path,
    adapter: _RestoreAdapter,
    gateway: GatewayControlClient,
    api: httpx.AsyncClient,
) -> SupervisorCore:
    return SupervisorCore(
        adapter,
        PortAllocator(),
        EventForwarder("http://api.invalid", tmp_path / "spool", client=api),
        api,
        gateway_control=gateway,
    )


def _runtime(instance: str = INSTANCE) -> dict:
    return {
        "profile_id": PROFILE,
        "desired_state": "running",
        "observed_state": "running",
        "runtime_instance_id": instance,
        "config_version": 1,
    }


async def _scan(core: SupervisorCore) -> None:
    await core.scan_and_reconcile_existing()


@pytest.mark.asyncio
async def test_restore_ignores_gateway_visibility_503(tmp_path):
    """AC-001: no session, visibility 503 -> session and UDP port restored."""
    adapter = _RestoreAdapter(tmp_path)
    gateway = _gateway_control(tmp_path, visibility=_visibility_503())
    core = _make_core(tmp_path, adapter, gateway, _runtime_api(_runtime()))

    await _scan(core)

    session = core.get_session(PROFILE)
    assert isinstance(session, ActiveSession)
    assert session.runtime_instance_id == INSTANCE
    assert session.udp_mux_port == UDP_PORT
    assert session.browser_container_id == "c_browser"
    assert session.stream_container_id == "c_stream"


@pytest.mark.asyncio
async def test_restore_attaches_gateway_in_same_pass(tmp_path):
    """AC-002: a rebuilt Gateway is attached within the restoring pass."""
    adapter = _RestoreAdapter(tmp_path)
    gateway = _gateway_control(tmp_path, visibility=_visibility_503())
    core = _make_core(tmp_path, adapter, gateway, _runtime_api(_runtime()))

    await _scan(core)

    assert f"attach:{GATEWAY}" in adapter.calls
    assert adapter.attached_gateway == GATEWAY
    observation = core.get_transport_observation(PROFILE)
    assert observation.runtime_instance_id == INSTANCE
    assert observation.transport_state == "recovering"
    assert observation.gateway_endpoint == PLAN.gateway_endpoint
    assert observation.last_attached_at is not None


@pytest.mark.asyncio
async def test_restore_without_gateway_keeps_session(tmp_path):
    """AC-003: a missing Gateway never blocks the session restore."""
    adapter = _RestoreAdapter(tmp_path)
    adapter.gateway_id = None
    gateway = _gateway_control(
        tmp_path, visibility=httpx.ConnectError("gateway down")
    )
    core = _make_core(tmp_path, adapter, gateway, _runtime_api(_runtime()))
    core.gateway_container_id = None

    await _scan(core)

    assert core.get_session(PROFILE) is not None
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "recovering"
    assert observation.last_error == "gateway_missing"
    assert adapter.torn_down is False


@pytest.mark.asyncio
async def test_restore_with_unreachable_control_keeps_session(tmp_path):
    """AC-003: an unreachable control interface reports gateway_unreachable."""
    adapter = _RestoreAdapter(tmp_path)
    adapter.attached_gateway = GATEWAY
    gateway = _gateway_control(
        tmp_path, visibility=httpx.ConnectError("gateway down")
    )
    core = _make_core(tmp_path, adapter, gateway, _runtime_api(_runtime()))

    await _scan(core)

    assert core.get_session(PROFILE) is not None
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "recovering"
    assert observation.last_error == "gateway_unreachable"
    assert adapter.torn_down is False


@pytest.mark.asyncio
async def test_api_offline_recovery_attaches_without_session(tmp_path):
    """AC-004: API offline only re-attaches, never creates a session."""
    adapter = _RestoreAdapter(tmp_path)
    gateway = _gateway_control(tmp_path, visibility=_visibility_503())
    core = _make_core(
        tmp_path, adapter, gateway, _runtime_api(api_down=True)
    )

    await _scan(core)

    assert adapter.calls == [f"attach:{GATEWAY}"]
    assert core.get_session(PROFILE) is None
    observation = core.get_transport_observation(PROFILE)
    assert observation.runtime_instance_id == INSTANCE
    assert observation.transport_state == "recovering"


@pytest.mark.asyncio
async def test_nonconforming_media_network_replaces_stream_only(tmp_path):
    """AC-005: drift goes through Stream-only replacement, not a raw attach."""
    adapter = _RestoreAdapter(tmp_path)
    adapter.conforms = False
    gateway = _gateway_control(tmp_path, visibility=_visibility_503())
    core = _make_core(tmp_path, adapter, gateway, _runtime_api(_runtime()))
    secret_dir = adapter.validator.get_secret_dir(PROFILE)
    secret_dir.mkdir(parents=True, exist_ok=True)
    (secret_dir / "agent_secret.txt").write_text("x" * 40)

    await _scan(core)

    assert "rebuild_network" in adapter.calls
    assert "start_stream" in adapter.calls
    assert adapter.calls.index("rebuild_network") < adapter.calls.index(
        f"attach:{GATEWAY}"
    )


@pytest.mark.asyncio
async def test_label_instance_mismatch_is_not_restored(tmp_path):
    """AC-006: a label instance mismatch still blocks restoration."""
    adapter = _RestoreAdapter(tmp_path)
    browser, stream = adapter.scan_active_containers()
    stream["instance_id"] = "inst_other"
    adapter.scan_active_containers = lambda: [browser, stream]
    gateway = _gateway_control(tmp_path, visibility=_visibility_503())
    core = _make_core(tmp_path, adapter, gateway, _runtime_api(_runtime()))

    await _scan(core)

    assert core.get_session(PROFILE) is None
    assert adapter.calls == []


@pytest.mark.asyncio
async def test_api_fence_mismatch_is_not_restored(tmp_path):
    """AC-006: an API instance fence mismatch still blocks restoration."""
    adapter = _RestoreAdapter(tmp_path)
    gateway = _gateway_control(tmp_path, visibility=_visibility_503())
    core = _make_core(
        tmp_path, adapter, gateway, _runtime_api(_runtime("inst_other"))
    )

    await _scan(core)

    assert core.get_session(PROFILE) is None
    assert adapter.calls == []
