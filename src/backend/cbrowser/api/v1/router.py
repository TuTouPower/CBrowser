"""FastAPI /api/v1 router for CBrowser."""

from __future__ import annotations

import logging
from typing import Annotated

from cbrowser.adapters.database.models import SessionModel
from cbrowser.adapters.database.repository import (
    InstanceConflictError,
    InvalidConfigVersionError,
)
from cbrowser.api.v1.deps import get_profile_service
from cbrowser.api.v1.groups_router import group_router
from cbrowser.api.v1.proxies_router import proxy_router
from cbrowser.api.runtime_coordinator import RuntimeEventBroadcaster
from cbrowser.preview import PreviewPolicy, clear_preview, write_policy
from cbrowser.api.v1.control_router import (
    get_optional_control_service,
)
from cbrowser.api.v1.runtime_views import (
    fence_search_defaults,
    fence_transport,
    make_runtime_response,
    resolve_operation_id,
)
from cbrowser.auth.dependencies import require_csrf_and_origin, require_user_session
from cbrowser.domain.models import (
    ConfigVersionResponse,
    ErrorResponse,
    ProfileConfig,
    ProfileCreateRequest,
    ProfileDuplicateRequest,
    ProfileResetRequest,
    ProfileResponse,
    ProfileRuntimeEventData,
    ProfileRuntimeResponse,
    ProfileRuntimeStatusEvent,
    ProfileUpdateRequest,
    RuntimeDesiredStateRequest,
    RuntimeEvent,
    RuntimeEventReportRequest,
    RuntimeEventResponse,
    RuntimeInstanceBindRequest,
    RuntimeObservedReportRequest,
    ValidationErrorResponse,
)
from cbrowser.services.profile_service import (
    ConstraintViolationError,
    DatabaseLockError,
    InvalidFontSetBindingError,
    InvalidProfileNameError,
    ProfileNotFoundError,
    ProfileOperationConflictError,
    ProfileRunningError,
    ProfileService,
    StaleInstanceError,
)
from cbrowser.services.control_service import ProfileControlService
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

logger = logging.getLogger("cbrowser.api.v1.router")


async def _apply_preview_policy(
    profile_id: str,
    enabled: bool,
    epoch: int,
    request: Request,
    service: ProfileService,
) -> None:
    # Concurrent PATCHes race on the policy file: serialize on the
    # per-profile lock and re-read the authoritative DB policy inside it,
    # so a stale `enabled` read from before a newer commit can never
    # overwrite that newer policy file (old enabled vs new disabled).
    # The 10s supervisor RPC stays outside the lock so the same-profile
    # start/stop/bind/delete never blocks behind a slow dispatch.
    async with service._locks.lock(profile_id):
        fresh = await service.get_preview_policy(profile_id)
        if fresh is None:
            return
        enabled, epoch = fresh
        instance: str | None = None
        try:
            runtime = await service.get_runtime(profile_id)
            instance = runtime.runtime_instance_id
        except ProfileNotFoundError:
            pass
        directory = service.get_preview_dir(profile_id)
        if directory is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Preview storage unavailable",
            )
        try:
            write_policy(
                directory,
                PreviewPolicy(
                    enabled=enabled,
                    epoch=epoch,
                    runtime_instance_id=instance,
                ),
            )
        except OSError as exc:
            logger.error(
                "Preview policy write failed: profile=%s error_type=%s",
                profile_id,
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Preview storage unavailable",
            ) from None
        if not enabled:
            clear_preview(directory)
            await service.clear_preview_capture(profile_id)
    coordinator = getattr(request.app.state, "coordinator", None)
    if coordinator is not None:
        await coordinator.request_preview_policy(profile_id, enabled, epoch, instance)
        if coordinator.has_pending_preview_policy(profile_id):
            coordinator.trigger_reconcile(profile_id)


v1_router = APIRouter(prefix="/api/v1")
profile_router = APIRouter(
    tags=["profiles"], dependencies=[Depends(require_csrf_and_origin)]
)


@v1_router.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0"}


@v1_router.get(
    "/events",
    response_model=ProfileRuntimeStatusEvent,
    response_class=StreamingResponse,
    responses={
        status.HTTP_200_OK: {
            "description": "SSE stream for profile runtime status updates",
            "content": {
                "text/event-stream": {
                    "schema": {"$ref": "#/components/schemas/ProfileRuntimeStatusEvent"}
                }
            },
        },
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Authentication required",
        },
    },
)
async def subscribe_runtime_events(
    request: Request,
    session: Annotated[SessionModel, Depends(require_user_session)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
    control_service: Annotated[
        ProfileControlService | None, Depends(get_optional_control_service)
    ] = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    last_event_id_query: Annotated[str | None, Query(alias="last_event_id")] = None,
):
    async def get_initial_snapshots() -> list[ProfileRuntimeEventData]:
        profiles = await service.list_profiles()
        coordinator = getattr(request.app.state, "coordinator", None)
        snapshots = []
        for p in profiles:
            try:
                rt = await service.get_runtime(p.id)
                last_err = (
                    coordinator.get_last_error(p.id, runtime=rt)
                    if coordinator
                    else None
                )
                search_defaults = fence_search_defaults(
                    coordinator.get_search_defaults(p.id)
                    if coordinator is not None
                    and hasattr(coordinator, "get_search_defaults")
                    else None,
                    rt.runtime_instance_id,
                )
                transport = fence_transport(
                    coordinator.get_transport(p.id)
                    if coordinator is not None
                    and hasattr(coordinator, "get_transport")
                    else None,
                    rt.runtime_instance_id,
                )
                control = None
                if control_service is not None:
                    try:
                        control = await control_service.get_state(p.id)
                    except Exception:  # noqa: BLE001 - snapshot stays usable
                        control = None
                snapshots.append(
                    ProfileRuntimeEventData(
                        profile_id=rt.profile_id,
                        desired_state=rt.desired_state,
                        observed_state=rt.observed_state,
                        runtime_instance_id=rt.runtime_instance_id,
                        failure_count=rt.failure_count,
                        restart_blocked=rt.restart_blocked,
                        last_started_at=rt.last_started_at,
                        last_stopped_at=rt.last_stopped_at,
                        browser_product=rt.browser_product,
                        browser_user_agent=rt.browser_user_agent,
                        last_coordinator_error=last_err,
                        search_defaults=search_defaults,
                        transport=transport,
                        control=control,
                        updated_at=rt.updated_at,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - single profile failure must not abort initial SSE snapshot
                logger.warning(
                    "SSE snapshot unavailable: profile=%s error_type=%s",
                    p.id,
                    type(exc).__name__,
                )
        return snapshots

    effective_last_event_id = last_event_id or last_event_id_query
    coordinator = getattr(request.app.state, "coordinator", None)
    broadcaster = (
        coordinator.broadcaster
        if coordinator is not None
        else RuntimeEventBroadcaster()
    )
    generator = broadcaster.subscribe(
        last_event_id=effective_last_event_id,
        initial_snapshot_provider=get_initial_snapshots,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@profile_router.post(
    "/profiles",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Idempotency conflict",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ValidationErrorResponse,
            "description": "Validation error",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
async def create_profile(
    payload: ProfileCreateRequest,
    service: Annotated[ProfileService, Depends(get_profile_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_operation_id: Annotated[str | None, Header(alias="X-Operation-ID")] = None,
    operation_id: Annotated[str | None, Query()] = None,
):
    op_id = resolve_operation_id(idempotency_key, x_operation_id, operation_id)
    config = ProfileConfig(
        name=payload.name,
        fingerprint_seed=payload.fingerprint_seed
        if payload.fingerprint_seed is not None
        else ProfileConfig().fingerprint_seed,
        group_id=payload.group_id,
        proxy_id=payload.proxy_id,
        timezone=payload.timezone,
        locale=payload.locale,
        screen_width=payload.screen_width,
        screen_height=payload.screen_height,
        gpu_family=payload.gpu_family,
        humanize=payload.humanize,
        human_preset=payload.human_preset,
        geoip=payload.geoip,
        clipboard_sync=payload.clipboard_sync,
        auto_launch=payload.auto_launch,
        color_scheme=payload.color_scheme,
        fingerprint_platform=payload.fingerprint_platform,
        font_set_id=payload.font_set_id,
        launch_args=payload.launch_args,
        extension_paths=payload.extension_paths,
        allow_3p_cookies=payload.allow_3p_cookies,
        set_google_default=payload.set_google_default,
        capture_preview=payload.capture_preview,
        restore_session=payload.restore_session,
        transparent_proxy=payload.transparent_proxy,
        portable_cookies=payload.portable_cookies,
        notes=payload.notes,
        sort_order=payload.sort_order,
    )
    try:
        profile = await service.create_profile(
            config=config,
            operation_id=op_id,
            req_payload=payload.model_dump(),
            font_set_id_supplied="font_set_id" in payload.model_fields_set,
        )
    except InvalidFontSetBindingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None
    return ProfileResponse.from_domain(profile)


@profile_router.get(
    "/profiles",
    response_model=list[ProfileResponse],
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
async def list_profiles(
    service: Annotated[ProfileService, Depends(get_profile_service)],
):
    profiles = await service.list_profiles()
    return [ProfileResponse.from_domain(p) for p in profiles]


@profile_router.get(
    "/profiles/{profile_id}",
    response_model=ProfileResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Profile not found",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
async def get_profile(
    profile_id: str,
    service: Annotated[ProfileService, Depends(get_profile_service)],
):
    try:
        p = await service.get_profile(profile_id)
        return ProfileResponse.from_domain(p)
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )


@profile_router.put(
    "/profiles/{profile_id}",
    response_model=ProfileResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Profile not found",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Idempotency conflict",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ValidationErrorResponse,
            "description": "Validation error",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
@profile_router.patch(
    "/profiles/{profile_id}",
    response_model=ProfileResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Profile not found",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Idempotency conflict",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ValidationErrorResponse,
            "description": "Validation error",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
async def update_profile(
    profile_id: str,
    payload: ProfileUpdateRequest,
    request: Request,
    service: Annotated[ProfileService, Depends(get_profile_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_operation_id: Annotated[str | None, Header(alias="X-Operation-ID")] = None,
    operation_id: Annotated[str | None, Query()] = None,
):
    op_id = resolve_operation_id(idempotency_key, x_operation_id, operation_id)
    patch_data = payload.model_dump(exclude_unset=True)
    preview_patch = "capture_preview" in patch_data
    try:
        p = await service.update_profile(
            profile_id=profile_id,
            patch_data=patch_data,
            operation_id=op_id,
        )
    except InvalidFontSetBindingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )
    if preview_patch:
        after = await service.get_preview_policy(profile_id)
        if after is not None:
            await _apply_preview_policy(profile_id, after[0], after[1], request, service)
    return ProfileResponse.from_domain(p)


@profile_router.delete(
    "/profiles/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Profile not found",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
async def delete_profile(
    profile_id: str,
    request: Request,
    service: Annotated[ProfileService, Depends(get_profile_service)],
):
    try:
        await service.delete_profile(profile_id)
        artifact_service = getattr(request.app.state, "artifact_service", None)
        if artifact_service is not None:
            try:
                await artifact_service.remove_profile(profile_id)
            except Exception as exc:  # noqa: BLE001 - profile is already deleted
                logger.warning(
                    "Artifact cleanup after profile deletion failed: "
                    "profile=%s error_type=%s",
                    profile_id,
                    type(exc).__name__,
                )
        return
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )
    except ProfileRunningError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "profile_running", "message": str(exc)},
        )


@profile_router.post(
    "/profiles/{profile_id}/duplicate",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Invalid duplicate name",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Profile not found",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Profile is running or operation conflicts",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
async def duplicate_profile(
    profile_id: str,
    payload: ProfileDuplicateRequest,
    service: Annotated[ProfileService, Depends(get_profile_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_operation_id: Annotated[str | None, Header(alias="X-Operation-ID")] = None,
    operation_id: Annotated[str | None, Query()] = None,
):
    op_id = resolve_operation_id(idempotency_key, x_operation_id, operation_id)
    try:
        profile = await service.duplicate_profile(
            profile_id,
            include_browser_state=payload.include_browser_state,
            name=payload.name,
            operation_id=op_id,
        )
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        ) from None
    except InvalidProfileNameError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from None
    except ProfileOperationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from None
    except ProfileRunningError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from None
    except ConstraintViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from None
    except DatabaseLockError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    return ProfileResponse.from_domain(profile)


@profile_router.post(
    "/profiles/{profile_id}/reset",
    response_model=ProfileResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Confirmation required",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Profile not found",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Profile is running",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
async def reset_profile(
    profile_id: str,
    payload: ProfileResetRequest,
    service: Annotated[ProfileService, Depends(get_profile_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_operation_id: Annotated[str | None, Header(alias="X-Operation-ID")] = None,
    operation_id: Annotated[str | None, Query()] = None,
):
    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset requires explicit confirmation",
        )
    op_id = resolve_operation_id(idempotency_key, x_operation_id, operation_id)
    try:
        profile = await service.reset_profile(profile_id, operation_id=op_id)
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        ) from None
    except ProfileOperationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from None
    except ProfileRunningError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from None
    except DatabaseLockError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    return ProfileResponse.from_domain(profile)


@profile_router.get(
    "/profiles/{profile_id}/versions",
    response_model=list[ConfigVersionResponse],
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Profile not found",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
async def list_versions(
    profile_id: str,
    service: Annotated[ProfileService, Depends(get_profile_service)],
):
    try:
        versions = await service.list_config_versions(profile_id)
        return [
            ConfigVersionResponse(
                id=v.id,
                profile_id=v.profile_id,
                version=v.version,
                config=v.config,
                created_at=v.created_at,
            )
            for v in versions
        ]
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )


@profile_router.get(
    "/profiles/{profile_id}/versions/{version}",
    response_model=ConfigVersionResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Version not found",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
async def get_version(
    profile_id: str,
    version: int,
    service: Annotated[ProfileService, Depends(get_profile_service)],
):
    try:
        v = await service.get_config_version(profile_id, version)
        return ConfigVersionResponse(
            id=v.id,
            profile_id=v.profile_id,
            version=v.version,
            config=v.config,
            created_at=v.created_at,
        )
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Version {version} not found"
        )


@profile_router.get(
    "/profiles/{profile_id}/runtime",
    response_model=ProfileRuntimeResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Profile not found",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
async def get_profile_runtime(
    profile_id: str,
    request: Request,
    service: Annotated[ProfileService, Depends(get_profile_service)],
):
    try:
        rt = await service.get_runtime(profile_id)
        coord = getattr(request.app.state, "coordinator", None)
        if coord is not None and hasattr(coord, "refresh_search_defaults"):
            await coord.refresh_search_defaults(profile_id)
        if coord is not None and hasattr(coord, "refresh_transport"):
            await coord.refresh_transport(profile_id)
        return await make_runtime_response(rt, coord)
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )


@profile_router.post(
    "/profiles/{profile_id}/runtime/search-defaults/retry",
    response_model=ProfileRuntimeResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Profile not found",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Live instance changed; retry against the current instance",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Runtime or supervisor unavailable",
        },
    },
)
async def retry_profile_search_defaults(
    profile_id: str,
    request: Request,
    service: Annotated[ProfileService, Depends(get_profile_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    from cbrowser.api.runtime_coordinator import (
        SearchDefaultsConflictError,
        SearchDefaultsUnavailableError,
    )

    coord = getattr(request.app.state, "coordinator", None)
    if coord is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Runtime coordinator is unavailable",
        )
    try:
        # The caller's idempotency key becomes the end-to-end request_id:
        # repeating this call with the same key is deduplicated by the
        # supervisor and the runtime agent instead of executing twice.
        await coord.retry_search_defaults(
            profile_id, request_id=idempotency_key or None
        )
        rt = await service.get_runtime(profile_id)
        return await make_runtime_response(rt, coord)
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )
    except SearchDefaultsConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Live instance changed; retry against the current instance",
        )
    except SearchDefaultsUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search defaults retry is unavailable for this runtime",
        )


@profile_router.patch(
    "/profiles/{profile_id}/runtime/desired-state",
    response_model=ProfileRuntimeResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Profile not found",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Idempotency conflict",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ValidationErrorResponse,
            "description": "Validation error",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
async def set_desired_state(
    profile_id: str,
    payload: RuntimeDesiredStateRequest,
    request: Request,
    service: Annotated[ProfileService, Depends(get_profile_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_operation_id: Annotated[str | None, Header(alias="X-Operation-ID")] = None,
    operation_id: Annotated[str | None, Query()] = None,
):
    op_id = resolve_operation_id(idempotency_key, x_operation_id, operation_id)
    try:
        rt = await service.set_desired_state(
            profile_id, payload.desired_state, operation_id=op_id
        )
        coord = getattr(request.app.state, "coordinator", None)
        if coord:
            coord.publish_profile_change_later(profile_id)
            coord.trigger_reconcile(profile_id)
        return await make_runtime_response(rt, coord)
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )


@profile_router.post(
    "/profiles/{profile_id}/stop",
    response_model=ProfileRuntimeResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Profile not found",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Idempotency conflict",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
async def stop_profile(
    profile_id: str,
    request: Request,
    service: Annotated[ProfileService, Depends(get_profile_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_operation_id: Annotated[str | None, Header(alias="X-Operation-ID")] = None,
    operation_id: Annotated[str | None, Query()] = None,
):
    op_id = resolve_operation_id(idempotency_key, x_operation_id, operation_id)
    try:
        rt = await service.set_desired_state(profile_id, "stopped", operation_id=op_id)
        coord = getattr(request.app.state, "coordinator", None)
        if coord:
            coord.publish_profile_change_later(profile_id)
            coord.trigger_reconcile(profile_id)
        return await make_runtime_response(rt, coord)
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )


async def bind_runtime(
    profile_id: Annotated[str, Query()],
    payload: RuntimeInstanceBindRequest,
    request: Request,
    service: Annotated[ProfileService, Depends(get_profile_service)],
    control_service: Annotated[
        ProfileControlService | None, Depends(get_optional_control_service)
    ] = None,
):
    try:
        rt = await service.bind_runtime_instance(
            profile_id,
            payload.runtime_instance_id,
            payload.config_version,
            payload.expected_current_instance,
        )
        coord = getattr(request.app.state, "coordinator", None)
        if coord:
            coord.publish_profile_change_later(profile_id)
        if control_service is not None:
            # A fresh instance binding ends any previous agent control:
            # the old session's tunnels died with the old runtime.
            await control_service.note_runtime_started(
                profile_id, "profile_restart"
            )
        return await make_runtime_response(rt, coord)
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )
    except InvalidConfigVersionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)
        )
    except InstanceConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


async def report_observed_state(
    profile_id: Annotated[str, Query()],
    payload: RuntimeObservedReportRequest,
    request: Request,
    service: Annotated[ProfileService, Depends(get_profile_service)],
    control_service: Annotated[
        ProfileControlService | None, Depends(get_optional_control_service)
    ] = None,
):
    try:
        rt = await service.report_observed_state(
            profile_id,
            payload.runtime_instance_id,
            payload.observed_state,
            payload.config_version,
            payload.reason,
            browser_product=payload.browser_product,
            browser_user_agent=payload.browser_user_agent,
        )
        coord = getattr(request.app.state, "coordinator", None)
        if coord:
            coord.publish_profile_change_later(profile_id)
        if (
            control_service is not None
            and rt is not None
            and payload.observed_state == "error"
        ):
            # Crash observation releases the instance: control returns
            # to the user immediately, not at the next bind.
            await control_service.note_runtime_started(profile_id, "crash")
        return await make_runtime_response(rt, coord)
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )
    except StaleInstanceError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InvalidConfigVersionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)
        )


async def report_runtime_event(
    payload: RuntimeEventReportRequest,
    request: Request,
    service: Annotated[ProfileService, Depends(get_profile_service)],
):
    if payload.event_type == "exit" and payload.exit_code is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="exit_code cannot be null for exit event",
        )

    event = RuntimeEvent(
        event_id=payload.event_id,
        profile_id=payload.profile_id,
        runtime_instance_id=payload.runtime_instance_id,
        event_type=payload.event_type,
        exit_code=payload.exit_code,
        exit_reason=payload.exit_reason,
        config_version=payload.config_version,
        payload=payload.payload,
    )
    res = await service.process_runtime_event(event)
    coord = getattr(request.app.state, "coordinator", None)
    if coord:
        coord.publish_profile_change_later(payload.profile_id)
    return res


v1_router.include_router(profile_router)
v1_router.include_router(group_router)
v1_router.include_router(proxy_router)
