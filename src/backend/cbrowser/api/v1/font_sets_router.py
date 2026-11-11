"""Read-only API for content-addressed platform font sets (t041 AC-002)."""

from __future__ import annotations

import asyncio
from typing import Annotated
from weakref import WeakKeyDictionary

from cbrowser import font_sets
from cbrowser.api.v1.deps import get_profile_service
from cbrowser.auth.dependencies import require_user_session
from cbrowser.services.profile_service import ProfileService
from fastapi import APIRouter, Depends
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


class FontSetListResponse(BaseModel):
    """Font sets plus the backend-chosen default per platform (t053 A16).

    ``default_font_set_id`` is decided only by the backend, from the same
    integrity-ok rule as profile creation; the create form preselects it
    and never derives a default of its own.
    """

    items: list[FontSetInfo]
    default_font_set_id: dict[str, str | None] = Field(default_factory=dict)


font_set_router = APIRouter(
    prefix="/api/v1/font-sets",
    tags=["profiles"],
    dependencies=[Depends(require_user_session)],
)

Service = Annotated[ProfileService, Depends(get_profile_service)]

FONT_SCAN_CONCURRENCY = 2

_scan_semaphores: WeakKeyDictionary = WeakKeyDictionary()


def _scan_semaphore(loop: asyncio.AbstractEventLoop) -> asyncio.Semaphore:
    semaphore = _scan_semaphores.get(loop)
    if semaphore is None:
        semaphore = asyncio.Semaphore(FONT_SCAN_CONCURRENCY)
        _scan_semaphores[loop] = semaphore
    return semaphore


async def _collect_font_sets() -> list[dict]:
    loop = asyncio.get_running_loop()
    async with _scan_semaphore(loop):
        return await asyncio.to_thread(font_sets.list_font_sets)


@font_set_router.get("", response_model=FontSetListResponse)
async def list_font_sets(service: Service) -> FontSetListResponse:
    usage = await service.font_set_usage_counts()
    items = await _collect_font_sets()
    return FontSetListResponse(
        items=[
            FontSetInfo(
                platform=item["platform"],
                set_id=item["set_id"],
                source=item.get("source"),
                source_version=item.get("source_version"),
                created_at=item.get("created_at"),
                integrity=FontSetIntegrity(**item["integrity"]),
                file_count=item["file_count"],
                used_by_count=usage.get((item["platform"], item["set_id"]), 0),
            )
            for item in items
        ],
        default_font_set_id={
            platform: font_sets.pick_default_font_set(items, platform)
            for platform in font_sets.PLATFORMS
        },
    )
