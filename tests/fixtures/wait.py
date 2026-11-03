"""Bounded condition-polling helpers shared by E2E tests.

Every helper fails with ``TimeoutError`` instead of asserting on a value read
after an arbitrary fixed delay. Callers keep the contract assertion; the helper
only removes the race between the trigger and the observable state change.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")


async def wait_until(
    predicate: Callable[[], Any],
    *,
    timeout: float,
    interval: float = 0.1,
    description: str = "condition",
) -> None:
    """Poll a synchronous predicate until it is truthy or the deadline expires.

    The predicate's last return value is included in the timeout error as
    the last observation (same diagnosis contract as poll_until).
    """
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return
        await asyncio.sleep(interval)
    raise TimeoutError(
        f"Timed out after {timeout:g}s waiting for {description}: last={last!r}"
    )


async def poll_until(
    read: Callable[[], Awaitable[T]],
    predicate: Callable[[T], bool],
    *,
    timeout: float,
    interval: float = 0.1,
    description: str = "condition",
) -> T:
    """Repeatedly await ``read`` until ``predicate`` accepts the value.

    Returns the accepted value so callers can use it for contract assertions.
    The last observed value is included in the timeout error for diagnosis.
    """
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = await read()
        if predicate(last):
            return last
        await asyncio.sleep(interval)
    raise TimeoutError(
        f"Timed out after {timeout:g}s waiting for {description}: last={last!r}"
    )


async def wait_for_log(
    read_log: Callable[[], Awaitable[str]],
    needle: str,
    *,
    timeout: float = 15.0,
    interval: float = 0.2,
    offset: int = 0,
    description: str | None = None,
) -> str:
    """Poll a log reader for ``needle`` after ``offset``; return the new slice."""
    text = await poll_until(
        read_log,
        lambda value: needle in value[offset:],
        timeout=timeout,
        interval=interval,
        description=description or f"log {needle!r}",
    )
    return text[offset:]


def wait_until_sync(
    predicate: Callable[[], Any],
    *,
    timeout: float,
    interval: float = 0.05,
    description: str = "condition",
) -> None:
    """Poll a synchronous predicate from synchronous tests."""
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return
        time.sleep(interval)
    raise TimeoutError(
        f"Timed out after {timeout:g}s waiting for {description}: last={last!r}"
    )
