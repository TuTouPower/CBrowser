"""Unit tests for the font-set API layer: default binding, binding
validation, usage counting, and config-version generation (t041
AC-002/AC-003)."""

from __future__ import annotations

from pathlib import Path

import pytest
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.models import ProfileConfig
from cbrowser.font_sets import import_font_set
from cbrowser.services.profile_service import (
    InvalidFontSetBindingError,
    ProfileService,
)


@pytest.fixture
def fonts(tmp_path: Path, monkeypatch):
    source = tmp_path / "src"
    source.mkdir()
    (source / "arial.ttf").write_bytes(b"FONT:arial")
    (source / "calibri.ttf").write_bytes(b"FONT:calibri")
    root = tmp_path / "fonts"
    result = import_font_set(
        "windows", [str(source)], "win11-test", root=str(root)
    )
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(root))
    return {
        "root": root,
        "source": source,
        "set_id": result["set_id"],
        "set_dir": Path(result["dir"]),
    }


def _services(db_context) -> tuple[ProfileService, ProfileRepository]:
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    return ProfileService(repo), repo


@pytest.mark.asyncio
async def test_create_binds_default_font_set(db_context, fonts) -> None:
    service, _ = _services(db_context)
    profile = await service.create_profile(
        config=ProfileConfig(name="Defaulted"),
        req_payload={"name": "Defaulted"},
    )
    assert profile.config.font_set_id == fonts["set_id"]


@pytest.mark.asyncio
async def test_create_without_font_sets_leaves_binding_null(
    db_context, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(tmp_path / "empty"))
    service, _ = _services(db_context)
    profile = await service.create_profile(
        config=ProfileConfig(name="NoSets"),
        req_payload={"name": "NoSets"},
    )
    assert profile.config.font_set_id is None


@pytest.mark.asyncio
async def test_create_rejects_unknown_font_set(db_context, fonts) -> None:
    service, _ = _services(db_context)
    with pytest.raises(InvalidFontSetBindingError):
        await service.create_profile(
            config=ProfileConfig(name="Unknown", font_set_id="0" * 64),
            req_payload={"name": "Unknown", "font_set_id": "0" * 64},
        )


@pytest.mark.asyncio
async def test_create_rejects_platform_mismatch(db_context, fonts) -> None:
    service, _ = _services(db_context)
    with pytest.raises(InvalidFontSetBindingError):
        await service.create_profile(
            config=ProfileConfig(
                name="Mismatch",
                fingerprint_platform="macos",
                font_set_id=fonts["set_id"],
            ),
            req_payload={"name": "Mismatch"},
        )


@pytest.mark.asyncio
async def test_create_rejects_tampered_font_set(db_context, fonts) -> None:
    (fonts["set_dir"] / "arial.ttf").write_bytes(b"TAMPERED")
    service, _ = _services(db_context)
    with pytest.raises(InvalidFontSetBindingError):
        await service.create_profile(
            config=ProfileConfig(name="Tampered", font_set_id=fonts["set_id"]),
            req_payload={"name": "Tampered"},
        )


@pytest.mark.asyncio
async def test_patch_binding_validation(db_context, fonts) -> None:
    service, _ = _services(db_context)
    profile = await service.create_profile(
        config=ProfileConfig(name="P"),
        req_payload={"name": "P"},
    )
    assert profile.config.font_set_id == fonts["set_id"]

    cleared = await service.update_profile(profile.id, {"font_set_id": None})
    assert cleared.config.font_set_id is None

    rebound = await service.update_profile(
        profile.id, {"font_set_id": fonts["set_id"]}
    )
    assert rebound.config.font_set_id == fonts["set_id"]

    with pytest.raises(InvalidFontSetBindingError):
        await service.update_profile(profile.id, {"font_set_id": "0" * 64})


@pytest.mark.asyncio
async def test_changing_font_fields_generates_config_versions(
    db_context, fonts
) -> None:
    service, repo = _services(db_context)
    profile = await service.create_profile(
        config=ProfileConfig(
            name="Versioned",
            fingerprint_platform="windows",
            font_set_id=fonts["set_id"],
        ),
        req_payload={"name": "Versioned"},
    )
    assert profile.current_config_version == 1
    assert [v.version for v in await repo.list_config_versions(profile.id)] == [1]

    cleared = await service.update_profile(profile.id, {"font_set_id": None})
    assert cleared.current_config_version == 2

    switched = await service.update_profile(
        profile.id, {"fingerprint_platform": "macos"}
    )
    assert switched.current_config_version == 3
    assert switched.config.fingerprint_platform == "macos"
    assert [
        v.version for v in await repo.list_config_versions(profile.id)
    ] == [1, 2, 3]


@pytest.mark.asyncio
async def test_font_set_usage_counts_groups_non_empty_bindings(
    db_context, fonts
) -> None:
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    assert await repo.font_set_usage_counts() == {}

    await repo.create_profile(
        ProfileConfig(name="Bound", font_set_id=fonts["set_id"])
    )
    await repo.create_profile(ProfileConfig(name="Unbound"))
    await repo.create_profile(
        ProfileConfig(name="Bound2", font_set_id=fonts["set_id"])
    )
    # t053 A20: counts are keyed by (fingerprint_platform, font_set_id);
    # the fixture profiles default to the windows platform.
    assert await repo.font_set_usage_counts() == {
        ("windows", fonts["set_id"]): 2
    }
