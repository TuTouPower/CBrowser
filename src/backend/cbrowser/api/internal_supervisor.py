"""Authenticated service RPC for the Docker Supervisor."""

import hmac
from pathlib import Path
from typing import Annotated

from cbrowser.api.v1 import router as runtime_api
from cbrowser.domain.models import (
    ConfigVersionResponse,
    ProfileResponse,
    ProfileRuntimeResponse,
    RuntimeEventResponse,
)
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr

bearer = HTTPBearer(auto_error=False, scheme_name="SupervisorServiceBearer")


def read_supervisor_token(path: Path | str | None) -> SecretStr | None:
    if path is None:
        return None
    try:
        token = Path(path).read_text().strip()
    except (OSError, UnicodeError):
        raise RuntimeError("Cannot read Supervisor service token file") from None
    if len(token.encode("utf-8")) < 32:
        raise RuntimeError("Supervisor service token must contain at least 32 bytes")
    return SecretStr(token)


def require_supervisor(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    token = request.app.state.supervisor_token
    if token is None:
        raise HTTPException(503, "Supervisor RPC is not configured")
    if credentials is None or not hmac.compare_digest(
        credentials.credentials.encode("utf-8"),
        token.get_secret_value().encode("utf-8"),
    ):
        raise HTTPException(
            401,
            "Invalid Supervisor credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


supervisor_router = APIRouter(
    prefix="/api/v1/internal/supervisor",
    tags=["internal-supervisor"],
    dependencies=[Depends(require_supervisor)],
)


@supervisor_router.get("/health")
def supervisor_rpc_health() -> dict[str, str]:
    return {"status": "ok"}


# Reuse the canonical API handlers and their service transactions. This service
# surface grants configuration reads, runtime intent and reports, never Profile CRUD.
for path, method, endpoint, response_model in (
    ("/profiles", "GET", runtime_api.list_profiles, list[ProfileResponse]),
    ("/profiles/{profile_id}", "GET", runtime_api.get_profile, ProfileResponse),
    (
        "/profiles/{profile_id}/versions/{version}",
        "GET",
        runtime_api.get_version,
        ConfigVersionResponse,
    ),
    (
        "/profiles/{profile_id}/runtime",
        "GET",
        runtime_api.get_profile_runtime,
        ProfileRuntimeResponse,
    ),
    (
        "/profiles/{profile_id}/runtime/desired-state",
        "PATCH",
        runtime_api.set_desired_state,
        ProfileRuntimeResponse,
    ),
    ("/runtimes/bind", "POST", runtime_api.bind_runtime, ProfileRuntimeResponse),
    (
        "/runtimes/observed",
        "POST",
        runtime_api.report_observed_state,
        ProfileRuntimeResponse,
    ),
    (
        "/runtimes/events",
        "POST",
        runtime_api.report_runtime_event,
        RuntimeEventResponse,
    ),
):
    supervisor_router.add_api_route(
        path, endpoint, methods=[method], response_model=response_model
    )
