"""t062 AC-006: the shared rules behave identically at every consumer.

- The per-profile lock registry serializes one profile, parallelizes
  different profiles, and cleans up after itself.
- The instance fence drops values stamped by another instance.
- Deploy-side origin derivation goes through the one request-side
  normalization, so whitelist entries compare equal by construction.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from cbrowser.network_config import derive_origin_whitelist
from cbrowser.shared.endpoints import normalize_origin
from cbrowser.shared.fencing import fence_by_instance
from cbrowser.shared.profile_locks import ProfileLockRegistry


@pytest.mark.asyncio
async def test_lock_registry_serializes_same_profile() -> None:
    registry = ProfileLockRegistry()
    order: list[str] = []

    async def worker(tag: str) -> None:
        async with registry.lock("p1"):
            order.append(f"enter-{tag}")
            await asyncio.sleep(0.02)
            order.append(f"exit-{tag}")

    await asyncio.gather(worker("a"), worker("b"))
    assert order in (
        ["enter-a", "exit-a", "enter-b", "exit-b"],
        ["enter-b", "exit-b", "enter-a", "exit-a"],
    )
    assert registry.is_idle


@pytest.mark.asyncio
async def test_lock_registry_parallelizes_different_profiles() -> None:
    registry = ProfileLockRegistry()
    release = asyncio.Event()
    entered: list[str] = []

    async def worker(profile_id: str) -> None:
        async with registry.lock(profile_id):
            entered.append(profile_id)
            if len(entered) == 2:
                release.set()
            await asyncio.wait_for(release.wait(), timeout=5)

    # Both critical sections must be live at once; a serialized pair
    # would deadlock into the timeout instead.
    await asyncio.gather(worker("p1"), worker("p2"))
    assert sorted(entered) == ["p1", "p2"]
    assert registry.is_idle


@pytest.mark.asyncio
async def test_lock_registry_probe_reflects_holders() -> None:
    registry = ProfileLockRegistry()
    assert not registry.is_locked("p1")
    async with registry.lock("p1"):
        assert registry.is_locked("p1")
        assert registry.lock_for("p1").locked()
    assert not registry.is_locked("p1")
    assert registry.is_idle


@dataclass
class _Stamped:
    runtime_instance_id: str | None
    payload: str


def test_fence_by_instance() -> None:
    current = _Stamped("inst-2", "current")
    stale = _Stamped("inst-1", "stale")
    unstamped = _Stamped(None, "unstamped")
    assert fence_by_instance(current, "inst-2") is current
    assert fence_by_instance(stale, "inst-2") is None
    assert fence_by_instance(unstamped, "inst-2") is None
    assert fence_by_instance(unstamped, None) is unstamped
    assert fence_by_instance(None, "inst-2") is None


def test_origin_whitelist_uses_the_one_normalization() -> None:
    assert derive_origin_whitelist(443) == [
        normalize_origin("https://127.0.0.1:443"),
        normalize_origin("https://localhost:443"),
    ]
    assert derive_origin_whitelist(443) == [
        "https://127.0.0.1",
        "https://localhost",
    ]
    assert derive_origin_whitelist(56661) == [
        "https://127.0.0.1:56661",
        "https://localhost:56661",
    ]
