"""System settings API (t074): server-persisted UI preferences."""

from __future__ import annotations

from typing import Annotated

from cbrowser.api.v1.deps import get_profile_service
from cbrowser.auth.dependencies import require_csrf_and_origin, require_user_session
from cbrowser.domain.models import UserSettingsResponse, UserSettingsUpdateRequest
from cbrowser.services.profile_service import ProfileService
from fastapi import APIRouter, Depends

settings_router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(require_user_session), Depends(require_csrf_and_origin)],
)

Service = Annotated[ProfileService, Depends(get_profile_service)]


@settings_router.get("", response_model=UserSettingsResponse)
async def get_settings(service: Service):
    return await service.get_settings()


@settings_router.patch("", response_model=UserSettingsResponse)
async def update_settings(payload: UserSettingsUpdateRequest, service: Service):
    return await service.update_settings(payload)
