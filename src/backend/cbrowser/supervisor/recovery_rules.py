"""Pure recovery decisions shared by the supervisor recovery coordinator."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cbrowser.domain.runtime_policy import AUTO_RETRY_DELAYS

TERMINATED_CONTAINER_STATUSES = frozenset({"exited", "dead"})


def index_containers_by_profile(
    containers: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    indexed: dict[str, dict[str, dict[str, Any]]] = {}
    for container in containers:
        profile_id = container.get("profile_id")
        role = container.get("role")
        if profile_id and role:
            indexed.setdefault(profile_id, {})[role] = container
    return indexed


def live_instance_ids(
    docker_by_profile: dict[str, dict[str, dict[str, Any]]],
) -> set[str]:
    return {
        container.get("instance_id")
        for roles in docker_by_profile.values()
        for container in roles.values()
        if container.get("instance_id")
    }


def stream_missing(
    browser_status: Any, stream_container: dict[str, Any] | None
) -> bool:
    return browser_status == "running" and (
        not stream_container or stream_container.get("status") != "running"
    )


def browser_terminated(
    status: Any, instance_id: str, reported_instances: set[str]
) -> bool:
    return (
        status in TERMINATED_CONTAINER_STATUSES
        and instance_id not in reported_instances
    )


def exit_event_superseded(runtime: dict[str, Any], instance_id: str) -> bool:
    return (
        runtime.get("desired_state") == "stopped"
        or runtime.get("runtime_instance_id") is None
        or runtime.get("runtime_instance_id") != instance_id
    )


def terminal_observation(exit_code: int) -> tuple[str, str]:
    if exit_code == 0:
        return "stopped", "normal_exit"
    return "error", "container_exit"


def retry_delay_for_failure(failure_count: int) -> float:
    if failure_count == 0:
        return 0.0
    return AUTO_RETRY_DELAYS[failure_count - 1]


def remaining_retry_seconds(updated_at: Any, delay_sec: float) -> float:
    if not updated_at or delay_sec <= 0.0:
        return 0.0
    try:
        updated_dt = datetime.fromisoformat(updated_at)
        if updated_dt.tzinfo is None:
            updated_dt = updated_dt.replace(tzinfo=UTC)
        elapsed = (datetime.now(UTC) - updated_dt).total_seconds()
        return max(0.0, delay_sec - elapsed)
    except (ValueError, TypeError):
        return delay_sec


def remaining_retry_seconds_from_deadline(
    next_retry_at: Any, updated_at: Any, delay_sec: float
) -> float:
    """Resume the remaining window from the API's durable retry deadline.

    ``next_retry_at`` is the server-side authoritative deadline recorded
    when a failure is observed (``backoff_started_at +
    AUTO_RETRY_DELAYS[failure_count - 1]``). A Supervisor restart resumes
    the remaining window; it never replays the full delay. Fall back to the
    same formula derived from ``updated_at`` when the deadline is absent or
    unparsable.
    """
    if delay_sec <= 0.0:
        return 0.0
    if next_retry_at:
        try:
            deadline_dt = datetime.fromisoformat(next_retry_at)
            if deadline_dt.tzinfo is None:
                deadline_dt = deadline_dt.replace(tzinfo=UTC)
            return max(0.0, (deadline_dt - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError):
            pass
    return remaining_retry_seconds(updated_at, delay_sec)


def is_brand_new_runtime(
    failure_count: int, last_exit_event_id: str | None
) -> bool:
    return failure_count == 0 and last_exit_event_id is None


def runtime_pair_active(
    observed_state: Any,
    runtime_instance_id: str,
    browser: dict[str, Any] | None,
    stream: dict[str, Any] | None,
    stream_registered: bool | None = None,
) -> bool:
    # t026: a running Stream container whose Agent is known to be
    # unregistered is not an active pair; unknown registration (None)
    # keeps the historical behavior.
    return (
        observed_state != "error"
        and browser is not None
        and stream is not None
        and browser.get("status") == "running"
        and stream.get("status") == "running"
        and browser.get("instance_id") == runtime_instance_id
        and stream_registered is not False
    )


def failure_budget_exhausted(failure_count: int, limit: int) -> bool:
    return failure_count >= limit


def is_normal_exit_health(details: dict[str, Any]) -> bool:
    """Return True only if Agent supervision details confirm a clean exit.

    Requires exit code 0 and exit reason normal.
    """
    return (
        details.get("state") == "stopped"
        and details.get("exit_code") == 0
        and details.get("exit_reason") == "normal"
    )


def is_error_exit_health(details: dict[str, Any]) -> bool:
    """Return True if Agent supervision details confirm an error or owner-loss exit."""
    return (
        details.get("state") == "error"
        or details.get("exit_reason") == "process_observation_lost"
        or (details.get("state") == "stopped" and details.get("exit_code") != 0)
    )
