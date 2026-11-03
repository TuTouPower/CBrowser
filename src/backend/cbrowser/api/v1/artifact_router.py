"""Authenticated Artifact upload/list/download/delete API."""

from __future__ import annotations

from typing import Annotated

from cbrowser.adapters.database.models import SessionModel
from cbrowser.adapters.filesystem.artifact_store import (
    ArtifactError,
    ArtifactInsufficientStorage,
    ArtifactInvalidContentType,
    ArtifactInvalidName,
    ArtifactNotFound,
    ArtifactQuotaExceeded,
    ArtifactTooLarge,
)
from cbrowser.auth.dependencies import require_csrf_and_origin, require_user_session
from cbrowser.domain.models import ArtifactResponse
from cbrowser.service_errors import ServiceNotConfiguredError
from cbrowser.services.artifact_service import ArtifactService
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

artifact_router = APIRouter(prefix="/api/v1", tags=["artifacts"])


def get_artifact_service(request: Request) -> ArtifactService:
    service = getattr(request.app.state, "artifact_service", None)
    if service is None:
        raise ServiceNotConfiguredError("Artifact service is not configured")
    return service


def _raise_artifact_error(exc: ArtifactError) -> None:
    if isinstance(exc, ArtifactNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ArtifactInvalidName | ArtifactInvalidContentType):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, ArtifactTooLarge):
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    if isinstance(exc, ArtifactQuotaExceeded | ArtifactInsufficientStorage):
        raise HTTPException(status_code=507, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail="Artifact operation failed") from exc


@artifact_router.get(
    "/profiles/{profile_id}/artifacts",
    response_model=list[ArtifactResponse],
)
async def list_artifacts(
    profile_id: str,
    session: Annotated[SessionModel, Depends(require_user_session)],
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
):
    artifacts = await service.list(profile_id)
    return [
        ArtifactResponse.from_domain(item, service.container_path(item))
        for item in artifacts
    ]


@artifact_router.post(
    "/profiles/{profile_id}/artifacts",
    response_model=ArtifactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_artifact(
    profile_id: str,
    request: Request,
    session: Annotated[SessionModel, Depends(require_csrf_and_origin)],
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
    filename: Annotated[str, Query(min_length=1, max_length=255)],
):
    size_hint = 0
    raw_length = request.headers.get("content-length")
    if raw_length:
        try:
            size_hint = int(raw_length)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid Content-Length"
            ) from None
        if size_hint > service.max_artifact_bytes:
            raise HTTPException(status_code=413, detail="Upload exceeds size limit")
    try:
        artifact = await service.upload(
            profile_id,
            filename,
            request.headers.get("content-type"),
            request.stream(),
            size_hint=size_hint,
        )
    except ArtifactError as exc:
        _raise_artifact_error(exc)
    return ArtifactResponse.from_domain(artifact, service.container_path(artifact))


@artifact_router.get(
    "/profiles/{profile_id}/artifacts/{artifact_id}",
    response_class=FileResponse,
    responses={
        200: {
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
            "description": "Artifact bytes",
        }
    },
)
async def download_artifact(
    profile_id: str,
    artifact_id: str,
    session: Annotated[SessionModel, Depends(require_user_session)],
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
):
    try:
        artifact, path = await service.content_path(profile_id, artifact_id)
    except ArtifactError as exc:
        _raise_artifact_error(exc)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=artifact.name,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@artifact_router.delete(
    "/profiles/{profile_id}/artifacts/{artifact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_artifact(
    profile_id: str,
    artifact_id: str,
    session: Annotated[SessionModel, Depends(require_csrf_and_origin)],
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
):
    try:
        await service.delete(profile_id, artifact_id)
    except ArtifactError as exc:
        _raise_artifact_error(exc)
