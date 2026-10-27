"""FastAPI /api/v1 router for CBrowser v2."""

from __future__ import annotations

from typing import Annotated

from cbrowser.adapters.database.repository import (
    InstanceConflictError,
    InvalidConfigVersionError,
)
from cbrowser.domain.models import (
    ConfigVersionResponse,
    ErrorResponse,
    ProfileConfig,
    ProfileCreateRequest,
    ProfileResponse,
    ProfileRuntimeResponse,
    ProfileUpdateRequest,
    RuntimeDesiredStateRequest,
    RuntimeEvent,
    RuntimeEventReportRequest,
    RuntimeEventResponse,
    RuntimeInstanceBindRequest,
    RuntimeObservedReportRequest,
    Tag,
    ValidationErrorResponse,
)
from cbrowser.services.profile_service import (
    ProfileNotFoundError,
    ProfileService,
    StaleInstanceError,
)
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

v1_router = APIRouter(prefix="/api/v1", tags=["v1"])


def get_profile_service() -> ProfileService:
    raise NotImplementedError("ProfileService dependency must be provided")


@v1_router.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0"}


@v1_router.post(
    "/profiles",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Idempotency conflict",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
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
    op_id = idempotency_key or x_operation_id or operation_id
    config = ProfileConfig(
        name=payload.name,
        fingerprint_seed=payload.fingerprint_seed
        if payload.fingerprint_seed is not None
        else ProfileConfig().fingerprint_seed,
        proxy=payload.proxy,
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
        runtime_mode="docker",
        viewer_mode="webrtc",
    )
    tags = payload.tags or []
    profile = await service.create_profile(
        config=config, tags=tags, operation_id=op_id, req_payload=payload.model_dump()
    )
    return ProfileResponse.from_domain(profile)


@v1_router.get(
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


@v1_router.get(
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


@v1_router.put(
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
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": ValidationErrorResponse,
            "description": "Validation error",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
@v1_router.patch(
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
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
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
    service: Annotated[ProfileService, Depends(get_profile_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_operation_id: Annotated[str | None, Header(alias="X-Operation-ID")] = None,
    operation_id: Annotated[str | None, Query()] = None,
):
    op_id = idempotency_key or x_operation_id or operation_id
    try:
        patch_data = payload.model_dump(exclude_unset=True)
        tags_update = patch_data.pop("tags", None)
        tags_val = [Tag(**t) for t in tags_update] if tags_update is not None else None

        p = await service.update_profile(
            profile_id=profile_id,
            patch_data=patch_data,
            tags=tags_val,
            operation_id=op_id,
        )
        return ProfileResponse.from_domain(p)
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )


@v1_router.delete(
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
    service: Annotated[ProfileService, Depends(get_profile_service)],
):
    try:
        await service.delete_profile(profile_id)
        return
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )


@v1_router.get(
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
                tags=v.tags,
                created_at=v.created_at,
            )
            for v in versions
        ]
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )


@v1_router.get(
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
            tags=v.tags,
            created_at=v.created_at,
        )
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Version {version} not found"
        )


@v1_router.get(
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
    service: Annotated[ProfileService, Depends(get_profile_service)],
):
    try:
        rt = await service.get_runtime(profile_id)
        return ProfileRuntimeResponse(
            profile_id=rt.profile_id,
            desired_state=rt.desired_state,
            observed_state=rt.observed_state,
            runtime_instance_id=rt.runtime_instance_id,
            config_version=rt.config_version,
            failure_count=rt.failure_count,
            restart_blocked=rt.restart_blocked,
            last_exit_event_id=rt.last_exit_event_id,
            updated_at=rt.updated_at,
        )
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )


@v1_router.patch(
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
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
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
    service: Annotated[ProfileService, Depends(get_profile_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_operation_id: Annotated[str | None, Header(alias="X-Operation-ID")] = None,
    operation_id: Annotated[str | None, Query()] = None,
):
    op_id = idempotency_key or x_operation_id or operation_id
    try:
        rt = await service.set_desired_state(
            profile_id, payload.desired_state, operation_id=op_id
        )
        return ProfileRuntimeResponse(
            profile_id=rt.profile_id,
            desired_state=rt.desired_state,
            observed_state=rt.observed_state,
            runtime_instance_id=rt.runtime_instance_id,
            config_version=rt.config_version,
            failure_count=rt.failure_count,
            restart_blocked=rt.restart_blocked,
            last_exit_event_id=rt.last_exit_event_id,
            updated_at=rt.updated_at,
        )
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )


@v1_router.post(
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
    service: Annotated[ProfileService, Depends(get_profile_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_operation_id: Annotated[str | None, Header(alias="X-Operation-ID")] = None,
    operation_id: Annotated[str | None, Query()] = None,
):
    op_id = idempotency_key or x_operation_id or operation_id
    try:
        rt = await service.set_desired_state(profile_id, "stopped", operation_id=op_id)
        return ProfileRuntimeResponse(
            profile_id=rt.profile_id,
            desired_state=rt.desired_state,
            observed_state=rt.observed_state,
            runtime_instance_id=rt.runtime_instance_id,
            config_version=rt.config_version,
            failure_count=rt.failure_count,
            restart_blocked=rt.restart_blocked,
            last_exit_event_id=rt.last_exit_event_id,
            updated_at=rt.updated_at,
        )
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )


@v1_router.post(
    "/runtimes/bind",
    response_model=ProfileRuntimeResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Profile not found",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Active instance conflict",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": ValidationErrorResponse,
            "description": "Invalid config version or payload",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
async def bind_runtime(
    profile_id: Annotated[str, Query()],
    payload: RuntimeInstanceBindRequest,
    service: Annotated[ProfileService, Depends(get_profile_service)],
):
    try:
        rt = await service.bind_runtime_instance(
            profile_id,
            payload.runtime_instance_id,
            payload.config_version,
            payload.expected_current_instance,
        )
        return ProfileRuntimeResponse(
            profile_id=rt.profile_id,
            desired_state=rt.desired_state,
            observed_state=rt.observed_state,
            runtime_instance_id=rt.runtime_instance_id,
            config_version=rt.config_version,
            failure_count=rt.failure_count,
            restart_blocked=rt.restart_blocked,
            last_exit_event_id=rt.last_exit_event_id,
            updated_at=rt.updated_at,
        )
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )
    except InvalidConfigVersionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    except InstanceConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@v1_router.post(
    "/runtimes/observed",
    response_model=ProfileRuntimeResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Profile not found",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Stale instance conflict",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": ValidationErrorResponse,
            "description": "Invalid config version or payload",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
async def report_observed_state(
    profile_id: Annotated[str, Query()],
    payload: RuntimeObservedReportRequest,
    service: Annotated[ProfileService, Depends(get_profile_service)],
):
    try:
        rt = await service.report_observed_state(
            profile_id,
            payload.runtime_instance_id,
            payload.observed_state,
            payload.config_version,
        )
        return ProfileRuntimeResponse(
            profile_id=rt.profile_id,
            desired_state=rt.desired_state,
            observed_state=rt.observed_state,
            runtime_instance_id=rt.runtime_instance_id,
            config_version=rt.config_version,
            failure_count=rt.failure_count,
            restart_blocked=rt.restart_blocked,
            last_exit_event_id=rt.last_exit_event_id,
            updated_at=rt.updated_at,
        )
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )
    except StaleInstanceError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InvalidConfigVersionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )


@v1_router.post(
    "/runtimes/events",
    response_model=RuntimeEventResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Profile not found",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": ValidationErrorResponse,
            "description": "Invalid event payload or null exit code",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database busy (retryable)",
        },
    },
)
async def report_runtime_event(
    payload: RuntimeEventReportRequest,
    service: Annotated[ProfileService, Depends(get_profile_service)],
):
    if payload.event_type == "exit" and payload.exit_code is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
    return res
