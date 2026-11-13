"""The one instance-fence rule (t062).

A status/observation recorded for a previous runtime instance is stale:
it must never be presented as the current instance's outcome. Every
surface that pairs a value with an instance id (REST views, SSE
snapshots, live publish) applies this rule through here.
"""

from __future__ import annotations

from typing import Protocol, TypeVar


class _InstanceStamped(Protocol):
    runtime_instance_id: str | None


T = TypeVar("T", bound=_InstanceStamped)


def fence_by_instance(
    value: T | None, runtime_instance_id: str | None
) -> T | None:
    """Return ``value`` only when it belongs to ``runtime_instance_id``."""
    if value is None:
        return None
    if value.runtime_instance_id != runtime_instance_id:
        return None
    return value
