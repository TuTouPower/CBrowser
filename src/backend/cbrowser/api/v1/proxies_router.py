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
from cbrowser.services.profile_service import ProfileService
from fastapi import APIRouter, Depends, HTTPException, Request, status

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
async def create_proxy(payload: ProxyCreateRequest, service: Service):
    try:
        return await service.create_proxy(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "proxy_name_in_use", "message": str(exc)},
        ) from None


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
):
    try:
        proxy, affected = await service.update_proxy(proxy_id, payload)
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
        for pid in affected:
            coordinator.publish_profile_change_later(pid)
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
async def delete_proxy(proxy_id: str, service: Service):
    deleted, used_by = await service.delete_proxy(proxy_id)
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
