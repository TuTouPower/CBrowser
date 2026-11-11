"""Human-priority control endpoints (t031, ADR 019).

- State and tunnels: human management surface (user session).
- Claim and handoff: automation clients (automation token, no CSRF:
  Bearer auth is not cookie-based).
- Restore: human management surface (user session + CSRF + Origin).

Claim/handoff responses carry the control generation; clients must
ignore a response whose generation is older than the generation they
already know (stale-response fence, AC-005).
"""

from __future__ import annotations

import logging
from typing import Annotated

from cbrowser.adapters.database.models import SessionModel
from cbrowser.shared.client_ip import resolve_client_ip
from cbrowser.auth.dependencies import (
    get_auth_service,
    require_csrf_and_origin,
    require_user_session,
)
from cbrowser.auth.service import AuthService
from cbrowser.domain.models import (
    AutomationTunnelData,
    ControlClaimRequest,
    ControlHandoffRequest,
    ProfileControlStateData,
)
from cbrowser.services.control_service import (
    ControlConflictError,
    ControlNotFoundError,
    ProfileControlService,
)
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("cbrowser.api.v1.control")

control_router = APIRouter(prefix="/api/v1", tags=["control"])

CONTROL_WS_CLOSE_CODE = 4403
CONTROL_WS_CLOSE_REASON = "control_revoked"


def get_control_service() -> ProfileControlService:
    raise NotImplementedError("ProfileControlService dependency must be provided")


def get_optional_control_service() -> ProfileControlService | None:
    """Control service when the app wires it; None in bare unit tests.

    Lifecycle handlers (bind, observed-state) use this variant so
    tests that exercise them without the t031 wiring keep working;
    the control endpoints themselves use the strict dependency.
    """
    return None


def _bearer_token(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        return ""
    return authorization[7:].strip()


async def require_automation_token(
    request: Request,
    profile_id: str,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> str:
    """Validate a cbat_ automation token for the profile; return its id."""
    token = _bearer_token(request.headers.get("authorization", ""))
    client_ip = resolve_client_ip(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        getattr(request.app.state, "trusted_proxy_cidrs", []),
    )
    allowed, _reason = await auth_service.authorize_automation(
        token, profile_id, client_ip=client_ip
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid automation token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_id = await auth_service.resolve_automation_token_id(token)
    if token_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid automation token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_id


def _handle_control_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ControlNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found"
        )
    if isinstance(exc, ControlConflictError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        )
    raise exc


@control_router.get(
    "/profiles/{profile_id}/control",
    response_model=ProfileControlStateData,
)
async def get_control_state(
    profile_id: str,
    session: Annotated[SessionModel, Depends(require_user_session)],
    service: Annotated[ProfileControlService, Depends(get_control_service)],
):
    try:
        return await service.get_state(profile_id)
    except Exception as exc:  # noqa: BLE001 - mapped below
        raise _handle_control_error(exc) from exc


@control_router.get(
    "/profiles/{profile_id}/control/tunnels",
    response_model=list[AutomationTunnelData],
)
async def list_control_tunnels(
    request: Request,
    profile_id: str,
    session: Annotated[SessionModel, Depends(require_user_session)],
    service: Annotated[ProfileControlService, Depends(get_control_service)],
):
    try:
        await service.get_state(profile_id)
    except Exception as exc:  # noqa: BLE001 - mapped below
        raise _handle_control_error(exc) from exc
    registry = getattr(request.app.state, "automation_tunnels", None)
    if registry is None:
        return []
    return [
        AutomationTunnelData(**record.to_data())
        for record in registry.list_for_profile(profile_id)
    ]


@control_router.post(
    "/profiles/{profile_id}/control/claim",
    response_model=ProfileControlStateData,
)
async def claim_control(
    profile_id: str,
    body: ControlClaimRequest,
    token_id: Annotated[str, Depends(require_automation_token)],
    service: Annotated[ProfileControlService, Depends(get_control_service)],
):
    try:
        state, _close_requested = await service.claim(
            profile_id, token_id, body.agent_session_id
        )
        return state
    except Exception as exc:  # noqa: BLE001 - mapped below
        raise _handle_control_error(exc) from exc


@control_router.post(
    "/profiles/{profile_id}/control/handoff",
    response_model=ProfileControlStateData,
)
async def handoff_control(
    profile_id: str,
    body: ControlHandoffRequest,
    token_id: Annotated[str, Depends(require_automation_token)],
    service: Annotated[ProfileControlService, Depends(get_control_service)],
):
    try:
        state, _close_requested = await service.handoff(
            profile_id,
            body.reason,
            detail=body.detail,
            agent_instance_id=token_id,
            agent_session_id=body.agent_session_id,
        )
        return state
    except Exception as exc:  # noqa: BLE001 - mapped below
        raise _handle_control_error(exc) from exc


@control_router.post(
    "/profiles/{profile_id}/control/restore",
    response_model=ProfileControlStateData,
)
async def restore_control(
    profile_id: str,
    session: Annotated[SessionModel, Depends(require_csrf_and_origin)],
    service: Annotated[ProfileControlService, Depends(get_control_service)],
):
    try:
        state, _close_requested = await service.restore(profile_id)
        return state
    except Exception as exc:  # noqa: BLE001 - mapped below
        raise _handle_control_error(exc) from exc


class AttendantDialogAnswerRequest(BaseModel):
    """t031: answer a held dialog through the attendant's session."""

    model_config = ConfigDict(extra="forbid")
    target_id: str = Field(min_length=1)
    accept: bool = False
    prompt_text: str | None = None


async def _require_dialog_agent(
    profile_id: str,
    token_id: str,
    service: ProfileControlService,
) -> None:
    """Dialog-plane actions are agent actions (t031_code_f001).

    Peeking or answering a held dialog requires agent control held by
    the calling token: after a takeover (owner user) there is no agent
    right to act on dialogs, and a second token may not act on the
    controlling agent's held dialog. The instance dimension is the one
    this path can check (dialog requests carry no session id); a
    record without an instance defers, mirroring the claim rule.
    """
    try:
        state = await service.get_state(profile_id)
    except Exception as exc:  # noqa: BLE001 - mapped below
        raise _handle_control_error(exc) from exc
    if state.owner != "agent":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "control_not_agent",
                "message": "Control is held by the user; agent dialog "
                "actions are refused",
            },
        )
    if (
        state.agent_instance_id is not None
        and state.agent_instance_id != token_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "control_second_agent",
                "message": "Another agent holds control for this profile",
            },
        )


@control_router.get("/profiles/{profile_id}/control/dialogs")
async def list_control_dialogs(
    profile_id: str,
    request: Request,
    token_id: Annotated[str, Depends(require_automation_token)],
    service: Annotated[ProfileControlService, Depends(get_control_service)],
):
    """Peek dialogs held by the resident attendant (automation token).

    A session attached after a dialog opened cannot observe it through
    its own CDP session (t031 chain evidence), so a later session
    peeks here before deciding whether to answer via the attendant.
    The peek is gated to the controlling agent (see
    ``_require_dialog_agent``).
    """
    await _require_dialog_agent(profile_id, token_id, service)
    coordinator = getattr(request.app.state, "coordinator", None)
    dialogs = None
    if coordinator is not None:
        dialogs = await coordinator.list_attendant_dialogs(profile_id)
    return {"profile_id": profile_id, "dialogs": dialogs or []}


@control_router.post("/profiles/{profile_id}/control/dialog-answer")
async def answer_control_dialog(
    profile_id: str,
    body: AttendantDialogAnswerRequest,
    request: Request,
    token_id: Annotated[str, Depends(require_automation_token)],
    service: Annotated[ProfileControlService, Depends(get_control_service)],
):
    """Answer a held dialog on the attendant's session (automation token).

    Gated to the controlling agent (see ``_require_dialog_agent``):
    a taken-over profile or a second token cannot answer dialogs.
    """
    await _require_dialog_agent(profile_id, token_id, service)
    coordinator = getattr(request.app.state, "coordinator", None)
    answered = None
    if coordinator is not None:
        answered = await coordinator.answer_attendant_dialog(
            profile_id, body.target_id, body.accept, body.prompt_text
        )
    if answered is None:
        raise HTTPException(
            status_code=404, detail="no held dialog for target"
        )
    return {
        "profile_id": profile_id,
        "dialog": answered,
        "action": "accept" if body.accept else "dismiss",
    }
