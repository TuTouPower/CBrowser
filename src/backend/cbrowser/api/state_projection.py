"""Project domain runtimes onto the minimal state protocol (t083).

Lives in the API layer: ``cbrowser.shared`` must stay free of domain
imports (t062 boundary), while both producers of the protocol — the
snapshot endpoint and the coordinator's change notices — are API-side.
"""

from __future__ import annotations

from cbrowser.domain.models import ProfileRuntime
from cbrowser.shared.state_protocol import SupervisorProfileState


def profile_state_from_runtime(
    runtime: ProfileRuntime,
) -> SupervisorProfileState:
    """Project a domain ``ProfileRuntime`` onto the minimal DTO."""
    return SupervisorProfileState(
        profile_id=runtime.profile_id,
        display_number=runtime.display_number,
        desired_state=runtime.desired_state,
        observed_state=runtime.observed_state,
        runtime_instance_id=runtime.runtime_instance_id,
        config_version=runtime.config_version,
        failure_count=runtime.failure_count,
        restart_blocked=runtime.restart_blocked,
        last_exit_event_id=runtime.last_exit_event_id,
        backoff_started_at=runtime.backoff_started_at,
        next_retry_at=runtime.next_retry_at,
        updated_at=runtime.updated_at,
        state_revision=runtime.state_revision,
    )
