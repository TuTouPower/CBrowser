"""Edge authorization resolver consumed only by Caddy forward_auth (t064).

Before Caddy proxies a viewer signal handshake (``/stream/{profileId}/
signal``) to the Gateway, it issues a ``forward_auth`` subrequest here.
This endpoint is the single place where the management session cookie is
resolved into a Gateway-bound authorization context:

- the caller must prove it is the deployment edge by presenting the
  ``edge_proof_key`` secret (``X-CBrowser-Edge-Proof``); the path is also
  refused on the external listener by the rendered Caddyfile, so a direct
  external call fails on the proof even if it somehow routed here;
- session validity, Origin and Profile binding are decided by
  ``AuthService.authorize_viewer`` — the same single decision point the
  retired Gateway-relayed flow used;
- on success the response carries ``X-CBrowser-Authorized-Profile`` and a
  short-lived ``X-CBrowser-Viewer-Grant`` for Caddy to copy onto the
  proxied handshake. The Gateway verifies the grant locally; the session
  cookie never reaches it.
"""

from __future__ import annotations

import hmac
import logging
import re
from pathlib import Path
from typing import Annotated
from urllib.parse import unquote, urlsplit

from cbrowser.auth.dependencies import get_auth_service
from cbrowser.auth.service import AuthService
from cbrowser.secret_files import read_secret_file
from cbrowser.service_errors import ServiceNotConfiguredError
from cbrowser.shared.viewer_grants import (
    AUTHORIZED_PROFILE_HEADER,
    EDGE_PROOF_HEADER,
    VIEWER_GRANT_HEADER,
    ViewerGrantAuthority,
)
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import Response
from pydantic import SecretStr

logger = logging.getLogger("cbrowser.api.internal_edge")

_SIGNAL_URI = re.compile(r"^/stream/([^/]+)/signal$")


def read_edge_proof(path: Path | str | None) -> SecretStr | None:
    if path is None:
        return None
    return SecretStr(
        read_secret_file(path, label="Edge proof secret", minimum_bytes=32)
    )


edge_router = APIRouter(prefix="/api/v1/internal/edge", tags=["internal-edge"])


@edge_router.get("/viewer-authorize")
async def edge_viewer_authorize(
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    presented_proof: Annotated[
        str | None, Header(alias=EDGE_PROOF_HEADER)
    ] = None,
) -> Response:
    edge_proof: SecretStr | None = getattr(request.app.state, "edge_proof", None)
    grant_authority: ViewerGrantAuthority | None = getattr(
        request.app.state, "viewer_grant_authority", None
    )
    if edge_proof is None or grant_authority is None:
        raise ServiceNotConfiguredError("Edge authorization is not configured")

    presented = presented_proof or ""
    if not presented or not hmac.compare_digest(
        presented.encode("utf-8"),
        edge_proof.get_secret_value().encode("utf-8"),
    ):
        logger.warning("Edge viewer-authorize rejected: invalid edge proof")
        return Response(status_code=403)

    forwarded_uri = request.headers.get("X-Forwarded-Uri", "")
    match = _SIGNAL_URI.match(urlsplit(forwarded_uri).path)
    if match is None:
        logger.warning("Edge viewer-authorize rejected: non-signal forwarded URI")
        return Response(status_code=403)
    profile_id = unquote(match.group(1))

    session_cookie = request.cookies.get("cbrowser_session")
    if not session_cookie:
        return Response(status_code=401)

    allowed_origins = getattr(request.app.state, "allowed_origins", [])
    allowed, reason = await auth_service.authorize_viewer(
        session_token=session_cookie,
        origin=request.headers.get("Origin", ""),
        profile_id=profile_id,
        allowed_origins=allowed_origins,
    )
    if not allowed:
        return Response(status_code=401 if reason == "invalid_session" else 403)

    return Response(
        status_code=200,
        headers={
            AUTHORIZED_PROFILE_HEADER: profile_id,
            VIEWER_GRANT_HEADER: grant_authority.mint(profile_id),
        },
    )
