"""Authenticated environment preview thumbnail read endpoint (t040)."""

from __future__ import annotations

import json
from typing import Annotated

from cbrowser.adapters.database.models import SessionModel
from cbrowser.api.v1.deps import get_profile_service
from cbrowser.auth.dependencies import require_user_session
from cbrowser.preview import IMAGE_FILE, is_current_preview, read_meta, read_policy
from cbrowser.services.profile_service import ProfileNotFoundError, ProfileService
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response

preview_router = APIRouter(prefix="/api/v1", tags=["profiles"])

_NOT_FOUND = "Preview not found"


@preview_router.get(
    "/profiles/{profile_id}/preview",
    response_class=FileResponse,
    responses={
        200: {
            "content": {
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}}
            },
            "description": "Latest environment preview JPEG",
        }
    },
)
async def get_preview(
    profile_id: str,
    request: Request,
    session: Annotated[SessionModel, Depends(require_user_session)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
):
    policy_row = await service.get_preview_policy(profile_id)
    if policy_row is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    if not policy_row[0]:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    epoch = policy_row[1]
    directory = service.get_preview_dir(profile_id)
    if directory is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    policy = read_policy(directory)
    if policy is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    meta = read_meta(directory)
    try:
        runtime = await service.get_runtime(profile_id)
    except ProfileNotFoundError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from None
    runtime_instance_id = runtime.runtime_instance_id
    if runtime_instance_id is None and meta is not None:
        runtime_instance_id = meta.runtime_instance_id
    if not is_current_preview(
        directory, policy, epoch=epoch, runtime_instance_id=runtime_instance_id
    ):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    captured_at = meta.captured_at if meta is not None else ""
    etag = json.dumps(captured_at)
    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return FileResponse(
        directory / IMAGE_FILE,
        media_type="image/jpeg",
        headers=headers,
    )
