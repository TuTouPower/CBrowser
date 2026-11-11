"""Proxy CRUD API (t035 AC-004 / AC-005 / AC-006)."""

from __future__ import annotations

from typing import Annotated

from cbrowser.api.v1.deps import get_profile_service
from cbrowser.auth.dependencies import require_csrf_and_origin
from cbrowser.domain.models import (
    ProxyCreateRequest,
    ProxyResponse,
    ProxyUpdateRequest,
)
from cbrowser.api.v1.runtime_views import (
    publish_reference_change,
    resolve_operation_id,
)
from cbrowser.services.profile_service import ProfileService
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

proxy_router = APIRouter(
    prefix="/proxies",
    tags=["proxies"],
    dependencies=[Depends(require_csrf_and_origin)],
)

Service = Annotated[ProfileService, Depends(get_profile_service)]


@proxy_router.get("", response_model=list[ProxyResponse])
async def list_proxies(service: Service):
    return await service.list_proxies()


@proxy_router.post("", response_model=ProxyResponse, status_code=status.HTTP_201_CREATED)
async def create_proxy(
    payload: ProxyCreateRequest,
    request: Request,
    service: Service,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_operation_id: Annotated[str | None, Header(alias="X-Operation-ID")] = None,
    operation_id: Annotated[str | None, Query()] = None,
):
    op_id = resolve_operation_id(idempotency_key, x_operation_id, operation_id)
    try:
        created = await service.create_proxy(payload, operation_id=op_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "proxy_name_in_use", "message": str(exc)},
        ) from None
    publish_reference_change(request, "proxies_changed", created.id)
    return created


@proxy_router.get("/{proxy_id}", response_model=ProxyResponse)
async def get_proxy(proxy_id: str, service: Service):
    proxy = await service.get_proxy(proxy_id)
    if proxy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proxy {proxy_id} not found",
        )
    return proxy


@proxy_router.patch("/{proxy_id}", response_model=ProxyResponse)
async def update_proxy(
    proxy_id: str,
    payload: ProxyUpdateRequest,
    request: Request,
    service: Service,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_operation_id: Annotated[str | None, Header(alias="X-Operation-ID")] = None,
    operation_id: Annotated[str | None, Query()] = None,
):
    op_id = resolve_operation_id(idempotency_key, x_operation_id, operation_id)
    try:
        proxy, versioned, runtime_only = await service.update_proxy(
            proxy_id, payload, operation_id=op_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "proxy_name_in_use", "message": str(exc)},
        ) from None
    if proxy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proxy {proxy_id} not found",
        )
    coordinator = getattr(request.app.state, "coordinator", None)
    if coordinator is not None:
        # t056 A17: versioned profiles get a new config version; bound-only
        # profiles get a runtime event only — both are notified over SSE so
        # the frontend refreshes their runtime state.
        for pid in [*versioned, *runtime_only]:
            coordinator.publish_profile_change_later(pid)
    # t056 A31: the proxy reference itself changed for every list client.
    publish_reference_change(request, "proxies_changed", proxy_id)
    return proxy


@proxy_router.post(
    "/{proxy_id}/probe", response_model=ProxyResponse
)
async def probe_proxy(proxy_id: str, request: Request, service: Service):
    """Manual egress probe (t052 AC-006/AC-009).

    The request carries no body: only the proxy id is accepted, and the
    stored endpoint + credentials are loaded server-side, so a caller can
    never redirect the stored password to another host, port, scheme or
    username.  Any request body is rejected (AC-009 negative path).
    """
    body = await request.body()
    if body and body.strip() not in (b"", b"{}"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="probe accepts only the proxy id; no request body allowed",
        )
    proxy = await service.probe_proxy_egress(proxy_id)
    if proxy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proxy {proxy_id} not found",
        )
    return proxy


@proxy_router.delete("/{proxy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proxy(
    proxy_id: str,
    request: Request,
    service: Service,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_operation_id: Annotated[str | None, Header(alias="X-Operation-ID")] = None,
    operation_id: Annotated[str | None, Query()] = None,
):
    op_id = resolve_operation_id(idempotency_key, x_operation_id, operation_id)
    deleted, used_by = await service.delete_proxy(proxy_id, operation_id=op_id)
    if not deleted and used_by:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "proxy_in_use", "used_by_count": used_by},
        )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proxy {proxy_id} not found",
        )
    publish_reference_change(request, "proxies_changed", proxy_id)
