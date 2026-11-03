"""Supervisor core search-defaults fencing and UDS outcome mapping (A55)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.runtime_agent.protocol import HealthResponse, SearchDefaultsStatus
from cbrowser.supervisor.core import (
    ActiveSession,
    LifecycleConflictError,
    RuntimeUnavailableError,
    SupervisorCore,
)
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator


def _core(tmp_path, *, session: bool = True) -> SupervisorCore:
    api = httpx.AsyncClient(base_url="http://127.0.0.1:1", trust_env=False)
    core = SupervisorCore(
        SimpleNamespace(validator=PathValidator(tmp_path)),
        PortAllocator(),
        EventForwarder("http://127.0.0.1:1", tmp_path / "spool", client=api),
        api,
    )
    if session:
        core._sessions["profile"] = ActiveSession(
            "profile", "inst_1", 1, 30000, "browser", "stream"
        )
    return core


def _status(instance: str = "inst_1") -> SearchDefaultsStatus:
    return SearchDefaultsStatus(
        state="failed",
        error_kind="timeout",
        runtime_instance_id=instance,
        request_id=None,
        updated_at="2026-11-04T00:00:00+00:00",
    )


def _health(instance: str = "inst_1", status_instance: str = "inst_1") -> HealthResponse:
    return HealthResponse(
        status="ok",
        ready=True,
        display_ready=True,
        browser_ready=True,
        audio_ready=True,
        cdp_ready=True,
        profile_id="profile",
        runtime_instance_id=instance,
        config_version=1,
        search_defaults=_status(status_instance),
    )


@pytest.mark.asyncio
async def test_get_search_defaults_fences_status_instance(tmp_path) -> None:
    """The supervisor only surfaces a status whose own instance matches
    the live session (t022_code_f009)."""
    core = _core(tmp_path)

    async def matching(_profile_id: str):
        return _health()

    core._query_agent_health = matching  # type: ignore[method-assign]
    instance, status = await core.get_search_defaults("profile")
    assert instance == "inst_1" and status is not None

    async def mismatched_status(_profile_id: str):
        return _health(status_instance="inst_other")

    core._query_agent_health = mismatched_status  # type: ignore[method-assign]
    instance, status = await core.get_search_defaults("profile")
    assert instance == "inst_1" and status is None


@pytest.mark.asyncio
async def test_retry_maps_agent_outcomes(tmp_path) -> None:
    core = _core(tmp_path)

    def client_returning(status_code: int):
        @asynccontextmanager
        async def factory(_profile_id: str):
            async def post(_url: str, json=None):  # noqa: ARG001 - stub transport
                return SimpleNamespace(status_code=status_code)

            yield SimpleNamespace(post=post)

        return factory

    core._agent_uds_client = client_returning(200)  # type: ignore[method-assign]
    await core.retry_search_defaults("profile", "inst_1", "req-1")

    core._agent_uds_client = client_returning(403)  # type: ignore[method-assign]
    with pytest.raises(LifecycleConflictError):
        await core.retry_search_defaults("profile", "inst_1", "req-1")

    core._agent_uds_client = client_returning(503)  # type: ignore[method-assign]
    with pytest.raises(RuntimeUnavailableError):
        await core.retry_search_defaults("profile", "inst_1", "req-1")


@pytest.mark.asyncio
async def test_retry_fences_before_any_uds_call(tmp_path) -> None:
    core = _core(tmp_path)
    with pytest.raises(LifecycleConflictError):
        await core.retry_search_defaults("profile", "inst_stale", "req-1")

    core_no_session = _core(tmp_path, session=False)
    with pytest.raises(RuntimeUnavailableError):
        await core_no_session.retry_search_defaults("profile", "inst_1", "req-1")
