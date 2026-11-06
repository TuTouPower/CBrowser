"""Authenticated service RPC for the Docker Supervisor."""

import hmac
from pathlib import Path
from typing import Annotated

from cbrowser.api.v1 import router as runtime_api
from cbrowser.api.v1.deps import get_profile_service
from cbrowser.domain.models import (
    ConfigVersionResponse,
    ProfileResponse,
    ProfileRuntimeResponse,
    RuntimeEventResponse,
)
from cbrowser.secret_files import read_secret_file
from cbrowser.service_errors import ServiceNotConfiguredError
from cbrowser.services.profile_service import ProfileNotFoundError, ProfileService
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, SecretStr

bearer = HTTPBearer(auto_error=False, scheme_name="SupervisorServiceBearer")


def read_supervisor_token(path: Path | str | None) -> SecretStr | None:
    if path is None:
        return None
    return SecretStr(
        read_secret_file(path, label="Supervisor service token", minimum_bytes=32)
    )


def require_supervisor(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    token = getattr(request.app.state, "supervisor_token", None)
    if token is None:
        raise ServiceNotConfiguredError("Supervisor RPC is not configured")
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


class ProxyCredentialsResponse(BaseModel):
    """Current proxy credentials for the Supervisor's Browser sandbox.

    ``proxy_credential_revision`` is the revision frozen in the bound config
    version; ``credential_revision`` is the proxy's current revision. The
    Supervisor refuses to launch when they disagree (AC-007).
    """

    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    credential_revision: int
    proxy_credential_revision: int | None = None


@supervisor_router.get(
    "/proxies/{proxy_id}/credentials",
    response_model=ProxyCredentialsResponse,
    include_in_schema=False,
)
async def get_proxy_credentials(
    proxy_id: str,
    profile_id: Annotated[str, Query()],
    version: Annotated[int, Query(ge=1)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> ProxyCredentialsResponse:
    """Return current proxy credentials plus the version's frozen revision.

    Read-only service-plane RPC protected by the Supervisor bearer token. The
    password is returned only over this internal channel and is never logged.
    Both reads go through the service/repository layer: the frozen revision
    comes from the domain config-version snapshot, the live credentials from
    the proxy library.
    """
    try:
        snapshot = await service.get_config_version(profile_id, version)
    except ProfileNotFoundError:
        raise HTTPException(404, "Config version not found") from None
    cfg = snapshot.config if isinstance(snapshot.config, dict) else {}
    if cfg.get("proxy_id") != proxy_id:
        raise HTTPException(404, "Proxy credentials not found")
    creds = await service.get_proxy_credentials(proxy_id)
    if creds is None:
        raise HTTPException(404, "Proxy credentials not found")
    return ProxyCredentialsResponse(
        **creds,
        proxy_credential_revision=snapshot.proxy_credential_revision,
    )
