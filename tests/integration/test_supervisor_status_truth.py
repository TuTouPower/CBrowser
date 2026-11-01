"""No local sandbox is not evidence that persisted user intent is stopped."""

from types import SimpleNamespace

import httpx
import pytest
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator

pytest_plugins = ("test_supervisor_rpc",)


@pytest.mark.asyncio
async def test_status_without_local_session_keeps_persisted_running_intent(
    supervisor_api, tmp_path
):
    server, token = supervisor_api
    profile = server.post("/api/v1/profiles", json={"name": "unbound_running"}).json()[
        "id"
    ]
    assert (
        server.patch(
            f"/api/v1/profiles/{profile}/runtime/desired-state",
            json={"desired_state": "running"},
        ).status_code
        == 200
    )
    key = tmp_path / "key"
    key.write_text(token)
    headers = {"Authorization": "Bearer " + token}
    async with httpx.AsyncClient(
        base_url=str(server.base_url), headers=headers, trust_env=False
    ) as api:
        core = SupervisorCore(
            SimpleNamespace(validator=PathValidator(tmp_path)),
            PortAllocator(),
            EventForwarder(str(api.base_url), tmp_path / "spool", client=api),
            api,
        )
        app = create_control_app(core, key)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://supervisor",
            headers=headers,
        ) as control:
            response = await control.get(f"/supervisor/v1/profiles/{profile}/status")
            assert response.status_code == 200
            assert response.json()["desired_state"] == "running"
            assert response.json()["runtime_instance_id"] is None


@pytest.mark.asyncio
async def test_status_reflects_observation_not_disk_events(supervisor_api, tmp_path):
    from cbrowser.supervisor.core import ActiveSession

    server, token = supervisor_api
    profile = server.post("/api/v1/profiles", json={"name": "exit status"}).json()["id"]
    prefix = "/api/v1/internal/supervisor"
    headers = {"Authorization": f"Bearer {token}"}
    server.patch(
        f"/api/v1/profiles/{profile}/runtime/desired-state",
        json={"desired_state": "running"},
    ).raise_for_status()
    server.post(
        prefix + "/runtimes/bind",
        params={"profile_id": profile},
        headers=headers,
        json={"runtime_instance_id": "old", "config_version": 1},
    ).raise_for_status()
    server.post(
        prefix + "/runtimes/events",
        headers=headers,
        json={
            "profile_id": profile,
            "runtime_instance_id": "old",
            "event_id": "abnormal",
            "event_type": "exit",
            "exit_code": 137,
            "exit_reason": "test_abnormal",
            "config_version": 1,
        },
    ).raise_for_status()

    # Disk events are diagnostics: they cannot terminate the bound instance.
    persisted = server.get(f"/api/v1/profiles/{profile}/runtime").json()
    assert persisted["runtime_instance_id"] == "old"
    assert persisted["desired_state"] == "running"
    assert persisted["observed_state"] == "starting"
    assert persisted["failure_count"] == 0

    server.post(
        prefix + "/runtimes/observed",
        params={"profile_id": profile},
        headers=headers,
        json={
            "runtime_instance_id": "old",
            "observed_state": "error",
            "config_version": 1,
            "reason": "process_lost",
        },
    ).raise_for_status()

    key = tmp_path / "key"
    key.write_text(token)
    async with httpx.AsyncClient(
        base_url=str(server.base_url), headers=headers, trust_env=False
    ) as api:
        core = SupervisorCore(
            SimpleNamespace(validator=PathValidator(tmp_path)),
            PortAllocator(),
            EventForwarder(str(api.base_url), tmp_path / "spool", client=api),
            api,
        )
        core._sessions[profile] = ActiveSession(
            profile, "old", 1, 30000, "b", "s", observed_state="error"
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_control_app(core, key)),
            base_url="http://supervisor",
            headers=headers,
        ) as control:
            response = await control.get(f"/supervisor/v1/profiles/{profile}/status")
            assert response.status_code == 200
            body = response.json()
            persisted = server.get(f"/api/v1/profiles/{profile}/runtime").json()
            assert persisted["runtime_instance_id"] is None
            assert persisted["desired_state"] == "running"
            assert persisted["observed_state"] == "error"
            assert persisted["failure_count"] == 1
            for field in (
                "runtime_instance_id",
                "observed_state",
                "desired_state",
                "failure_count",
            ):
                assert body[field] == persisted[field]
