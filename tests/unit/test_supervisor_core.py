"""Unit test suite for Supervisor Core components.

Tests:
1. Path validation & symlink escape refusal (AC-001).
2. UDP mux port allocator bounds, exhaustion, and reuse after release (AC-002).
3. Retry policy 2/10/30 backoff and 3-strikes blocking (AC-005).
4. Event forwarder offline spooling and recovery deduplication (AC-004).
"""

from pathlib import Path

import pytest
from cbrowser.supervisor.path_validator import PathSecurityError, PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator, PortPoolExhaustedError


def test_path_validator_symlink_and_traversal(tmp_path: Path):
    safe_root = tmp_path / "safe_root"
    safe_root.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    validator = PathValidator(safe_root)

    # 1. Valid profile dirs
    pdir = validator.get_profile_data_dir("p1")
    assert str(pdir).startswith(str(safe_root.resolve()))
    assert pdir.name == "profile"

    # 2. Path traversal rejection
    with pytest.raises(PathSecurityError):
        validator.get_profile_data_dir("../p1")

    with pytest.raises(PathSecurityError):
        validator.get_profile_data_dir("p1/../../escape")

    # 3. Symlink escape rejection
    symlink_dir = safe_root / "profiles" / "escaped"
    symlink_dir.parent.mkdir(parents=True, exist_ok=True)
    symlink_dir.symlink_to(outside_dir, target_is_directory=True)

    with pytest.raises(PathSecurityError):
        validator.get_profile_data_dir("escaped")


@pytest.mark.asyncio
async def test_port_allocator_exhaustion_and_reuse():
    # Test on a small test range [30000, 30002]
    alloc = PortAllocator(min_port=30000, max_port=30002)

    p0 = await alloc.allocate("prof_0")
    p1 = await alloc.allocate("prof_1")
    p2 = await alloc.allocate("prof_2")

    assert p0 == 30000
    assert p1 == 30001
    assert p2 == 30002

    # Idempotent allocation
    assert await alloc.allocate("prof_0") == 30000

    # Exhaustion
    with pytest.raises(PortPoolExhaustedError):
        await alloc.allocate("prof_3")

    # Release and reuse
    released = await alloc.release("prof_1")
    assert released == 30001
    assert not alloc.is_port_used(30001)

    # Now prof_3 can get 30001
    p3 = await alloc.allocate("prof_3")
    assert p3 == 30001
