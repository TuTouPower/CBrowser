"""A persisted manual retry supersedes a sleeping automatic retry."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.recovery_coordinator import RecoveryCoordinator
from test_supervisor_rpc import supervisor_api as supervisor_api


@pytest.mark.asyncio
async def test_manual_reset_preempts_old_backoff_over_real_api(
    supervisor_api, tmp_path
):
    server, token = supervisor_api
    profile = server.post("/api/v1/profiles", json={"name": "manual retry"}).json()[
        "id"
    ]
    prefix = "/api/v1/internal/supervisor"
    headers = {"Authorization": "Bearer " + token}
    server.patch(
        f"/api/v1/profiles/{profile}/runtime/desired-state",
        json={"desired_state": "running"},
    ).raise_for_status()
    for number in range(3):
        instance = f"i{number}"
        server.post(
            prefix + "/runtimes/bind",
            params={"profile_id": profile},
            headers=headers,
            json={"runtime_instance_id": instance, "config_version": 1},
        ).raise_for_status()
        server.post(
            prefix + "/runtimes/events",
            headers=headers,
            json={
                "profile_id": profile,
                "runtime_instance_id": instance,
                "event_id": f"exit{number}",
                "event_type": "exit",
                "exit_code": 137,
                "exit_reason": "test_abnormal",
                "config_version": 1,
            },
        ).raise_for_status()
    started = asyncio.Event()

    async def start_profile(**kwargs):
        assert kwargs["profile_id"] == profile
        started.set()

    async with httpx.AsyncClient(
        base_url=str(server.base_url), headers=headers, trust_env=False
    ) as api:
        locks = {}
        core = SimpleNamespace(
            _get_profile_lock=lambda pid: locks.setdefault(pid, asyncio.Lock()),
            has_native_exit=lambda *_: False,
            api=api,
            _auth_headers=lambda: headers,
            docker=SimpleNamespace(
                validator=PathValidator(tmp_path), scan_active_containers=lambda: []
            ),
            start_profile=start_profile,
        )
        recovery = RecoveryCoordinator(core)
        try:
            await recovery.tick()
            old = recovery._in_flight_tasks[profile]
            await asyncio.sleep(0.05)
            assert not old.done()
            reset = server.patch(
                prefix + f"/profiles/{profile}/runtime/desired-state",
                headers={**headers, "Idempotency-Key": "manual_during_backoff"},
                json={"desired_state": "running"},
            )
            reset.raise_for_status()
            assert reset.json()["failure_count"] == 0
            await recovery.tick()
            await asyncio.wait_for(started.wait(), 1.5)
            assert old.cancelled()
        finally:
            await recovery.close()


@pytest.mark.asyncio
async def test_replayed_manual_operation_cannot_bypass_new_block(
    supervisor_api, tmp_path
):
    import secrets

    from cbrowser.domain.models import ProfileConfig
    from cbrowser.supervisor.core import SupervisorCore
    from cbrowser.supervisor.event_forwarder import EventForwarder
    from cbrowser.supervisor.port_allocator import PortAllocator

    server, token = supervisor_api
    profile = server.post("/api/v1/profiles", json={"name": "replay block"}).json()[
        "id"
    ]
    prefix = "/api/v1/internal/supervisor"
    headers = {"Authorization": "Bearer " + token}
    desired = prefix + f"/profiles/{profile}/runtime/desired-state"
    server.patch(
        desired,
        headers={**headers, "Idempotency-Key": "old_manual"},
        json={"desired_state": "running"},
    ).raise_for_status()
    for number in range(4):
        instance = f"failed{number}"
        server.post(
            prefix + "/runtimes/bind",
            params={"profile_id": profile},
            headers=headers,
            json={"runtime_instance_id": instance, "config_version": 1},
        ).raise_for_status()
        server.post(
            prefix + "/runtimes/events",
            headers=headers,
            json={
                "profile_id": profile,
                "runtime_instance_id": instance,
                "event_id": f"exit{number}",
                "event_type": "exit",
                "exit_code": 137,
                "exit_reason": "test_abnormal",
                "config_version": 1,
            },
        ).raise_for_status()
    key = tmp_path / "agent_key"
    key.write_text(secrets.token_urlsafe(32))
    ports = PortAllocator()
    async with httpx.AsyncClient(
        base_url=str(server.base_url), headers=headers, trust_env=False
    ) as api:
        core = SupervisorCore(
            SimpleNamespace(validator=PathValidator(tmp_path)),
            ports,
            EventForwarder(str(api.base_url), tmp_path / "spool", client=api),
            api,
            agent_key_file=key,
        )
        with pytest.raises(RuntimeError, match="Automatic retries exhausted"):
            await core.start_profile(
                profile,
                ProfileConfig(name="replay block"),
                force=True,
                operation_id="old_manual",
            )
        persisted = server.get(f"/api/v1/profiles/{profile}/runtime").json()
        assert persisted["restart_blocked"] is True
        assert persisted["failure_count"] == 4
        assert persisted["runtime_instance_id"] is None
        assert ports.get_port(profile) is None
