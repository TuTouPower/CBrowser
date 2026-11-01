"""Authenticated internal RPC router for the Gateway service."""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import Annotated

from cbrowser.api.v1.router import get_profile_service
from cbrowser.auth.dependencies import get_auth_service
from cbrowser.auth.service import AuthService
from cbrowser.secret_files import read_secret_file
from cbrowser.services.profile_service import ProfileNotFoundError, ProfileService
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, SecretStr

bearer = HTTPBearer(auto_error=False, scheme_name="GatewayServiceBearer")


def read_gateway_token(path: Path | str | None) -> SecretStr | None:
    if path is None:
        return None
    return SecretStr(
        read_secret_file(path, label="Gateway service token", minimum_bytes=32)
    )


def require_gateway(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    token = getattr(request.app.state, "gateway_token", None)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway RPC is not configured",
        )
    if credentials is None or not hmac.compare_digest(
        credentials.credentials.encode("utf-8"),
        token.get_secret_value().encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Gateway credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


gateway_router = APIRouter(
    prefix="/api/v1/internal/gateway",
    tags=["internal-gateway"],
    dependencies=[Depends(require_gateway)],
)


class ViewerAuthorizeRequest(BaseModel):
    session_token: str | None = None
    session_cookie: str | None = None
    origin: str
    profile_id: str


class ViewerAuthorizeResponse(BaseModel):
    allowed: bool
    reason: str | None = None


class AutomationAuthorizeRequest(BaseModel):
    token: str
    profile_id: str


class AutomationAuthorizeResponse(BaseModel):
    allowed: bool
    reason: str | None = None


class GatewayRuntimeResponse(BaseModel):
    profile_id: str
    runtime_instance_id: str | None = None
    config_version: int
    desired_state: str
    observed_state: str


@gateway_router.post(
    "/viewer-authorize",
    response_model=ViewerAuthorizeResponse,
    status_code=status.HTTP_200_OK,
)
async def viewer_authorize(
    payload: ViewerAuthorizeRequest,
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    token = payload.session_token or payload.session_cookie
    if not token:
        return ViewerAuthorizeResponse(allowed=False, reason="missing_session")

    allowed_origins = getattr(request.app.state, "allowed_origins", [])
    allowed, reason = await auth_service.authorize_viewer(
        session_token=token,
        origin=payload.origin,
        profile_id=payload.profile_id,
        allowed_origins=allowed_origins,
    )
    return ViewerAuthorizeResponse(allowed=allowed, reason=reason)


@gateway_router.post(
    "/automation-authorize",
    response_model=AutomationAuthorizeResponse,
    status_code=status.HTTP_200_OK,
)
async def automation_authorize(
    payload: AutomationAuthorizeRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    allowed, reason = await auth_service.authorize_automation(
        token=payload.token,
        profile_id=payload.profile_id,
    )
    return AutomationAuthorizeResponse(allowed=allowed, reason=reason)


@gateway_router.get(
    "/profiles/{profile_id}/runtime",
    response_model=GatewayRuntimeResponse,
    status_code=status.HTTP_200_OK,
)
async def get_gateway_profile_runtime(
    profile_id: str,
    profile_service: Annotated[ProfileService, Depends(get_profile_service)],
):
    try:
        rt = await profile_service.get_runtime(profile_id)
        return GatewayRuntimeResponse(
            profile_id=rt.profile_id,
            runtime_instance_id=rt.runtime_instance_id,
            config_version=rt.config_version,
            desired_state=rt.desired_state,
            observed_state=rt.observed_state,
        )
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )
