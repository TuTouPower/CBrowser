"""Core-level lifecycle conflict producers (t022 A11 / AC-005).

The control-server tests prove the HTTP mapping; these prove the three
production raise sites in SupervisorCore.start_profile actually raise the
typed LifecycleConflictError (not a generic RuntimeError).
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from cbrowser.domain.models import ProfileConfig
from cbrowser.supervisor.core import (
    ActiveSession,
    LifecycleConflictError,
    SupervisorCore,
)
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator


def _core(tmp_path, runtime_payload: dict) -> SupervisorCore:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=runtime_payload)

    api = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://api",
        trust_env=False,
    )
    core = SupervisorCore(
        SimpleNamespace(validator=PathValidator(tmp_path)),
        PortAllocator(),
        EventForwarder("http://127.0.0.1:1", tmp_path / "spool", client=api),
        api,
    )
    core.agent_credentials = object()  # presence is all start_profile checks
    return core


def _runtime(**overrides) -> dict:
    payload = {
        "profile_id": "profile",
        "desired_state": "running",
        "observed_state": "stopped",
        "runtime_instance_id": None,
        "config_version": 1,
        "failure_count": 0,
        "restart_blocked": False,
        "last_exit_event_id": None,
        "updated_at": "2026-11-04T00:00:00+00:00",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_unfinished_cleanup_blocks_new_start(tmp_path) -> None:
    core = _core(tmp_path, _runtime())
    core._sessions["profile"] = ActiveSession(
        "profile", "inst_old", 1, 30000, "browser", "stream",
        observed_state="stopping",
    )
    with pytest.raises(LifecycleConflictError):
        await core.start_profile(
            profile_id="profile", config=ProfileConfig(name="P"), config_version=1
        )


@pytest.mark.asyncio
async def test_missing_running_intent_is_a_conflict(tmp_path) -> None:
    core = _core(tmp_path, _runtime(desired_state="stopped"))
    with pytest.raises(LifecycleConflictError):
        await core.start_profile(
            profile_id="profile", config=ProfileConfig(name="P"), config_version=1
        )


@pytest.mark.asyncio
async def test_restart_blocked_is_a_conflict(tmp_path) -> None:
    core = _core(tmp_path, _runtime(restart_blocked=True, failure_count=4))
    with pytest.raises(LifecycleConflictError):
        await core.start_profile(
            profile_id="profile", config=ProfileConfig(name="P"), config_version=1
        )
