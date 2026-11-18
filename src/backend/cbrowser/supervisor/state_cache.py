"""Supervisor-side cache of the minimal batch state protocol (t083).

The cache is the Supervisor's only view of API intent:

- A full snapshot (keyset batches under one ``api_epoch``) is the
  alignment authority; it is refreshed at most every
  ``FULL_SYNC_INTERVAL_SEC`` seconds and whenever the epoch changes.
- Pushed ``StateChangeNotice`` messages apply incrementally between
  snapshots, fenced by the per-Profile ``state_revision``; stale or
  replayed notices are dropped, removals delete the entry.
- Snapshot fetches are single-flight with bounded backoff: a slow or
  unreachable API never multiplies into per-Profile requests, and a
  steady tick performs no HTTP at all.
- Consumers may act only while the cache is *authoritative*: a
  complete snapshot exists and the last successful contact (completed
  snapshot or applied notice) is inside the authority window.  Outside
  it, coordination pauses — the same failure posture as the former
  per-tick API errors — and readiness reports not-ready.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from cbrowser.shared.state_protocol import (
    MAX_STATE_BATCH,
    StateChangeNotice,
    StateSnapshot,
    SupervisorProfileState,
)

logger = logging.getLogger("cbrowser.supervisor.state_cache")

FULL_SYNC_INTERVAL_SEC = 30.0
AUTHORITY_WINDOW_SEC = 40.0
MAX_SYNC_BACKOFF_SEC = 30.0

FetchSnapshot = Callable[[str | None, int], Awaitable[StateSnapshot]]


def _entry_dict(state: SupervisorProfileState) -> dict[str, Any]:
    entry = state.model_dump()
    # Consumers historically read the list entry's ``id``; the minimal
    # DTO names it ``profile_id``.  Carry both keys in the cache view.
    entry["id"] = state.profile_id
    return entry


class SupervisorStateCache:
    """Epoch-fenced, revision-fenced view of minimal Profile state."""

    def __init__(
        self,
        fetch_snapshot: FetchSnapshot,
        *,
        full_sync_interval: float = FULL_SYNC_INTERVAL_SEC,
        authority_window: float = AUTHORITY_WINDOW_SEC,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch_snapshot
        self._full_sync_interval = full_sync_interval
        self._authority_window = authority_window
        self._clock = clock
        self._epoch: str | None = None
        self._entries: dict[str, dict[str, Any]] = {}
        self._complete = False
        self._last_contact: float | None = None
        self._last_full_sync: float | None = None
        self._inflight: asyncio.Task[None] | None = None
        self._failures = 0
        self._next_attempt_at = 0.0
        self._dirty: set[str] = set()
        self._resync_requested = False

    # -- reads ------------------------------------------------------

    @property
    def has_inflight(self) -> bool:
        """Whether a snapshot fetch is currently in flight."""
        return self._inflight is not None and not self._inflight.done()

    @property
    def resync_pending(self) -> bool:
        """Whether a local write invalidated the cached view."""
        return self._resync_requested

    def note_local_write(self) -> None:
        """Invalidate the view after this Supervisor's own API write.

        A successful bind/observed/event report changes the very state
        the cache mirrors; the next read must realign instead of
        trusting the pre-write entry.  The stale entries stay readable
        (never mistaken for deletions) until the resync lands.
        """
        self._resync_requested = True
        self._last_full_sync = None
        self._next_attempt_at = 0.0

    def authoritative(self, now: float | None = None) -> bool:
        """Whether consumers may act on the cached state right now."""
        if not self._complete or self._last_contact is None:
            return False
        clock = self._clock() if now is None else now
        return clock - self._last_contact <= self._authority_window

    def get(self, profile_id: str) -> dict[str, Any] | None:
        entry = self._entries.get(profile_id)
        return dict(entry) if entry is not None else None

    def entries(self) -> list[dict[str, Any]]:
        return [dict(e) for e in self._entries.values()]

    def drain_dirty(self) -> set[str]:
        dirty = self._dirty
        self._dirty = set()
        return dirty

    # -- push path ----------------------------------------------------

    def apply_notice(self, notice: StateChangeNotice) -> None:
        """Apply one pushed notice under epoch/revision fences."""
        now = self._clock()
        if self._epoch is not None and notice.api_epoch != self._epoch:
            # Another API lifetime: nothing cached may be trusted as a
            # complete view anymore; force a fresh snapshot.
            logger.warning("State notice epoch mismatch; invalidating cache")
            self._complete = False
            self._epoch = notice.api_epoch
            self._last_full_sync = None
            return
        if self._epoch is None:
            self._epoch = notice.api_epoch
        for state in notice.states:
            existing = self._entries.get(state.profile_id)
            if (
                existing is not None
                and existing["state_revision"] >= state.state_revision
            ):
                continue  # stale or replayed notice
            self._entries[state.profile_id] = _entry_dict(state)
            self._dirty.add(state.profile_id)
        for profile_id in notice.removed:
            if self._entries.pop(profile_id, None) is not None:
                self._dirty.add(profile_id)
        self._last_contact = now

    # -- snapshot path --------------------------------------------------

    async def maintain(self) -> None:
        """Drive the snapshot schedule without blocking the caller.

        Starts the single in-flight snapshot when one is due; steady
        ticks inside the interval perform no work and no HTTP.
        """
        if self._inflight is not None and not self._inflight.done():
            return
        now = self._clock()
        if (
            not self._resync_requested
            and self._complete
            and self._last_full_sync is not None
            and now - self._last_full_sync < self._full_sync_interval
        ):
            return
        if now < self._next_attempt_at:
            return
        self._inflight = asyncio.create_task(self._sync())

    async def sync_now(self) -> bool:
        """Await a full snapshot (startup/tests); True when complete."""
        if self._inflight is None or self._inflight.done():
            self._inflight = asyncio.create_task(self._sync())
        await self._inflight
        return self._complete

    async def _sync(self) -> None:
        try:
            epoch: str | None = None
            collected: dict[str, dict[str, Any]] = {}
            cursor: str | None = None
            while True:
                batch = await self._fetch(cursor, MAX_STATE_BATCH)
                if epoch is None:
                    epoch = batch.api_epoch
                elif batch.api_epoch != epoch:
                    raise ValueError("snapshot epoch changed mid-read")
                for state in batch.profiles:
                    collected[state.profile_id] = _entry_dict(state)
                cursor = batch.next_cursor
                if cursor is None:
                    break
            now = self._clock()
            self._epoch = epoch
            self._entries = collected
            self._complete = True
            self._last_contact = now
            self._last_full_sync = now
            self._failures = 0
            self._next_attempt_at = 0.0
            self._resync_requested = False
            self._dirty.update(collected.keys())
        except Exception as exc:  # noqa: BLE001 - sync failure degrades to backoff, never crashes the loop
            self._failures += 1
            backoff = min(
                MAX_SYNC_BACKOFF_SEC, 2.0 ** min(self._failures, 5)
            )
            self._next_attempt_at = self._clock() + backoff
            logger.warning(
                "State snapshot failed: error_type=%s backoff=%.0fs",
                type(exc).__name__,
                backoff,
            )
