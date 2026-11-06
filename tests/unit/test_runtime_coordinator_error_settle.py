"""Coordinator last error must settle once the runtime record converges.

The Supervisor reports ``observed_state=running`` through runtime events on a
path independent of the coordinator's backoff retry loop. A residual
``last_coordinator_error`` from an earlier failed start must not remain
visible once the authoritative runtime record shows a healthy running pair.
"""

from __future__ import annotations

from types import SimpleNamespace

from cbrowser.api.runtime_coordinator import RuntimeCoordinator


def _coordinator() -> RuntimeCoordinator:
    return RuntimeCoordinator(
        supervisor_url=None,
        supervisor_token=None,
        profile_service=object(),
    )


def _converged() -> SimpleNamespace:
    return SimpleNamespace(
        desired_state="running",
        observed_state="running",
        runtime_instance_id="inst-1",
    )


def test_converged_runtime_clears_residual_coordinator_error() -> None:
    coordinator = _coordinator()
    coordinator.set_last_error(
        "p1", "Supervisor start failed (503): Mock supervisor failure"
    )
    assert coordinator.get_last_error("p1") is not None

    assert coordinator.get_last_error("p1", runtime=_converged()) is None
    assert coordinator.get_last_error("p1") is None


def test_pending_runtime_keeps_coordinator_error() -> None:
    coordinator = _coordinator()
    coordinator.set_last_error("p1", "Supervisor start failed (503)")
    pending = SimpleNamespace(
        desired_state="running",
        observed_state="stopped",
        runtime_instance_id=None,
    )
    assert (
        coordinator.get_last_error("p1", runtime=pending)
        == "Supervisor start failed (503)"
    )
