"""The one per-profile lock registry (t062).

Serializes work per profile id inside one process: the same profile is
strictly serialized, different profiles proceed in parallel. Entries
disappear once no task uses them, so the registry does not grow with
the number of profiles ever seen.

Each process owns its registry instance; a registry is an in-process
coordination device only and is never a cross-process mutex.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class ProfileLockRegistry:
    """Per-profile locks whose entries disappear once no task uses them."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def is_idle(self) -> bool:
        """Whether no profile lock is currently registered."""
        return not self._locks

    def lock_for(self, profile_id: str) -> asyncio.Lock:
        """Return the lock object for ``profile_id``, creating it on use."""
        lock = self._locks.get(profile_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[profile_id] = lock
        return lock

    def is_locked(self, profile_id: str) -> bool:
        """Whether some task currently holds ``profile_id``'s lock."""
        lock = self._locks.get(profile_id)
        return lock is not None and lock.locked()

    @asynccontextmanager
    async def lock(self, profile_id: str) -> AsyncIterator[None]:
        lock = self._locks.setdefault(profile_id, asyncio.Lock())
        try:
            async with lock:
                yield
        finally:
            if (
                self._locks.get(profile_id) is lock
                and not lock.locked()
                and not getattr(lock, "_waiters", None)
            ):
                self._locks.pop(profile_id, None)
