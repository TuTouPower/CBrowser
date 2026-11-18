"""Font set API over the t081 asset catalog.

Listing and defaults read catalog metadata recorded at verification
time — no filesystem scan and no font-byte hashing on any read path.
The only verification trigger exposed here is the explicit audit:
bounded, deduplicated, off the event loop, and fenced so a late
verdict cannot overwrite newer catalog state.
"""

from __future__ import annotations

from typing import Annotated

from cbrowser import font_sets
from cbrowser.api.v1.deps import get_profile_service
from cbrowser.auth.dependencies import require_user_session
from cbrowser.services.profile_service import ProfileService
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field


class FontDetection(BaseModel):
    total: int
    matched: int
    missing: list[str]


class FontSetIntegrity(BaseModel):
    ok: bool
    problems: list[str] = Field(default_factory=list)
    missing_fonts: list[str] = Field(default_factory=list)
    hash_mismatches: list[str] = Field(default_factory=list)
    unregistered_fonts: list[str] = Field(default_factory=list)
    file_count: int = 0
    detection: dict[str, FontDetection] = Field(default_factory=dict)


class FontSetInfo(BaseModel):
    platform: str
    set_id: str
    source: str | None = None
    source_version: str | None = None
    created_at: str | None = None
    integrity: FontSetIntegrity
    file_count: int
    used_by_count: int = 0
    state: str
    revision: int
    verified_at: str | None
    audited_at: str | None


class FontSetListResponse(BaseModel):
    """Font sets plus the backend-chosen default per platform.

    ``default_font_set_id`` is decided only by the backend, from the
    catalog's verified records; the create form preselects it and never
    derives a default of its own.
    """

    items: list[FontSetInfo]
    default_font_set_id: dict[str, str | None] = Field(default_factory=dict)


class FontSetAuditResponse(BaseModel):
    platform: str
    set_id: str
    status: str


font_set_router = APIRouter(
    prefix="/api/v1/font-sets",
    tags=["profiles"],
    dependencies=[Depends(require_user_session)],
)

Service = Annotated[ProfileService, Depends(get_profile_service)]


def _integrity(record) -> FontSetIntegrity:
    stored = record.integrity or {}
    return FontSetIntegrity(
        ok=record.verified,
        problems=list(stored.get("problems", [])),
        missing_fonts=list(stored.get("missing_fonts", [])),
        hash_mismatches=list(stored.get("hash_mismatches", [])),
        unregistered_fonts=list(stored.get("unregistered_fonts", [])),
        file_count=record.file_count,
        detection=dict(stored.get("detection", {})),
    )


@font_set_router.get("", response_model=FontSetListResponse)
async def list_font_sets(service: Service) -> FontSetListResponse:
    catalog = service.font_catalog()
    usage = await service.font_set_usage_counts()
    records = await catalog.list_assets()
    return FontSetListResponse(
        items=[
            FontSetInfo(
                platform=record.platform,
                set_id=record.set_id,
                source=record.source,
                source_version=record.source_version,
                created_at=record.created_at,
                integrity=_integrity(record),
                file_count=record.file_count,
                used_by_count=usage.get((record.platform, record.set_id), 0),
                state=record.state,
                revision=record.revision,
                verified_at=record.verified_at,
                audited_at=record.audited_at,
            )
            for record in records
        ],
        default_font_set_id={
            platform: await catalog.default_set_id(platform)
            for platform in font_sets.PLATFORMS
        },
    )


@font_set_router.post(
    "/{platform}/{set_id}/audit",
    response_model=FontSetAuditResponse,
    status_code=202,
)
async def audit_font_set(
    platform: str, set_id: str, service: Service
) -> FontSetAuditResponse:
    """Schedule an explicit audit of one published set.

    Returns ``in_flight`` when an audit for the same set is already
    running (requests are deduplicated, never queued twice); the
    verdict lands in the catalog when the audit completes.
    """
    if platform not in font_sets.PLATFORMS or not font_sets.manifest.SET_ID_PATTERN.fullmatch(
        set_id
    ):
        raise HTTPException(status_code=404, detail="font set not found")
    status = await service.font_catalog().request_audit(platform, set_id)
    return FontSetAuditResponse(platform=platform, set_id=set_id, status=status)
