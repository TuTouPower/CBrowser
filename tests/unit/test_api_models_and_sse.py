"""Unit tests for API runtime models and the in-memory SSE broadcaster."""

import pytest
from cbrowser.api.runtime_coordinator import RuntimeEventBroadcaster
from cbrowser.domain.models import (
    ProfileRuntimeResponse,
    ProfileRuntimeStatusEvent,
)


def test_profile_runtime_response_last_coordinator_error():
    rt = ProfileRuntimeResponse(
        profile_id="p1",
        desired_state="running",
        observed_state="starting",
        runtime_instance_id="inst_1",
        config_version=1,
        failure_count=0,
        restart_blocked=False,
        last_exit_event_id=None,
        updated_at="2026-10-31T00:00:00Z",
        last_coordinator_error="Supervisor unreachable",
    )
    assert rt.last_coordinator_error == "Supervisor unreachable"

    rt_default = ProfileRuntimeResponse(
        profile_id="p1",
        desired_state="stopped",
        observed_state="stopped",
        runtime_instance_id=None,
        config_version=1,
        failure_count=0,
        restart_blocked=False,
        last_exit_event_id=None,
        updated_at="2026-10-31T00:00:00Z",
    )
    assert rt_default.last_coordinator_error is None


@pytest.mark.asyncio
async def test_sse_broadcaster_initial_snapshot():
    broadcaster = RuntimeEventBroadcaster(maxlen=10)

    async def snapshot_provider():
        return [
            ProfileRuntimeStatusEvent(
                profile_id="p_snap",
                desired_state="stopped",
                observed_state="stopped",
                updated_at="2026-10-31T00:00:00Z",
            )
        ]

    gen = broadcaster.subscribe(initial_snapshot_provider=snapshot_provider)
    first_chunk = await gen.__anext__()

    assert "event: runtime_state" in first_chunk
    assert "p_snap" in first_chunk


def test_profile_runtime_status_event_exposes_font_set_state():
    """t041 AC-007: the runtime status event reports the bound font set and
    the detection fonts missing from it, defaulting to the unconfigured state."""
    unconfigured = ProfileRuntimeStatusEvent(
        profile_id="p1",
        desired_state="running",
        observed_state="stopped",
        runtime_instance_id=None,
        failure_count=1,
        restart_blocked=False,
        last_coordinator_error="Connection refused",
        updated_at="2026-10-31T00:00:00Z",
    )
    assert unconfigured.model_dump() == {
        "profile_id": "p1",
        "desired_state": "running",
        "observed_state": "stopped",
        "runtime_instance_id": None,
        "failure_count": 1,
        "restart_blocked": False,
        "last_started_at": None,
        "last_stopped_at": None,
        "browser_product": None,
        "browser_user_agent": None,
        "font_set_id": None,
        "missing_fonts": [],
        "last_coordinator_error": "Connection refused",
        "search_defaults": None,
        "transport": None,
        "control": None,
        "updated_at": "2026-10-31T00:00:00Z",
    }
    assert unconfigured.model_dump()["font_set_id"] is None
    assert unconfigured.model_dump()["missing_fonts"] == []

    bound = ProfileRuntimeStatusEvent(
        profile_id="p1",
        desired_state="running",
        observed_state="running",
        updated_at="2026-10-31T00:00:00Z",
        font_set_id="a" * 64,
        missing_fonts=["arial.ttf"],
    )
    assert bound.model_dump()["font_set_id"] == "a" * 64
    assert bound.model_dump()["missing_fonts"] == ["arial.ttf"]
