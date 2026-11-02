"""A bound launch that exhausts capacity must not leave a phantom instance."""

import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from cbrowser.domain.models import ProfileConfig
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator, PortPoolExhaustedError
from test_supervisor_rpc import supervisor_api as supervisor_api  # noqa: PLC0414


@pytest.mark.asyncio
async def test_exhausted_port_after_binding_records_one_start_failure(
    supervisor_api, tmp_path
):
    server, token = supervisor_api
    profile = server.post("/api/v1/profiles", json={"name": "capacity"}).json()["id"]
    server.patch(
        f"/api/v1/profiles/{profile}/runtime/desired-state",
        json={"desired_state": "running"},
    ).raise_for_status()
    dirs = {}
    for key in ("runtime", "profile", "events", "exchange", "x11", "pulse"):
        dirs[key] = tmp_path / key
        dirs[key].mkdir(exist_ok=True)
    adapter = SimpleNamespace(
        validator=PathValidator(tmp_path),
        prepare_profile_directories=lambda _: dirs,
        teardown_profile=AsyncMock(),
    )
    key_file = tmp_path / "agent_key"
    key_file.write_text(secrets.token_urlsafe(32))
    ports = PortAllocator(30000, 30000)
    await ports.allocate("other_profile")
    async with httpx.AsyncClient(
        base_url=str(server.base_url),
        headers={"Authorization": "Bearer " + token},
        trust_env=False,
    ) as api:
        events = EventForwarder(str(api.base_url), tmp_path / "spool", client=api)
        core = SupervisorCore(
            adapter,
            ports,
            events,
            api,
            agent_key_file=key_file,
            coturn_container_id="coturn_test_id",
        )
        with pytest.raises(PortPoolExhaustedError):
            await core.start_profile(profile, ProfileConfig(name="capacity"))
        runtime = server.get(f"/api/v1/profiles/{profile}/runtime").json()
        assert runtime["runtime_instance_id"] is None
        assert runtime["failure_count"] == 1
        assert runtime["desired_state"] == "running"
        assert ports.is_port_used(30000)
        assert not list((tmp_path / "spool").glob("*.json"))
