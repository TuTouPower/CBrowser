"""Pure helpers for API runtime response construction."""

from __future__ import annotations

from typing import Any

from cbrowser.domain.models import (
    ProfileRuntime,
    ProfileRuntimeResponse,
    SearchDefaultsStatusData,
    TransportObservationData,
)


def fence_search_defaults(
    status: SearchDefaultsStatusData | None,
    runtime_instance_id: str | None,
) -> SearchDefaultsStatusData | None:
    """A status recorded for a previous instance is stale: never present
    it as the current instance's outcome. Single implementation shared by
    the REST view and the SSE snapshot assembly (the coordinator's live
    publish path applies the same rule via its own fenced accessor)."""
    if status is None:
        return None
    if status.runtime_instance_id != runtime_instance_id:
        return None
    return status


def fence_transport(
    observation: TransportObservationData | None,
    runtime_instance_id: str | None,
) -> TransportObservationData | None:
    """Same instance fence as search-defaults, for transport state."""
    if observation is None:
        return None
    if observation.runtime_instance_id != runtime_instance_id:
        return None
    return observation


async def make_runtime_response(
    rt: ProfileRuntime, coordinator: Any = None
) -> ProfileRuntimeResponse:
    last_error = coordinator.get_last_error(rt.profile_id) if coordinator else None
    search_defaults = fence_search_defaults(
        coordinator.get_search_defaults(rt.profile_id)
        if coordinator is not None
        and hasattr(coordinator, "get_search_defaults")
        else None,
        rt.runtime_instance_id,
    )
    transport = fence_transport(
        coordinator.get_transport(rt.profile_id)
        if coordinator is not None and hasattr(coordinator, "get_transport")
        else None,
        rt.runtime_instance_id,
    )
    control = None
    control_service = getattr(coordinator, "control_service", None)
    if control_service is not None:
        try:
            control = await control_service.get_state(rt.profile_id)
        except Exception:  # noqa: BLE001 - control is advisory on the runtime view
            control = None
    font_set_id: str | None = None
    missing_fonts: list[str] = []
    if coordinator is not None and hasattr(coordinator, "get_font_runtime"):
        font_set_id, missing_fonts = await coordinator.get_font_runtime(rt.profile_id)
    return ProfileRuntimeResponse(
        profile_id=rt.profile_id,
        desired_state=rt.desired_state,
        observed_state=rt.observed_state,
        runtime_instance_id=rt.runtime_instance_id,
        config_version=rt.config_version,
        failure_count=rt.failure_count,
        restart_blocked=rt.restart_blocked,
        last_exit_event_id=rt.last_exit_event_id,
        last_started_at=rt.last_started_at,
        last_stopped_at=rt.last_stopped_at,
        browser_product=rt.browser_product,
        browser_user_agent=rt.browser_user_agent,
        font_set_id=font_set_id,
        missing_fonts=missing_fonts,
        last_coordinator_error=last_error,
        search_defaults=search_defaults,
        transport=transport,
        control=control,
        updated_at=rt.updated_at,
    )


def resolve_operation_id(
    idempotency_key: str | None,
    x_operation_id: str | None,
    operation_id: str | None,
) -> str | None:
    return idempotency_key or x_operation_id or operation_id
