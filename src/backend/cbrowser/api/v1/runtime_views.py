"""Pure helpers for API runtime response construction."""

from __future__ import annotations

from typing import Any

from cbrowser.domain.models import (
    ProfileRuntime,
    ProfileRuntimeResponse,
    SearchDefaultsStatusData,
    TransportObservationData,
)
from fastapi import Request
from cbrowser.shared.fencing import fence_by_instance


def fence_search_defaults(
    status: SearchDefaultsStatusData | None,
    runtime_instance_id: str | None,
) -> SearchDefaultsStatusData | None:
    """A status recorded for a previous instance is stale: never present
    it as the current instance's outcome. The rule itself is the shared
    fence (`cbrowser.shared.fencing`), applied identically by the REST
    view, the SSE snapshot assembly and the coordinator's live publish."""
    return fence_by_instance(status, runtime_instance_id)


def fence_transport(
    observation: TransportObservationData | None,
    runtime_instance_id: str | None,
) -> TransportObservationData | None:
    """Same instance fence as search-defaults, for transport state."""
    return fence_by_instance(observation, runtime_instance_id)


async def make_runtime_response(
    rt: ProfileRuntime, coordinator: Any = None
) -> ProfileRuntimeResponse:
    last_error = (
        coordinator.get_last_error(rt.profile_id, runtime=rt)
        if coordinator
        else None
    )
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
        display_number=rt.display_number,
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
        backoff_started_at=rt.backoff_started_at,
        next_retry_at=rt.next_retry_at,
        preview_captured_at=rt.preview_captured_at,
        updated_at=rt.updated_at,
    )


def resolve_operation_id(
    idempotency_key: str | None,
    x_operation_id: str | None,
    operation_id: str | None,
) -> str | None:
    return idempotency_key or x_operation_id or operation_id


def publish_reference_change(
    request: Request, event_name: str, entity_id: str | None = None
) -> None:
    """Notify SSE subscribers that group/proxy reference data changed
    (t056 A31).  No-op when no coordinator is attached (e.g. unit tests
    that build the app standalone); never raises for a publish failure —
    the coordinator owns its background task errors."""
    coordinator = getattr(request.app.state, "coordinator", None)
    if coordinator is not None:
        publish = getattr(coordinator, "publish_reference_change_later", None)
        if publish is not None:
            publish(event_name, entity_id)
