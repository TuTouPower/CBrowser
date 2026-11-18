"""Unit tests for the font-set API layer: default binding, binding
validation, usage counting, and config-version generation (t041
AC-002/AC-003; binding semantics revised by t075: the binding is
backend-managed, creation without an available set fails, and the
binding can no longer be cleared through an update)."""

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


async def _adopted_services(db_context):
    """t081: profile binding reads the asset catalog, so a published set
    becomes bindable through adoption (the API startup path), exactly as
    in production.  Assertions below are unchanged from the filesystem
    era; only the setup gains the adoption step."""
    service, repo = _services(db_context)
    await service.font_catalog().adopt_all()
    return service, repo


@pytest.mark.asyncio
async def test_create_binds_default_font_set(db_context, fonts) -> None:
    service, _ = await _adopted_services(db_context)
    profile = await service.create_profile(
        config=ProfileConfig(name="Defaulted"),
        req_payload={"name": "Defaulted"},
    )
    assert profile.config.font_set_id == fonts["set_id"]


@pytest.mark.asyncio
async def test_create_without_font_sets_fails(
    db_context, tmp_path, monkeypatch
) -> None:
    """t075 rewrite of ``test_create_without_font_sets_leaves_binding_null``:
    an unbound profile is no longer a legal outcome — with no verified
    set for the platform, creation fails before anything is written."""
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(tmp_path / "empty"))
    service, repo = await _adopted_services(db_context)
    with pytest.raises(InvalidFontSetBindingError):
        await service.create_profile(
            config=ProfileConfig(name="NoSets"),
            req_payload={"name": "NoSets"},
        )
    assert await repo.list_profiles() == []


@pytest.mark.asyncio
async def test_create_rejects_unknown_font_set(db_context, fonts) -> None:
    service, _ = await _adopted_services(db_context)
    with pytest.raises(InvalidFontSetBindingError):
        await service.create_profile(
            config=ProfileConfig(name="Unknown", font_set_id="0" * 64),
            req_payload={"name": "Unknown", "font_set_id": "0" * 64},
        )


@pytest.mark.asyncio
async def test_create_rejects_platform_mismatch(db_context, fonts) -> None:
    service, _ = await _adopted_services(db_context)
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
    service, _ = await _adopted_services(db_context)
    with pytest.raises(InvalidFontSetBindingError):
        await service.create_profile(
            config=ProfileConfig(name="Tampered", font_set_id=fonts["set_id"]),
            req_payload={"name": "Tampered"},
        )


@pytest.mark.asyncio
async def test_patch_binding_validation(db_context, fonts) -> None:
    """t075: the binding can no longer be cleared — a null font_set_id
    patch is rejected and the managed binding survives; a patch naming
    the platform's verified set is accepted, an unknown one rejected.
    (The HTTP layer forbids the field outright via ProfileUpdateRequest;
    the service keeps validating direct patches as a second fence.)"""
    service, _ = await _adopted_services(db_context)
    profile = await service.create_profile(
        config=ProfileConfig(name="P"),
        req_payload={"name": "P"},
    )
    assert profile.config.font_set_id == fonts["set_id"]

    with pytest.raises(InvalidFontSetBindingError):
        await service.update_profile(profile.id, {"font_set_id": None})
    unchanged = await service.get_profile(profile.id)
    assert unchanged.config.font_set_id == fonts["set_id"]

    rebound = await service.update_profile(
        profile.id, {"font_set_id": fonts["set_id"]}
    )
    assert rebound.config.font_set_id == fonts["set_id"]

    with pytest.raises(InvalidFontSetBindingError):
        await service.update_profile(profile.id, {"font_set_id": "0" * 64})


@pytest.mark.asyncio
async def test_changing_identity_fields_generates_config_versions(
    db_context, fonts
) -> None:
    """t075 rewrite of ``test_changing_font_fields_generates_config_versions``:
    clearing the binding and switching to a set-less platform are no
    longer legal moves, so version generation is proven on the fields
    that remain runtime identity inputs — the CJK switch and the color
    scheme."""
    service, repo = await _adopted_services(db_context)
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

    toggled = await service.update_profile(
        profile.id, {"include_cjk_fonts": False}
    )
    assert toggled.current_config_version == 2
    assert toggled.config.include_cjk_fonts is False

    recolored = await service.update_profile(
        profile.id, {"color_scheme": "dark"}
    )
    assert recolored.current_config_version == 3
    assert recolored.config.color_scheme == "dark"
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
