"""t083: Supervisor state cache — batching, fencing, authority.

The cache is the Supervisor's only view of API intent: full snapshots
in declared batches under one epoch, pushed notices fenced by the
per-Profile revision, single-flight fetches with bounded backoff, and
an authority window outside which consumers must pause.
"""

from __future__ import annotations

import asyncio

import pytest
from cbrowser.shared.state_protocol import (
    MAX_STATE_BATCH,
    StateChangeNotice,
    StateSnapshot,
    SupervisorProfileState,
)
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


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, sec: float) -> None:
        self.now += sec


def _fetcher(pages: dict[str | None, StateSnapshot], calls: list):
    async def fetch(cursor, limit):
        calls.append((cursor, limit))
        page = pages[cursor]
        if isinstance(page, Exception):
            raise page
        return page

    return fetch


@pytest.mark.asyncio
async def test_snapshot_batches_under_one_epoch_become_authoritative():
    clock = _Clock()
    calls: list = []
    pages = {
        None: StateSnapshot(
            api_epoch="e1",
            profiles=[_state("p1"), _state("p2")],
            next_cursor="p2",
        ),
        "p2": StateSnapshot(
            api_epoch="e1", profiles=[_state("p3")], next_cursor=None
        ),
    }
    cache = SupervisorStateCache(_fetcher(pages, calls), clock=clock)
    assert await cache.sync_now() is True
    # Two batches for three Profiles: requests grow by batch, not by N,
    # and each batch asks for exactly the declared batch size.
    assert [c[0] for c in calls] == [None, "p2"]
    assert [c[1] for c in calls] == [MAX_STATE_BATCH, MAX_STATE_BATCH]
    assert cache.authoritative()
    assert {e["profile_id"] for e in cache.entries()} == {"p1", "p2", "p3"}
    assert cache.get("p1")["id"] == "p1"


@pytest.mark.asyncio
@pytest.mark.parametrize("total", [100, 1000])
async def test_snapshot_scales_by_declared_batch(total):
    # t083_test_f004: AC-002 names 0/1/100/1000 Profiles; the fetch
    # count must follow ceil(total / MAX_STATE_BATCH), not total.
    clock = _Clock()
    calls: list = []
    profiles = [_state(f"p{i:04d}") for i in range(total)]
    index = {p.profile_id: i for i, p in enumerate(profiles)}

    async def fetch(cursor, limit):
        calls.append((cursor, limit))
        start = 0 if cursor is None else index[cursor] + 1
        page = profiles[start : start + limit]
        next_cursor = (
            page[-1].profile_id
            if start + limit < len(profiles)
            else None
        )
        return StateSnapshot(
            api_epoch="e1", profiles=page, next_cursor=next_cursor
        )

    cache = SupervisorStateCache(fetch, clock=clock)
    assert await cache.sync_now() is True
    assert cache.authoritative()
    assert len(cache.entries()) == total
    assert len(calls) == (total + MAX_STATE_BATCH - 1) // MAX_STATE_BATCH
    assert all(limit == MAX_STATE_BATCH for _, limit in calls)


@pytest.mark.asyncio
async def test_epoch_change_mid_snapshot_is_not_authoritative():
    clock = _Clock()
    calls: list = []
    pages = {
        None: StateSnapshot(
            api_epoch="e1", profiles=[_state("p1")], next_cursor="p1"
        ),
        "p1": StateSnapshot(
            api_epoch="e2", profiles=[_state("p2")], next_cursor=None
        ),
    }
    cache = SupervisorStateCache(_fetcher(pages, calls), clock=clock)
    assert await cache.sync_now() is False
    assert not cache.authoritative()
    assert cache.entries() == []


@pytest.mark.asyncio
async def test_steady_maintain_inside_interval_fetches_nothing():
    clock = _Clock()
    calls: list = []
    pages = {
        None: StateSnapshot(
            api_epoch="e1", profiles=[_state("p1")], next_cursor=None
        )
    }
    cache = SupervisorStateCache(_fetcher(pages, calls), clock=clock)
    assert await cache.sync_now() is True
    calls.clear()
    for _ in range(10):
        await cache.maintain()
        clock.advance(2.0)
    assert calls == []
    # Past the 30 s fallback interval exactly one realignment starts.
    clock.advance(11.0)
    await cache.maintain()
    assert cache.has_inflight
    assert await cache.sync_now() is True
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_concurrent_maintain_is_single_flight():
    clock = _Clock()
    calls: list = []
    started = asyncio.Event()
    release = asyncio.Event()

    async def fetch(cursor, limit):
        calls.append(cursor)
        started.set()
        await release.wait()
        return StateSnapshot(
            api_epoch="e1", profiles=[_state("p1")], next_cursor=None
        )

    cache = SupervisorStateCache(fetch, clock=clock)
    await cache.maintain()
    await cache.maintain()
    await cache.maintain()
    await started.wait()
    assert calls == [None]
    release.set()
    assert await cache.sync_now() is True
    assert calls == [None]


@pytest.mark.asyncio
async def test_failed_snapshot_backs_off_and_never_authoritative():
    clock = _Clock()
    calls: list = []
    pages = {None: RuntimeError("api down")}
    cache = SupervisorStateCache(_fetcher(pages, calls), clock=clock)
    assert await cache.sync_now() is False
    assert not cache.authoritative()
    calls.clear()
    await cache.maintain()  # inside backoff: no new attempt
    assert calls == []
    # First failure backs off 2 s: +1 s is still inside the backoff,
    # +3 s is past it — the boundary itself is pinned, not just a
    # far-future retry.
    clock.advance(1.0)
    await cache.maintain()
    assert calls == []
    clock.advance(2.0)
    await cache.maintain()
    assert cache.has_inflight


@pytest.mark.asyncio
async def test_notice_fencing_by_revision_and_removal():
    clock = _Clock()
    calls: list = []
    pages = {
        None: StateSnapshot(
            api_epoch="e1",
            profiles=[_state("p1", revision=3)],
            next_cursor=None,
        )
    }
    cache = SupervisorStateCache(_fetcher(pages, calls), clock=clock)
    assert await cache.sync_now() is True

    # Stale replay (revision 2 < 3) is dropped.
    cache.apply_notice(
        StateChangeNotice(
            api_epoch="e1",
            states=[_state("p1", revision=2, desired_state="stopped")],
        )
    )
    assert cache.get("p1")["desired_state"] == "running"

    # Newer revision applies and marks the Profile dirty.
    cache.apply_notice(
        StateChangeNotice(
            api_epoch="e1",
            states=[_state("p1", revision=4, desired_state="stopped")],
        )
    )
    assert cache.get("p1")["desired_state"] == "stopped"
    assert cache.drain_dirty() == {"p1"}

    # Equal-revision replay (same revision, different desired_state)
    # is dropped too and must not re-mark the Profile dirty: this is
    # AC-007's literal "duplicate/replayed notice" case.
    cache.apply_notice(
        StateChangeNotice(
            api_epoch="e1",
            states=[_state("p1", revision=4, desired_state="running")],
        )
    )
    assert cache.get("p1")["desired_state"] == "stopped"
    assert cache.drain_dirty() == set()

    # Removal deletes the entry.
    cache.apply_notice(StateChangeNotice(api_epoch="e1", removed=["p1"]))
    assert cache.get("p1") is None


@pytest.mark.asyncio
async def test_notice_from_another_epoch_invalidates_completeness():
    clock = _Clock()
    calls: list = []
    pages = {
        None: StateSnapshot(
            api_epoch="e1", profiles=[_state("p1")], next_cursor=None
        )
    }
    cache = SupervisorStateCache(_fetcher(pages, calls), clock=clock)
    assert await cache.sync_now() is True
    assert cache.authoritative()
    cache.apply_notice(
        StateChangeNotice(api_epoch="e2", states=[_state("p1", revision=9)])
    )
    assert not cache.authoritative()


@pytest.mark.asyncio
async def test_authority_window_expires_without_contact():
    clock = _Clock()
    calls: list = []
    pages = {
        None: StateSnapshot(
            api_epoch="e1", profiles=[_state("p1")], next_cursor=None
        )
    }
    cache = SupervisorStateCache(
        _fetcher(pages, calls), clock=clock, authority_window=40.0
    )
    assert await cache.sync_now() is True
    clock.advance(41.0)
    assert not cache.authoritative()
    # A notice is contact too: it re-arms the window.
    cache.apply_notice(
        StateChangeNotice(
            api_epoch="e1", states=[_state("p1", revision=2)]
        )
    )
    assert cache.authoritative()


@pytest.mark.asyncio
async def test_local_write_forces_resync_on_next_maintain():
    clock = _Clock()
    calls: list = []
    pages = {
        None: StateSnapshot(
            api_epoch="e1", profiles=[_state("p1")], next_cursor=None
        )
    }
    cache = SupervisorStateCache(_fetcher(pages, calls), clock=clock)
    assert await cache.sync_now() is True
    calls.clear()
    cache.note_local_write()
    assert cache.resync_pending
    await cache.maintain()
    assert cache.has_inflight
    assert await cache.sync_now() is True
    assert len(calls) == 1
    assert not cache.resync_pending
