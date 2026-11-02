"""FastAPI authentication and CSRF/Origin validation dependencies."""

from __future__ import annotations

import hmac
from typing import Annotated
from urllib.parse import urlsplit

from cbrowser.adapters.database.models import SessionModel
from cbrowser.auth.service import AuthService
from cbrowser.gateway.endpoint import normalize_origin
from fastapi import Depends, HTTPException, Request, status


def get_auth_service(request: Request) -> AuthService:
    service = getattr(request.app.state, "auth_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not configured",
        )
    return service


async def require_user_session(
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionModel:
    """Validate that the request carries an active cbrowser_session cookie."""
    session_token = request.cookies.get("cbrowser_session")
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    session = await auth_service.get_valid_session(session_token)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    request.state.session = session
    return session


async def require_csrf_and_origin(
    request: Request,
    session: Annotated[SessionModel, Depends(require_user_session)],
) -> SessionModel:
    """Validate user session and verify CSRF token and allowed Origin for writes."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        # 1. CSRF Verification
        csrf_token = request.headers.get("x-csrf-token")
        if not csrf_token or not hmac.compare_digest(csrf_token, session.csrf_token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid CSRF token",
            )

        # 2. Origin Verification
        origin = request.headers.get("origin")
        if not origin:
            referer = request.headers.get("referer")
            if referer:
                parsed = urlsplit(referer)
                if parsed.scheme and parsed.netloc:
                    origin = f"{parsed.scheme}://{parsed.netloc}"

        allowed_origins = getattr(request.app.state, "allowed_origins", [])
        try:
            clean_origin = normalize_origin(origin) if origin else ""
        except ValueError:
            clean_origin = ""
        if not clean_origin or clean_origin not in allowed_origins:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Origin not allowed",
            )

    return session
