"""Authentication and Automation Token Router for CBrowser API v1."""

from __future__ import annotations

import json
import logging
from typing import Annotated

from cbrowser.adapters.database.models import SessionModel
from cbrowser.api.v1.control_router import get_optional_control_service
from cbrowser.auth.client_ip import resolve_client_ip
from cbrowser.auth.dependencies import (
    get_auth_service,
    require_csrf_and_origin,
    require_user_session,
)
from cbrowser.auth.service import AuthService
from cbrowser.services.control_service import ProfileControlService
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

logger = logging.getLogger("cbrowser.api.v1.auth")

auth_router = APIRouter(prefix="/api/v1", tags=["auth"])


class LoginRequest(BaseModel):
    password: str = Field(..., description="Administrator password")


class LoginResponse(BaseModel):
    csrf_token: str = Field(..., description="CSRF token for write requests")


class SessionResponse(BaseModel):
    authenticated: bool
    csrf_token: str


class AutomationTokenCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    profile_ids: list[str] = Field(default_factory=list)
    expires_in_hours: float | None = Field(default=None, gt=0, le=24 * 365)


class AutomationTokenResponse(BaseModel):
    id: str
    name: str
    profile_ids: list[str]
    created_at: str
    revoked: bool
    revoked_at: str | None = None
    expires_at: str | None = None


class AutomationTokenCreatedResponse(AutomationTokenResponse):
    token: str = Field(
        ..., description="Plaintext token returned only once upon creation"
    )


@auth_router.post(
    "/auth/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    client_ip = resolve_client_ip(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        getattr(request.app.state, "trusted_proxy_cidrs", []),
    )
    ok, reason = await auth_service.authenticate_admin(payload.password, client_ip)
    if not ok:
        if reason == "rate_limited":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts, please try again later",
                headers={
                    "Retry-After": str(auth_service.rate_limit_retry_after(client_ip))
                },
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
        )

    raw_session_token, csrf_token, _ = await auth_service.create_session()

    response.set_cookie(
        key="cbrowser_session",
        value=raw_session_token,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        key="cbrowser_csrf",
        value=csrf_token,
        httponly=False,
        secure=True,
        samesite="strict",
        path="/",
    )

    return LoginResponse(csrf_token=csrf_token)


@auth_router.post(
    "/auth/logout",
    dependencies=[Depends(require_csrf_and_origin)],
    status_code=status.HTTP_200_OK,
)
async def logout(
    request: Request,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    session_token = request.cookies.get("cbrowser_session")
    if session_token:
        await auth_service.revoke_session(session_token)

    response.delete_cookie(
        key="cbrowser_session",
        path="/",
        httponly=True,
        secure=True,
        samesite="strict",
    )
    response.delete_cookie(
        key="cbrowser_csrf",
        path="/",
        httponly=False,
        secure=True,
        samesite="strict",
    )
    return {"status": "ok"}


@auth_router.get(
    "/auth/session",
    response_model=SessionResponse,
    dependencies=[Depends(require_user_session)],
)
async def get_session(request: Request):
    session: SessionModel = request.state.session
    return SessionResponse(authenticated=True, csrf_token=session.csrf_token)


@auth_router.post(
    "/automation/tokens",
    response_model=AutomationTokenCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf_and_origin)],
)
async def create_automation_token(
    payload: AutomationTokenCreateRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    raw_token, model = await auth_service.create_automation_token(
        name=payload.name,
        profile_ids=payload.profile_ids,
        expires_in_hours=payload.expires_in_hours,
    )
    return AutomationTokenCreatedResponse(
        id=model.id,
        name=model.name,
        profile_ids=json.loads(model.profile_ids),
        token=raw_token,
        created_at=model.created_at,
        revoked=model.revoked,
        revoked_at=model.revoked_at,
        expires_at=model.expires_at,
    )


@auth_router.get(
    "/automation/tokens",
    response_model=list[AutomationTokenResponse],
    dependencies=[Depends(require_user_session)],
)
async def list_automation_tokens(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    models = await auth_service.list_automation_tokens()
    return [
        AutomationTokenResponse(
            id=m.id,
            name=m.name,
            profile_ids=json.loads(m.profile_ids),
            created_at=m.created_at,
            revoked=m.revoked,
            revoked_at=m.revoked_at,
            expires_at=m.expires_at,
        )
        for m in models
    ]


@auth_router.delete(
    "/automation/tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf_and_origin)],
)
async def revoke_automation_token(
    token_id: str,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    control_service: Annotated[
        ProfileControlService | None,
        Depends(get_optional_control_service),
    ],
):
    ok = await auth_service.revoke_automation_token(token_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Token {token_id} not found or already revoked",
        )
    # t031_code_f002: revoking the token must also move live control
    # back to the user (identity_invalid) through the normal cascade,
    # or the revoked agent's established tunnels would keep working.
    # Best-effort after the revoke commit: a handoff failure is logged
    # but never undoes the revoke.
    if control_service is not None:
        try:
            await control_service.handoff_for_identity(
                token_id, "identity_invalid"
            )
        except Exception:  # noqa: BLE001 - revoke already committed
            logger.warning(
                "Control handoff after token revoke failed: token=%s",
                token_id,
            )
