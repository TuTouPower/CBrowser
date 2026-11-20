"""Proxy CRUD API (t035 AC-004 / AC-005 / AC-006)."""

from __future__ import annotations

from typing import Annotated

from cbrowser.api.v1.deps import get_profile_service
from cbrowser.auth.dependencies import require_csrf_and_origin
from cbrowser.domain.models import (
    CandidateEntry,
    CollectionPage,
    ProxyCandidateEntry,
    ProxyCountryRange,
    ProxyCreateRequest,
    ProxyProbeJob,
    ProxyProbeJobAccepted,
    ProxyProbeJobRequest,
    ProxyResponse,
    ProxyUpdateRequest,
    ProxyUsedByResponse,
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


@proxy_router.get("/collection", response_model=CollectionPage[ProxyResponse])
async def list_proxies_collection(
    service: Service,
    search: Annotated[str | None, Query(max_length=255)] = None,
    country_code: Annotated[str | None, Query(max_length=8)] = None,
    city: Annotated[str | None, Query(max_length=255)] = None,
    scheme: Annotated[str | None, Query(pattern="^(http|https|socks5)$")] = None,
    sort: Annotated[str, Query(pattern="^(default|name)$")] = "default",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=1000)] = 50,
):
    """t076 AC-001/AC-006: bounded server-side proxy page; country/city
    filter by the stable country code from egress observations."""
    return await service.list_proxies_page(
        search=search,
        country_code=country_code,
        city=city,
        scheme=scheme,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@proxy_router.get("/candidates", response_model=list[ProxyCandidateEntry])
async def list_proxy_candidates(
    service: Service,
    search: Annotated[str, Query(max_length=255)] = "",
    limit: Annotated[int, Query(ge=1, le=500)] = 20,
):
    """t076 AC-006: bounded name/host search over proxies."""
    return await service.list_proxy_candidates(search=search, limit=limit)


@proxy_router.get("/countries", response_model=list[ProxyCountryRange])
async def list_proxy_countries(service: Service):
    """t076 AC-006: stable country -> city ranges from observations."""
    return await service.proxy_country_ranges()


@proxy_router.get("/{proxy_id}/used-by", response_model=ProxyUsedByResponse)
async def get_proxy_used_by(proxy_id: str, service: Service):
    """t076 AC-004: used-by detail with kind labels, same union as the
    count and delete protection."""
    entries = await service.get_proxy_used_by(proxy_id)
    if entries is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proxy {proxy_id} not found",
        )
    return ProxyUsedByResponse(proxy_id=proxy_id, entries=entries)


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
    "/probe-jobs", response_model=ProxyProbeJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_probe_job(
    payload: ProxyProbeJobRequest,
    service: Service,
):
    """Submit a server-owned probe job (t094).

    The target set is resolved to explicit proxy ids and frozen before any
    work runs; submission returns immediately. Both the global "probe all"
    and the per-row button use this endpoint (the latter with one id).
    """
    proxy_ids: list[str]
    if payload.proxy_ids is not None:
        proxy_ids = list(dict.fromkeys(payload.proxy_ids))
    else:
        proxy_ids = await service.list_proxy_ids_for_filters(
            search=payload.filters.search if payload.filters else None,
            country_code=payload.filters.country_code if payload.filters else None,
            city=payload.filters.city if payload.filters else None,
            scheme=payload.filters.scheme if payload.filters else None,
        )
    return await service.request_probe_jobs(proxy_ids)


@proxy_router.get("/probe-jobs/{job_id}", response_model=ProxyProbeJob)
async def get_probe_job(job_id: str, service: Service):
    job = await service.get_probe_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Probe job {job_id} not found",
        )
    return job


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
