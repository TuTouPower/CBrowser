"""Shared API dependencies (kept separate to avoid router import cycles)."""

from __future__ import annotations

from cbrowser.services.profile_service import ProfileService


def get_profile_service() -> ProfileService:
    raise NotImplementedError("ProfileService dependency must be provided")
