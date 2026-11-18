"""t083: pushed state notices reach the Supervisor and wake a scan.

Two halves of the AC-003 push path: the control endpoint accepts an
authenticated notice (401 without a token) and marks the Profile
dirty in the state cache, and the monitor loop's scan-due decision
treats a drained dirty set as an immediate scan instead of waiting
for the 30 s fallback.
"""

from __future__ import annotations

import asyncio
import secrets
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.shared.state_protocol import (
    StateChangeNotice,
    SupervisorProfileState,
)
from cbrowser.supervisor import runner as runner_module
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.state_cache import SupervisorStateCache


def _state(pid: str, revision: int = 1, **overrides) -> SupervisorProfileState:
    data = {
        "profile_id": pid,
        "display_number": 1,
        "desired_state": "running",
        "observed_state": "running",
        "runtime_instance_id": f"inst_{pid}",
        "config_version": 1,
        "failure_count": 0,
        "restart_blocked": False,
        "last_exit_event_id": None,
        "backoff_started_at": None,
        "next_retry_at": None,
        "updated_at": "2026-01-01T00:00:00Z",
        "state_revision": revision,
    }
    data.update(overrides)
    return SupervisorProfileState(**data)


@pytest.mark.asyncio
async def test_state_changes_endpoint_auth_and_marks_dirty(tmp_path):
    token = secrets.token_urlsafe(32)
    key = tmp_path / "key"
    key.write_text(token)
    key.chmod(0o600)

    async def _never_fetch(cursor, limit):
        raise AssertionError("applying a notice must not fetch")

    cache = SupervisorStateCache(_never_fetch)
    core = SimpleNamespace(state_cache=cache, _sessions={})
    app = create_control_app(core, key)
    notice = StateChangeNotice(
        api_epoch="e1", states=[_state("p1", revision=2)]
    ).model_dump(mode="json")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://supervisor"
    ) as client:
        denied = await client.post(
            "/supervisor/v1/state-changes", json=notice
        )
        assert denied.status_code == 401
        assert cache.drain_dirty() == set()
        accepted = await client.post(
            "/supervisor/v1/state-changes",
            json=notice,
            headers={"Authorization": "Bearer " + token},
        )
        assert accepted.status_code == 200
        assert accepted.json() == {"status": "ok"}
    assert cache.drain_dirty() == {"p1"}


def test_dirty_set_wakes_scan_without_waiting_for_fallback():
    async def _never_fetch(cursor, limit):
        raise AssertionError("the scan-due decision must not fetch")

    cache = SupervisorStateCache(_never_fetch)
    wakeup = asyncio.Event()
    # No dirty Profiles and a recent scan: no scan is due.
    assert (
        runner_module._scan_due(cache, wakeup, last_scan=1000.0, now=1001.0)
        is False
    )
    assert not wakeup.is_set()
    # A pushed notice marks the Profile dirty: the next loop tick
    # owes a scan immediately, and the wakeup stays set for it.
    cache.apply_notice(
        StateChangeNotice(api_epoch="e1", states=[_state("p1")])
    )
    assert (
        runner_module._scan_due(cache, wakeup, last_scan=1000.0, now=1001.0)
        is True
    )
    assert wakeup.is_set()
    # With the dirty set drained and no wakeup, only the 30 s
    # fallback schedules a scan.
    wakeup.clear()
    assert (
        runner_module._scan_due(cache, wakeup, last_scan=1000.0, now=1029.0)
        is False
    )
    assert (
        runner_module._scan_due(cache, wakeup, last_scan=1000.0, now=1030.0)
        is True
    )
