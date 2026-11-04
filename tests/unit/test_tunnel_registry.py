"""t031 tunnel registry: register, close, generation fence."""

from __future__ import annotations

import pytest
from cbrowser.services.tunnel_registry import AutomationTunnelRegistry


@pytest.mark.asyncio
async def test_register_list_and_unregister():
    registry = AutomationTunnelRegistry(layer="api")
    closed: list[str] = []

    async def close_fn():
        closed.append("x")

    record = registry.register(
        "p1", close_fn, generation=3, agent_instance_id="tok-1"
    )
    assert registry.list_for_profile("p1") == [record]
    assert registry.list_for_profile("p2") == []
    assert record.to_data()["generation"] == 3
    registry.unregister(record.tunnel_id)
    assert registry.list_for_profile("p1") == []
    assert closed == []


@pytest.mark.asyncio
async def test_close_all_advances_fence_and_closes():
    registry = AutomationTunnelRegistry(layer="supervisor")
    closed: list[str] = []

    async def make_close(name: str):
        async def close_fn():
            closed.append(name)

        return close_fn

    registry.register("p1", await make_close("a"), generation=4)
    registry.register("p1", await make_close("b"), generation=4)
    registry.register("p2", await make_close("c"), generation=4)
    closed_ids = await registry.close_all_for_profile("p1", generation=5)
    assert sorted(closed) == ["a", "b"]
    assert len(closed_ids) == 2
    assert registry.list_for_profile("p1") == []
    assert len(registry.list_for_profile("p2")) == 1
    # Fence: generations at or below 5 are stale for p1.
    assert registry.is_generation_fenced("p1", 5) is True
    assert registry.is_generation_fenced("p1", 4) is True
    assert registry.is_generation_fenced("p1", 6) is False
    assert registry.is_generation_fenced("p2", 5) is False
    # Absent generation is never fenced (infrastructure caller).
    assert registry.is_generation_fenced("p1", None) is False


@pytest.mark.asyncio
async def test_close_all_with_no_tunnels_still_fences():
    registry = AutomationTunnelRegistry(layer="supervisor")
    closed = await registry.close_all_for_profile("p1", generation=7)
    assert closed == []
    assert registry.is_generation_fenced("p1", 7) is True


@pytest.mark.asyncio
async def test_fence_is_monotonic():
    registry = AutomationTunnelRegistry(layer="supervisor")
    await registry.close_all_for_profile("p1", generation=9)
    await registry.close_all_for_profile("p1", generation=5)
    assert registry.fence_generation("p1") == 9
