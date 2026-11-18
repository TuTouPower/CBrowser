"""t075: unified runtime identity contract (domain + service layer).

New semantics proven here:
- Profiles no longer carry a user-chosen font package or GPU vendor:
  ``font_set_id`` is a backend-managed binding resolved from the t081
  catalog by platform, and ``gpu_family`` is gone entirely (the fixed
  engine derives GPU identity from the persistent seed + platform,
  spike s026).
- ``color_scheme`` is exactly ``light`` / ``dark`` with default
  ``light``; the old ``null`` / ``no-preference`` states are abolished.
- ``include_cjk_fonts`` is an explicit switch decoupled from locale:
  Chinese locales default to on, English locales default to off, and
  either can be overridden explicitly.
- Creating a profile for a platform with no verified font set fails
  instead of silently starting on Linux base fonts.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cbrowser.adapters.database.font_repository import FontSetRepository
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.models import (
    ProfileConfig,
    ProfileCreateRequest,
    ProfileUpdateRequest,
)
from cbrowser.domain.profile_locale import default_include_cjk_fonts
from cbrowser.font_sets import import_font_set
from cbrowser.services.font_set_catalog import FontSetCatalogService
from cbrowser.services.profile_service import (
    InvalidFontSetBindingError,
    ProfileService,
)
from pydantic import ValidationError

FONT_NAMES = ("arial.ttf", "calibri.ttf", "cour.ttf", "tahoma.ttf")


def _source(tmp_path: Path, platform: str) -> Path:
    source = tmp_path / f"src-{platform}"
    source.mkdir(parents=True, exist_ok=True)
    for name in FONT_NAMES:
        # Per-platform bytes: identical content across platforms would
        # hash to the same set_id and make the platform-switch rebind
        # assertion vacuous.
        (source / name).write_bytes(b"FONT:" + platform.encode() + name.encode() * 64)
    return source


async def _verified_catalog(db_context, tmp_path: Path, *platforms: str):
    """Publish + adopt one verified set per platform; return (catalog, ids)."""
    _engine, session_maker = db_context
    root = tmp_path / "fonts"
    catalog = FontSetCatalogService(FontSetRepository(session_maker), fonts_root=root)
    ids: dict[str, str] = {}
    for platform in platforms:
        result = import_font_set(
            platform, [str(_source(tmp_path, platform))], "v1", root=str(root)
        )
        ids[platform] = result["set_id"]
    await catalog.adopt_all()
    return catalog, ids


def _service(db_context, catalog: FontSetCatalogService) -> ProfileService:
    _engine, session_maker = db_context
    service = ProfileService(ProfileRepository(session_maker))
    service.set_font_catalog(catalog)
    return service


# --- domain shape -----------------------------------------------------------


def test_create_request_rejects_removed_fields() -> None:
    with pytest.raises(ValidationError):
        ProfileCreateRequest(name="x", gpu_family="nvidia")
    with pytest.raises(ValidationError):
        ProfileCreateRequest(name="x", font_set_id="a" * 64)


def test_update_request_rejects_removed_fields() -> None:
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(gpu_family="intel")
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(font_set_id=None)


def test_color_scheme_is_binary_with_light_default() -> None:
    assert ProfileCreateRequest(name="x").color_scheme == "light"
    assert ProfileConfig(name="x").color_scheme == "light"
    with pytest.raises(ValidationError):
        ProfileCreateRequest(name="x", color_scheme="no-preference")
    with pytest.raises(ValidationError):
        ProfileCreateRequest(name="x", color_scheme=None)
    with pytest.raises(ValidationError):
        ProfileConfig(name="x", color_scheme="no-preference")


def test_config_has_no_gpu_family() -> None:
    assert "gpu_family" not in ProfileConfig.model_fields
    with pytest.raises(ValidationError):
        ProfileConfig(name="x", gpu_family="auto")


def test_include_cjk_defaults_follow_language() -> None:
    assert default_include_cjk_fonts("zh-CN") is True
    assert default_include_cjk_fonts("en-US") is False
    assert default_include_cjk_fonts(None) is False


# --- service binding --------------------------------------------------------


@pytest.mark.asyncio
async def test_create_binds_platform_default_set(db_context, tmp_path: Path) -> None:
    catalog, ids = await _verified_catalog(db_context, tmp_path, "windows")
    service = _service(db_context, catalog)
    profile = await service.create_profile(
        ProfileConfig(name="p", fingerprint_platform="windows")
    )
    assert profile.config.font_set_id == ids["windows"]


@pytest.mark.asyncio
async def test_create_fails_without_available_platform_set(
    db_context, tmp_path: Path
) -> None:
    catalog, _ids = await _verified_catalog(db_context, tmp_path, "windows")
    service = _service(db_context, catalog)
    with pytest.raises(InvalidFontSetBindingError):
        await service.create_profile(
            ProfileConfig(name="p", fingerprint_platform="macos")
        )


@pytest.mark.asyncio
async def test_create_preserves_explicit_verified_binding(
    db_context, tmp_path: Path
) -> None:
    """Clone/duplicate carries an existing binding: a verified set id on
    the incoming config is kept, not replaced by the platform default."""
    catalog, ids = await _verified_catalog(db_context, tmp_path, "windows")
    service = _service(db_context, catalog)
    profile = await service.create_profile(
        ProfileConfig(
            name="clone",
            fingerprint_platform="windows",
            font_set_id=ids["windows"],
        )
    )
    assert profile.config.font_set_id == ids["windows"]


@pytest.mark.asyncio
async def test_create_rejects_unverified_binding(db_context, tmp_path: Path) -> None:
    catalog, _ids = await _verified_catalog(db_context, tmp_path, "windows")
    service = _service(db_context, catalog)
    with pytest.raises(InvalidFontSetBindingError):
        await service.create_profile(
            ProfileConfig(
                name="p",
                fingerprint_platform="windows",
                font_set_id="b" * 64,
            )
        )


@pytest.mark.asyncio
async def test_platform_switch_rebinds_to_new_platform_default(
    db_context, tmp_path: Path
) -> None:
    catalog, ids = await _verified_catalog(db_context, tmp_path, "windows", "macos")
    service = _service(db_context, catalog)
    profile = await service.create_profile(
        ProfileConfig(name="p", fingerprint_platform="windows")
    )
    updated = await service.update_profile(
        profile.id, {"fingerprint_platform": "macos"}
    )
    assert updated.config.fingerprint_platform == "macos"
    assert updated.config.font_set_id == ids["macos"]


@pytest.mark.asyncio
async def test_platform_switch_fails_without_target_set(
    db_context, tmp_path: Path
) -> None:
    catalog, _ids = await _verified_catalog(db_context, tmp_path, "windows")
    service = _service(db_context, catalog)
    profile = await service.create_profile(
        ProfileConfig(name="p", fingerprint_platform="windows")
    )
    with pytest.raises(InvalidFontSetBindingError):
        await service.update_profile(profile.id, {"fingerprint_platform": "macos"})
    unchanged = await service.get_profile(profile.id)
    assert unchanged.config.fingerprint_platform == "windows"


@pytest.mark.asyncio
async def test_identity_fields_round_trip(db_context, tmp_path: Path) -> None:
    catalog, ids = await _verified_catalog(db_context, tmp_path, "windows")
    service = _service(db_context, catalog)
    profile = await service.create_profile(
        ProfileConfig(
            name="p",
            fingerprint_platform="windows",
            color_scheme="dark",
            include_cjk_fonts=False,
            locale="zh-CN",
        )
    )
    fetched = await service.get_profile(profile.id)
    assert fetched.config.color_scheme == "dark"
    assert fetched.config.include_cjk_fonts is False
    assert fetched.config.font_set_id == ids["windows"]
    snapshot = await service.get_config_version(profile.id, 1)
    assert snapshot is not None
    assert snapshot.config["color_scheme"] == "dark"
    assert snapshot.config["include_cjk_fonts"] is False
    assert "gpu_family" not in snapshot.config


@pytest.mark.asyncio
async def test_ordinary_config_change_keeps_user_data_and_binding(
    db_context, tmp_path: Path
) -> None:
    """t075 review f004 (AC-008, second half): changing an ordinary
    config field must not clear cookies, site data or the login
    session — i.e. the browser user-data directory the profile points
    at is left byte-identical, and the font binding is untouched."""
    catalog, ids = await _verified_catalog(db_context, tmp_path, "windows")
    service = _service(db_context, catalog)
    profile = await service.create_profile(
        ProfileConfig(
            name="p",
            fingerprint_platform="windows",
            color_scheme="light",
            locale="en-US",
        )
    )
    user_data = Path(profile.user_data_dir)
    user_data.mkdir(parents=True, exist_ok=True)
    cookies = user_data / "Cookies"
    cookies.write_bytes(b"session-bytes")
    login_state = user_data / "Login Data"
    login_state.write_bytes(b"login-bytes")

    updated = await service.update_profile(
        profile.id, {"color_scheme": "dark"}
    )
    assert updated.config.color_scheme == "dark"
    assert updated.config.font_set_id == ids["windows"]
    assert updated.current_config_version == 2
    assert cookies.read_bytes() == b"session-bytes"
    assert login_state.read_bytes() == b"login-bytes"
    fetched = await service.get_profile(profile.id)
    assert fetched.config.font_set_id == ids["windows"]
