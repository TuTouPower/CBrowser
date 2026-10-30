"""Cancelling a real delayed retry must not deadlock the coordinator shutdown."""

import asyncio
from types import SimpleNamespace

import pytest
from cbrowser.supervisor.recovery_coordinator import RecoveryCoordinator


@pytest.mark.asyncio
async def test_shutdown_cancels_and_awaits_delayed_retry_without_lock_deadlock():
    coordinator = RecoveryCoordinator(SimpleNamespace())
    task = asyncio.create_task(
        coordinator._execute_retry(
            "profile",
            30,
            {"failure_count": 3},
            {},
        )
    )
    coordinator._in_flight_tasks["profile"] = task
    await asyncio.sleep(0)
    await asyncio.wait_for(coordinator.close(), timeout=1)
    assert task.done()
