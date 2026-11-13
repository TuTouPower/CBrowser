"""Authenticated internal RPC router for the Gateway service."""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import Annotated

from cbrowser.api.v1.control_router import get_control_service
from cbrowser.api.v1.router import get_profile_service
from cbrowser.domain.models import (
    ControlTakeoverReport,
    DesiredState,
    ObservedState,
    ProfileControlStateData,
)
from cbrowser.secret_files import read_secret_file
from cbrowser.service_errors import ServiceNotConfiguredError
from cbrowser.services.control_service import (
    ControlConflictError,
    ControlNotFoundError,
    ProfileControlService,
)
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
        raise ServiceNotConfiguredError("Gateway RPC is not configured")
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


class GatewayRuntimeResponse(BaseModel):
    profile_id: str
    runtime_instance_id: str | None = None
    config_version: int
    desired_state: DesiredState
    observed_state: ObservedState


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


@gateway_router.post(
    "/profiles/{profile_id}/control/takeover",
    response_model=ProfileControlStateData,
    status_code=status.HTTP_200_OK,
)
async def gateway_report_takeover(
    profile_id: str,
    payload: ControlTakeoverReport,
    control_service: Annotated[
        ProfileControlService, Depends(get_control_service)
    ],
):
    """Human-input takeover reported by the Gateway (t031).

    The Stream Agent classifies a foreground viewer input, the Gateway
    forwards it here, and the control service moves the profile to the
    user, closes tunnels, and broadcasts the new state. Idempotent:
    reporting a takeover for an already-user profile is a no-op.
    """
    try:
        state, _close_requested = await control_service.takeover(
            profile_id,
            conn_id=payload.conn_id,
            input_kind=payload.input_kind,
        )
        return state
    except ControlNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )
    except ControlConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        )
