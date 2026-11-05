"""t020: per-profile CJK font bundles (domain, repository, migration, runner).

Covers the non-Docker halves of AC-002/AC-005 plus the fontconfig generation
contract behind AC-003/AC-004. Real Browser/Chrome rendering assertions live
in tests/e2e/test_browser_font_bundles_e2e.py.

t035: the 0001-0009 migration chain was replaced by a single baseline.  The
two legacy-row migration tests (0006 -> 0007) were deleted wholesale, not
rewritten to the new output; see the "Baseline schema" section for the
reason and the replacement test.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest
from cbrowser.adapters.database.migrations import get_alembic_config
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.models import (
    ProfileConfig,
    ProfileCreateRequest,
    ProfileUpdateRequest,
)
from cbrowser.runtime_agent import fontconfig as fontconfig_module
from cbrowser.runtime_agent.fontconfig import (
    FONT_BUNDLE_ROOT,
    build_fontconfig_xml,
    prepare_profile_fontconfig,
)
from cbrowser.runtime_agent.runner import BrowserRunner
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Domain / DTO validation (AC-002)
# ---------------------------------------------------------------------------


def test_profile_config_defaults_to_no_cjk_bundle() -> None:
    assert ProfileConfig(name="p").font_bundle == "none"


@pytest.mark.parametrize("bundle", ["none", "wqy-microhei", "wqy-zenhei"])
def test_profile_config_accepts_the_three_bundles(bundle: str) -> None:
    assert ProfileConfig(name="p", font_bundle=bundle).font_bundle == bundle


def test_profile_config_rejects_unknown_bundle() -> None:
    with pytest.raises(ValidationError):
        ProfileConfig(name="p", font_bundle="noto-sans-cjk")


def test_profile_config_rejects_null_bundle() -> None:
    with pytest.raises(ValidationError):
        ProfileConfig(name="p", font_bundle=None)


def test_create_request_font_bundle_default_and_validation() -> None:
    assert ProfileCreateRequest(name="p").font_bundle == "none"
    assert (
        ProfileCreateRequest(name="p", font_bundle="wqy-zenhei").font_bundle
        == "wqy-zenhei"
    )
    with pytest.raises(ValidationError):
        ProfileCreateRequest(name="p", font_bundle="simsun")


def test_update_request_font_bundle_validation() -> None:
    assert ProfileUpdateRequest(font_bundle="wqy-microhei").font_bundle == (
        "wqy-microhei"
    )
    assert ProfileUpdateRequest().font_bundle is None
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(font_bundle="simsun")
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(font_bundle=None)


# ---------------------------------------------------------------------------
# Repository round-trip and config versioning (AC-002, AC-005)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repository_roundtrips_font_bundle(db_context) -> None:
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    created = await repo.create_profile(
        ProfileConfig(name="fonts", font_bundle="wqy-microhei")
    )
    assert created.config.font_bundle == "wqy-microhei"

    fetched = await repo.get_profile(created.id)
    assert fetched is not None
    assert fetched.config.font_bundle == "wqy-microhei"

    defaulted = await repo.create_profile(ProfileConfig(name="plain"))
    assert defaulted.config.font_bundle == "none"


@pytest.mark.asyncio
async def test_update_font_bundle_creates_new_config_version(db_context) -> None:
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    target = await repo.create_profile(ProfileConfig(name="target"))
    bystander = await repo.create_profile(
        ProfileConfig(name="bystander", font_bundle="wqy-microhei")
    )
    assert target.current_config_version == 1

    updated = await repo.update_profile(
        target.id, patch_data={"font_bundle": "wqy-zenhei"}
    )
    assert updated is not None
    assert updated.config.font_bundle == "wqy-zenhei"
    assert updated.current_config_version == 2

    versions = await repo.list_config_versions(target.id)
    assert [v.version for v in versions] == [1, 2]
    assert versions[0].config["font_bundle"] == "none"
    assert versions[1].config["font_bundle"] == "wqy-zenhei"

    untouched = await repo.get_profile(bystander.id)
    assert untouched is not None
    assert untouched.config.font_bundle == "wqy-microhei"
    assert untouched.current_config_version == 1


# ---------------------------------------------------------------------------
# Baseline schema (t035): font_bundle column + default (AC-001/AC-002)
# ---------------------------------------------------------------------------
# The two old tests here migrated an 0006-style database up to 0007 to
# prove the font_bundle column was added and legacy rows defaulted to
# "none".  The 0001-0009 chain is gone; there is no pre-font_bundle
# revision to upgrade from, so those tests and their _insert_legacy_profile
# helper were deleted wholesale (not rewritten to the new output).  The
# baseline schema ships the column directly, covered by the test below.


def test_baseline_schema_defaults_font_bundle_to_none(tmp_path: Path) -> None:
    from alembic import command

    db_path = tmp_path / "baseline_fonts.db"
    cfg = get_alembic_config(db_path)
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO profiles "
            "(id, name, fingerprint_seed, user_data_dir, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "baseline_profile_1",
                "plain",
                1,
                "/data/profiles/baseline_profile_1/profile",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT font_bundle FROM profiles WHERE id = 'baseline_profile_1'"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("none",)


# ---------------------------------------------------------------------------
# Fontconfig generation (AC-003 / AC-004 mechanism)
# ---------------------------------------------------------------------------


def _xml_dirs(xml_text: str) -> set[str]:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_text)
    return {element.text or "" for element in root.iter("dir")}


def _xml_includes(xml_text: str) -> set[str]:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_text)
    return {element.text or "" for element in root.iter("include")}


def test_fontconfig_xml_includes_system_config_and_only_the_bundle_dir() -> None:
    micro = build_fontconfig_xml("wqy-microhei")
    assert _xml_includes(micro) == {"/etc/fonts/fonts.conf"}
    # Exact set equality: an ancestor dir (e.g. the bundle root itself)
    # would silently expose every bundle and break per-profile isolation.
    assert _xml_dirs(micro) == {f"{FONT_BUNDLE_ROOT}/wqy-microhei"}

    zen = build_fontconfig_xml("wqy-zenhei")
    assert _xml_includes(zen) == {"/etc/fonts/fonts.conf"}
    assert _xml_dirs(zen) == {f"{FONT_BUNDLE_ROOT}/wqy-zenhei"}


def test_fontconfig_xml_rejects_none_and_unknown_bundles() -> None:
    with pytest.raises(ValueError):
        build_fontconfig_xml("none")
    with pytest.raises(ValueError):
        build_fontconfig_xml("simsun")


def test_prepare_fontconfig_none_writes_nothing(tmp_path: Path) -> None:
    assert prepare_profile_fontconfig(tmp_path, "none") is None
    assert list(tmp_path.iterdir()) == []


def test_prepare_fontconfig_none_removes_stale_generated_file(
    tmp_path: Path,
) -> None:
    generated = prepare_profile_fontconfig(tmp_path, "wqy-microhei")
    assert generated is not None and generated.exists()
    assert prepare_profile_fontconfig(tmp_path, "none") is None
    assert not generated.exists()


def test_prepare_fontconfig_unknown_bundle_falls_back_to_none(
    tmp_path: Path,
) -> None:
    assert prepare_profile_fontconfig(tmp_path, "simsun") is None
    assert list(tmp_path.iterdir()) == []


def test_prepare_fontconfig_writes_bundle_file(tmp_path: Path) -> None:
    path = prepare_profile_fontconfig(tmp_path, "wqy-microhei")
    assert path is not None
    assert path.parent == tmp_path
    content = path.read_text(encoding="utf-8")
    assert _xml_dirs(content) == {f"{FONT_BUNDLE_ROOT}/wqy-microhei"}


def test_font_bundle_dirs_live_outside_default_scan_paths() -> None:
    # AC-001 invariant on the layout constants: bundles sit under /opt, never
    # inside fontconfig's compiled-in default scan directories.
    assert str(FONT_BUNDLE_ROOT).startswith("/opt/")
    for default_dir in ("/usr/share/fonts", "/usr/local/share/fonts"):
        assert not str(FONT_BUNDLE_ROOT).startswith(default_dir)
    assert fontconfig_module.FONT_BUNDLE_DIRS == {
        "wqy-microhei": FONT_BUNDLE_ROOT / "wqy-microhei",
        "wqy-zenhei": FONT_BUNDLE_ROOT / "wqy-zenhei",
    }


# ---------------------------------------------------------------------------
# Browser image layout (AC-001, static half; fc-list half is E2E)
# ---------------------------------------------------------------------------


def test_browser_dockerfile_stages_bundles_outside_default_scan_paths() -> None:
    dockerfile = (
        Path(__file__).resolve().parents[2]
        / "config"
        / "docker"
        / "browser_runtime"
        / "Dockerfile"
    ).read_text(encoding="utf-8")
    assert "fonts-wqy-microhei" in dockerfile
    assert "fonts-wqy-zenhei" in dockerfile
    assert "/opt/cbrowser-fonts/wqy-microhei" in dockerfile
    assert "/opt/cbrowser-fonts/wqy-zenhei" in dockerfile
    assert "COPY --from=font_bundle_builder /opt/cbrowser-fonts" in dockerfile
    # The final image must not install the packages (that would drop the
    # fonts and their fontconfig snippets into the default scan paths).
    final_stage = dockerfile.split("AS font_bundle_builder", 1)[1]
    final_stage = final_stage.split("\nFROM ", 1)[1]
    assert "fonts-wqy" not in final_stage
    assert "/usr/share/fonts" not in final_stage


# ---------------------------------------------------------------------------
# Runner environment wiring (AC-003 / AC-004 / AC-005 mechanism)
# ---------------------------------------------------------------------------


def _make_runner(root: Path, font_bundle: str) -> BrowserRunner:
    snapshot = root / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "id": "snapshot_fonts",
                "profile_id": "profile_fonts",
                "version": 1,
                "config": {"name": "Font runner", "font_bundle": font_bundle},
                "created_at": "2026-11-04T00:00:00+08:00",
            }
        )
    )
    return BrowserRunner(
        "profile_fonts",
        "instance_fonts",
        snapshot,
        root / "runtime",
        root / "profile",
        events_dir=root / "events",
        engine_cache_dir=root / "engine_cache",
    )


def test_runner_env_omits_fontconfig_file_for_none_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FONTCONFIG_FILE", "/preset/elsewhere.conf")
    runner = _make_runner(tmp_path, "none")
    run_dir = tmp_path / "runtime"
    env = runner._browser_environment(
        run_dir / "pulse.sock",
        run_dir / "pulse.cookie",
        run_dir / "chrome_wrapper.sh",
        fontconfig_path=prepare_profile_fontconfig(run_dir, "none"),
    )
    assert "FONTCONFIG_FILE" not in env
    assert os.environ["FONTCONFIG_FILE"] == "/preset/elsewhere.conf"


def test_runner_env_points_fontconfig_file_at_generated_config(
    tmp_path: Path,
) -> None:
    runner = _make_runner(tmp_path, "wqy-zenhei")
    run_dir = tmp_path / "runtime"
    run_dir.mkdir(parents=True)
    generated = prepare_profile_fontconfig(run_dir, "wqy-zenhei")
    env = runner._browser_environment(
        run_dir / "pulse.sock",
        run_dir / "pulse.cookie",
        run_dir / "chrome_wrapper.sh",
        fontconfig_path=generated,
    )
    assert generated is not None
    assert env["FONTCONFIG_FILE"] == str(generated)
    assert "wqy-zenhei" in generated.read_text(encoding="utf-8")
