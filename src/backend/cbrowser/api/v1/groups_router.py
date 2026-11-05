"""Group CRUD API (t035 AC-003)."""

from __future__ import annotations

from typing import Annotated

from cbrowser.api.v1.deps import get_profile_service
from cbrowser.auth.dependencies import require_csrf_and_origin
from cbrowser.domain.models import (
    GroupCreateRequest,
    GroupReorderRequest,
    GroupResponse,
    GroupUpdateRequest,
)
from cbrowser.services.profile_service import ProfileService
from fastapi import APIRouter, Depends, HTTPException, status

group_router = APIRouter(
    prefix="/groups",
    tags=["groups"],
    dependencies=[Depends(require_csrf_and_origin)],
)

Service = Annotated[ProfileService, Depends(get_profile_service)]


@group_router.get("", response_model=list[GroupResponse])
async def list_groups(service: Service):
    return await service.list_groups()


@group_router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(payload: GroupCreateRequest, service: Service):
    try:
        return await service.create_group(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "group_name_in_use", "message": str(exc)},
        ) from None


@group_router.post("/reorder", response_model=list[GroupResponse])
async def reorder_groups(payload: GroupReorderRequest, service: Service):
    try:
        return await service.reorder_groups(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from None


@group_router.patch("/{group_id}", response_model=GroupResponse)
async def update_group(group_id: str, payload: GroupUpdateRequest, service: Service):
    try:
        updated = await service.update_group(group_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "group_name_in_use", "message": str(exc)},
        ) from None
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group {group_id} not found",
        )
    return updated


@group_router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: str, service: Service):
    if not await service.delete_group(group_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group {group_id} not found",
        )
