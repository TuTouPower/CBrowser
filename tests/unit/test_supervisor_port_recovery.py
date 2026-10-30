"""Recovery must reserve actual ports without duplicating live ownership."""

import asyncio

import pytest
from cbrowser.supervisor.port_allocator import PortAllocator


@pytest.mark.asyncio
async def test_restore_preserves_actual_port_and_rejects_conflicting_owner():
    allocator = PortAllocator(30000, 30002)
    await allocator.restore("profile_b", 30002)
    await allocator.restore("profile_b", 30002)
    with pytest.raises(ValueError, match="owned"):
        await allocator.restore("profile_a", 30002)
    assert await allocator.allocate("profile_a") == 30000
    with pytest.raises(ValueError, match="different"):
        await allocator.restore("profile_b", 30001)
    with pytest.raises(ValueError, match="range"):
        await allocator.restore("profile_c", 29999)


@pytest.mark.asyncio
async def test_parallel_restore_and_allocate_cannot_duplicate_a_port():
    allocator = PortAllocator(30000, 30002)
    await allocator.restore("existing", 30001)
    ports = await asyncio.gather(
        allocator.allocate("new_a"), allocator.allocate("new_b")
    )
    assert set(ports) == {30000, 30002}
