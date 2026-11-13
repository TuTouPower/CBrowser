"""t053 A16/A19/A20: font-set import repair, platform isolation, defaults.

- A19: a damaged set is repaired by re-importing the original fonts
  (atomic replacement); an intact set is left untouched.
- A20: usage counts are per (platform, set_id); a list entry whose
  manifest platform disagrees with its directory is an integrity failure.
- A16: the service only applies the backend default font set when the
  caller did not supply font_set_id at all; an explicit null stays null.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.models import ProfileConfig
from cbrowser.font_sets import (
    check_font_set,
    import_font_set,
    list_font_sets,
)
from cbrowser.services.profile_service import ProfileService


@pytest.fixture
def font_source(tmp_path: Path) -> Path:
    source = tmp_path / "src"
    source.mkdir()
    (source / "arial.ttf").write_bytes(b"FONT:arial")
    (source / "calibri.ttf").write_bytes(b"FONT:calibri")
    return source


def test_reimport_repairs_deleted_font(font_source: Path, tmp_path: Path) -> None:
    root = tmp_path / "fonts"
    first = import_font_set("windows", [str(font_source)], "v1", root=str(root))
    set_dir = Path(first["dir"])
    assert first["created"] is True
    assert check_font_set(set_dir)["ok"] is True

    (set_dir / "arial.ttf").unlink()
    assert check_font_set(set_dir)["ok"] is False

    repaired = import_font_set("windows", [str(font_source)], "v1", root=str(root))
    assert repaired["set_id"] == first["set_id"]
    assert repaired["created"] is True
    assert check_font_set(set_dir)["ok"] is True
    assert (set_dir / "arial.ttf").read_bytes() == b"FONT:arial"


def test_reimport_repairs_tampered_font(font_source: Path, tmp_path: Path) -> None:
    root = tmp_path / "fonts"
    first = import_font_set("windows", [str(font_source)], "v1", root=str(root))
    set_dir = Path(first["dir"])
    (set_dir / "calibri.ttf").write_bytes(b"TAMPERED")
    assert check_font_set(set_dir)["ok"] is False

    repaired = import_font_set("windows", [str(font_source)], "v1", root=str(root))
    assert repaired["set_id"] == first["set_id"]
    assert check_font_set(set_dir)["ok"] is True
    assert (set_dir / "calibri.ttf").read_bytes() == b"FONT:calibri"


def test_reimport_leaves_intact_set_untouched(
    font_source: Path, tmp_path: Path
) -> None:
    root = tmp_path / "fonts"
    first = import_font_set("windows", [str(font_source)], "v1", root=str(root))
    marker = Path(first["dir"]) / "arial.ttf"
    before = marker.stat().st_mtime_ns
    second = import_font_set("windows", [str(font_source)], "v1", root=str(root))
    assert second["created"] is False
    assert second["set_id"] == first["set_id"]
    assert marker.stat().st_mtime_ns == before


def test_list_flags_manifest_platform_mismatch(
    font_source: Path, tmp_path: Path
) -> None:
    root = tmp_path / "fonts"
    result = import_font_set("windows", [str(font_source)], "v1", root=str(root))
    set_dir = Path(result["dir"])
    manifest_path = set_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["platform"] = "macos"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    items = list_font_sets(root=str(root))
    assert len(items) == 1
    assert items[0]["platform"] == "windows"
    assert items[0]["integrity"]["ok"] is False
    assert any("platform" in p for p in items[0]["integrity"]["problems"])


def test_list_accepts_matching_manifest_platform(
    font_source: Path, tmp_path: Path
) -> None:
    root = tmp_path / "fonts"
    import_font_set("windows", [str(font_source)], "v1", root=str(root))
    items = list_font_sets(root=str(root))
    assert len(items) == 1
    assert items[0]["integrity"]["ok"] is True


def test_list_accepts_manifest_without_platform_field(
    font_source: Path, tmp_path: Path
) -> None:
    # A manifest that carries no platform claim is not a mismatch: only
    # a present-but-different platform fails the A20 check (t027/t051
    # fixtures build valid sets without the field).
    root = tmp_path / "fonts"
    result = import_font_set("windows", [str(font_source)], "v1", root=str(root))
    set_dir = Path(result["dir"])
    manifest_path = set_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["platform"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    items = list_font_sets(root=str(root))
    assert len(items) == 1
    assert items[0]["integrity"]["ok"] is True
    assert not any("platform" in p for p in items[0]["integrity"]["problems"])


@pytest.mark.asyncio
async def test_usage_counts_are_per_platform(
    db_context, font_source: Path, tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "fonts"
    win = import_font_set("windows", [str(font_source)], "v1", root=str(root))
    mac = import_font_set("macos", [str(font_source)], "v1", root=str(root))
    # Content-addressed ids are platform-independent: the same content
    # yields the same set_id under both platforms.
    assert win["set_id"] == mac["set_id"]
    set_id = win["set_id"]

    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    await repo.create_profile(
        ProfileConfig(
            name="Win", fingerprint_platform="windows", font_set_id=set_id
        )
    )
    await repo.create_profile(
        ProfileConfig(
            name="Mac", fingerprint_platform="macos", font_set_id=set_id
        )
    )
    await repo.create_profile(
        ProfileConfig(
            name="Mac2", fingerprint_platform="macos", font_set_id=set_id
        )
    )
    await repo.create_profile(ProfileConfig(name="Unbound"))
    assert await repo.font_set_usage_counts() == {
        ("windows", set_id): 1,
        ("macos", set_id): 2,
    }


def _services(db_context):
    _engine, session_maker = db_context
    return ProfileService(ProfileRepository(session_maker))


@pytest.mark.asyncio
async def test_create_applies_default_only_when_font_set_omitted(
    db_context, font_source: Path, tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "fonts"
    result = import_font_set("windows", [str(font_source)], "v1", root=str(root))
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(root))
    service = _services(db_context)

    omitted = await service.create_profile(
        config=ProfileConfig(name="Omitted"),
        req_payload={"name": "Omitted"},
    )
    assert omitted.config.font_set_id == result["set_id"]

    explicit_none = await service.create_profile(
        config=ProfileConfig(name="ExplicitNone"),
        req_payload={"name": "ExplicitNone", "font_set_id": None},
        font_set_id_supplied=True,
    )
    assert explicit_none.config.font_set_id is None


@pytest.mark.asyncio
async def test_create_with_supplied_set_keeps_it(
    db_context, font_source: Path, tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "fonts"
    result = import_font_set("windows", [str(font_source)], "v1", root=str(root))
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(root))
    service = _services(db_context)
    profile = await service.create_profile(
        config=ProfileConfig(name="Bound", font_set_id=result["set_id"]),
        req_payload={"name": "Bound", "font_set_id": result["set_id"]},
        font_set_id_supplied=True,
    )
    assert profile.config.font_set_id == result["set_id"]
