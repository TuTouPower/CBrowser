"""Read-only API for content-addressed platform font sets (t041 AC-002)."""

from __future__ import annotations

from typing import Annotated

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


font_set_router = APIRouter(
    prefix="/api/v1/font-sets",
    tags=["profiles"],
    dependencies=[Depends(require_user_session)],
)

Service = Annotated[ProfileService, Depends(get_profile_service)]


@font_set_router.get("", response_model=list[FontSetInfo])
async def list_font_sets(service: Service) -> list[FontSetInfo]:
    usage = await service.font_set_usage_counts()
    return [
        FontSetInfo(
            platform=item["platform"],
            set_id=item["set_id"],
            source=item.get("source"),
            source_version=item.get("source_version"),
            created_at=item.get("created_at"),
            integrity=FontSetIntegrity(**item["integrity"]),
            file_count=item["file_count"],
            used_by_count=usage.get(item["set_id"], 0),
        )
        for item in font_sets.list_font_sets()
    ]
