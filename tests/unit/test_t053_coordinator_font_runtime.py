"""t053 A19: Coordinator font runtime is read live, never cached.

- Deleting the bound font set is reported on the very next read
  (all detection fonts missing), with no restart and no stale cache.
- Damaging a font file is likewise visible on the next read.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cbrowser.domain.models import Profile, ProfileConfig
from cbrowser.font_sets import DETECTION_FONTS, import_font_set


def _profile(config: ProfileConfig) -> Profile:
    return Profile(
        id="p1",
        config=config,
        user_data_dir="/data/profiles/p1/profile",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


def _coordinator(service):
    from cbrowser.api.runtime_coordinator import RuntimeCoordinator

    return RuntimeCoordinator(
        supervisor_url=None,
        supervisor_token=None,
        profile_service=service,
        event_broadcaster=SimpleNamespace(publish=AsyncMock()),
    )


def _make_set(tmp_path: Path, platform: str = "windows") -> tuple[Path, str]:
    source = tmp_path / "src" / platform
    source.mkdir(parents=True, exist_ok=True)
    for name in ("arial.ttf", "calibri.ttf"):
        (source / name).write_bytes(b"font-bytes-" + name.encode("utf-8"))
    root = tmp_path / "fonts"
    result = import_font_set(platform, [source], "unit-1.0", root=root)
    return root, result["set_id"]


@pytest.mark.asyncio
async def test_deleted_set_reports_missing_without_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fonts_root, set_id = _make_set(tmp_path)
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(fonts_root))
    config = ProfileConfig(
        name="p1", fingerprint_platform="windows", font_set_id=set_id
    )
    service = SimpleNamespace(get_profile=AsyncMock(return_value=_profile(config)))
    coordinator = _coordinator(service)

    _, missing_before = await coordinator.get_font_runtime("p1")
    assert missing_before == sorted(
        name
        for name in DETECTION_FONTS["windows"] + DETECTION_FONTS["office"]
        if name not in ("arial.ttf", "calibri.ttf")
    )

    # The whole set directory disappears; the next read must say so.
    import shutil

    shutil.rmtree(fonts_root / "windows" / set_id)
    set_id_after, missing_after = await coordinator.get_font_runtime("p1")
    assert set_id_after == set_id
    assert missing_after == sorted(
        set(DETECTION_FONTS["windows"]) | set(DETECTION_FONTS["office"])
    )


@pytest.mark.asyncio
async def test_tampered_set_does_not_gain_detection_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A30 split: a tampered (hash-mismatched) file is an integrity failure,
    not a detection-coverage gap, so it must not appear in missing_fonts;
    the file is still present, only its content is wrong."""
    fonts_root, set_id = _make_set(tmp_path)
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(fonts_root))
    config = ProfileConfig(
        name="p1", fingerprint_platform="windows", font_set_id=set_id
    )
    service = SimpleNamespace(get_profile=AsyncMock(return_value=_profile(config)))
    coordinator = _coordinator(service)

    _, missing_before = await coordinator.get_font_runtime("p1")
    assert "arial.ttf" not in missing_before

    (fonts_root / "windows" / set_id / "arial.ttf").write_bytes(b"TAMPERED")
    _, missing_after = await coordinator.get_font_runtime("p1")
    assert "arial.ttf" not in missing_after

    # Deleting the file *is* a coverage gap and shows up immediately.
    (fonts_root / "windows" / set_id / "arial.ttf").unlink()
    _, missing_deleted = await coordinator.get_font_runtime("p1")
    assert "arial.ttf" in missing_deleted


@pytest.mark.asyncio
async def test_no_font_runtime_cache_attribute() -> None:
    """A19: the cache is gone, not merely bypassed."""
    coordinator = _coordinator(SimpleNamespace(get_profile=AsyncMock()))
    assert not hasattr(coordinator, "_font_runtime_cache")
