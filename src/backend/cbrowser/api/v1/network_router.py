"""Network Settings, Apply Operations, and Root CA Download Router."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse

from cbrowser.adapters.database.models import SessionModel
from cbrowser.auth.dependencies import require_csrf_and_origin, require_user_session
from cbrowser.domain.models import (
    NetworkAccessConfig,
    NetworkAccessSettingsResponse,
    NetworkApplyOperation,
    NetworkApplyRequest,
)
from cbrowser.services.network_service import NetworkService

logger = logging.getLogger("cbrowser.api.network_router")


def get_network_service(request: Request) -> NetworkService:
    svc = getattr(request.app.state, "network_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Network service is not configured",
        )
    return svc


def create_network_router() -> APIRouter:
    router = APIRouter(prefix="/network", tags=["network"])

    @router.get(
        "/settings",
        response_model=NetworkAccessSettingsResponse,
    )
    async def get_network_settings(
        session: Annotated[SessionModel, Depends(require_user_session)],
        service: Annotated[NetworkService, Depends(get_network_service)],
    ) -> NetworkAccessSettingsResponse:
        return await service.get_settings()

    @router.put(
        "/settings",
        response_model=dict[str, str],
        dependencies=[Depends(require_csrf_and_origin)],
    )
    async def update_network_settings(
        config: NetworkAccessConfig,
        session: Annotated[SessionModel, Depends(require_user_session)],
        service: Annotated[NetworkService, Depends(get_network_service)],
    ) -> dict[str, str]:
        await service.update_pending_config(config)
        return {"status": "ok"}

    @router.post(
        "/apply",
        response_model=NetworkApplyOperation,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_csrf_and_origin)],
    )
    async def apply_network_configuration(
        body: NetworkApplyRequest,
        request: Request,
        session: Annotated[SessionModel, Depends(require_user_session)],
        service: Annotated[NetworkService, Depends(get_network_service)],
    ) -> NetworkApplyOperation:
        try:
            client_host = request.headers.get("host", "")
            return await service.apply_configuration(
                body.admin_password,
                current_request_host=client_host,
            )
        except PermissionError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e),
            ) from e
        except RuntimeError as e:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e),
            ) from e

    @router.get(
        "/operations/{operation_id}",
        response_model=NetworkApplyOperation,
    )
    async def get_apply_operation(
        operation_id: str,
        session: Annotated[SessionModel, Depends(require_user_session)],
        service: Annotated[NetworkService, Depends(get_network_service)],
    ) -> NetworkApplyOperation:
        op = await service.get_operation(operation_id)
        if op is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Operation not found",
            )
        return op

    @router.get(
        "/check-disconnect",
        response_model=dict[str, Any],
    )
    async def check_disconnect(
        request: Request,
        session: Annotated[SessionModel, Depends(require_user_session)],
        service: Annotated[NetworkService, Depends(get_network_service)],
    ) -> dict[str, Any]:
        client_host = request.headers.get("host", "127.0.0.1")
        settings = await service.get_settings()
        will_disconnect, new_url = service.check_entry_disconnect(
            client_host, settings.pending_config
        )
        return {
            "will_disconnect": will_disconnect,
            "new_entry_url": new_url,
        }

    @router.get(
        "/root-ca",
        response_class=PlainTextResponse,
    )
    async def download_root_ca(
        request: Request,
    ) -> Response:
        """Download public root CA certificate only (AC-008). No private keys."""
        caddy_ca_dir = getattr(
            request.app.state,
            "caddy_ca_dir",
            Path("/data/caddy/pki/authorities/local"),
        )
        ca_cert_path = caddy_ca_dir / "root.crt"

        if not ca_cert_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Root CA certificate not available",
            )

        content = ca_cert_path.read_text(encoding="utf-8")
        return Response(
            content=content,
            media_type="application/x-x509-ca-cert",
            headers={
                "Content-Disposition": 'attachment; filename="cbrowser_root_ca.crt"',
                "Cache-Control": "no-store",
            },
        )

    return router
