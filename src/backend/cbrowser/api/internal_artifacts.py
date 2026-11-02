"""Authenticated Supervisor RPC for completed browser downloads."""

from __future__ import annotations

from typing import Annotated

from cbrowser.adapters.filesystem.artifact_store import ArtifactError, ArtifactNotFound
from cbrowser.api.internal_supervisor import require_supervisor
from cbrowser.domain.models import ArtifactDownloadReport, ArtifactDownloadResponse
from cbrowser.services.artifact_service import ArtifactService
from fastapi import APIRouter, Depends, HTTPException, Request

internal_artifact_router = APIRouter(
    prefix="/api/v1/internal/supervisor",
    tags=["internal-artifacts"],
    dependencies=[Depends(require_supervisor)],
)


def get_artifact_service(request: Request) -> ArtifactService:
    service = getattr(request.app.state, "artifact_service", None)
    if service is None:
        raise HTTPException(503, "Artifact service is not configured")
    return service


@internal_artifact_router.post(
    "/artifacts/downloads", response_model=ArtifactDownloadResponse
)
async def report_download(
    payload: ArtifactDownloadReport,
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
):
    try:
        result = await service.ingest_download(
            payload.profile_id,
            path=payload.path,
            name=payload.name,
            sha256=payload.sha256,
            size=payload.size,
            content_type=payload.content_type,
        )
    except ArtifactNotFound:
        raise HTTPException(404, "Profile not found") from None
    except ArtifactError:
        return ArtifactDownloadResponse(outcome="rejected", event_id=payload.event_id)
    if result.artifact is None:
        return ArtifactDownloadResponse(outcome="ignored", event_id=payload.event_id)
    return ArtifactDownloadResponse(
        outcome="created" if result.created else "duplicate",
        artifact_id=result.artifact.id,
        event_id=payload.event_id,
    )
