"""t089: wrapped profile config snapshot identity migration & 0014 compensation."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory

from cbrowser.adapters.database.migrations import (
    get_alembic_config,
    run_database_migrations,
)
from cbrowser.domain.models import ProfileConfig

REVISION_0012 = "c81f0a11b001"
REVISION_0013_PREDECESSOR = "d83a2c12b083"
REVISION_0013 = "d75a0013f001"
REVISION_LEGACY_HEAD = "d7e3a91f4c62"
REVISION_0014_COMPENSATION = "e89a0014c001"
# t094 appends the probe-job migration after the t089 head.
REVISION_HEAD = "f1a2b3c4d5e6"

WIN_SET = "1" * 64
MAC_SET = "2" * 64
BAD_SET = "9" * 64


def _insert_font_asset(
    conn: sqlite3.Connection,
    platform: str,
    set_id: str,
    *,
    state: str = "verified",
    verified_at: str | None = "2026-01-02T00:00:00+00:00",
) -> None:
    conn.execute(
        "INSERT INTO font_set_assets (platform, set_id, source, source_version,"
        " file_count, total_bytes, integrity, state, revision, state_seq,"
        " verified_at, audited_at, created_at, updated_at)"
        " VALUES (?, ?, 'test', 'v1', 4, 100, '{}', ?, 1, 1, ?, NULL,"
        " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
        (platform, set_id, state, verified_at),
    )


def _insert_pre_0013_profile(
    conn: sqlite3.Connection,
    profile_id: str,
    display_number: int,
    *,
    locale: str = "en-US",
    platform: str = "windows",
) -> None:
    conn.execute(
        "INSERT INTO profiles (id, name, fingerprint_seed, user_data_dir,"
        " created_at, updated_at, display_number, gpu_family, color_scheme,"
        " locale, fingerprint_platform, font_set_id)"
        " VALUES (?, ?, 1234, ?, '2026-01-01T00:00:00+00:00',"
        " '2026-01-01T00:00:00+00:00', ?, 'auto', NULL, ?, ?, NULL)",
        (profile_id, f"prof-{profile_id}", f"/data/profiles/{profile_id}", display_number, locale, platform),
    )


def _insert_post_0013_profile(
    conn: sqlite3.Connection,
    profile_id: str,
    display_number: int,
    *,
    locale: str = "en-US",
    platform: str = "windows",
    font_set_id: str = WIN_SET,
) -> None:
    conn.execute(
        "INSERT INTO profiles (id, name, fingerprint_seed, user_data_dir,"
        " created_at, updated_at, display_number, color_scheme, include_cjk_fonts,"
        " locale, fingerprint_platform, font_set_id)"
        " VALUES (?, ?, 1234, ?, '2026-01-01T00:00:00+00:00',"
        " '2026-01-01T00:00:00+00:00', ?, 'light', ?, ?, ?, ?)",
        (
            profile_id,
            f"prof-{profile_id}",
            f"/data/profiles/{profile_id}",
            display_number,
            0 if locale == "en-US" else 1,
            locale,
            platform,
            font_set_id,
        ),
    )


def _insert_version(
    conn: sqlite3.Connection,
    row_id: str,
    profile_id: str,
    version: int,
    snapshot: str,
) -> None:
    conn.execute(
        "INSERT INTO profile_config_versions (id, profile_id, version, snapshot, created_at)"
        " VALUES (?, ?, ?, ?, '2026-01-01T00:00:00+00:00')",
        (row_id, profile_id, version, snapshot),
    )


def _seed_pre_0013_db(db: Path) -> None:
    cfg = get_alembic_config(db)
    command.upgrade(cfg, REVISION_0013_PREDECESSOR)
    conn = sqlite3.connect(db)
    try:
        _insert_font_asset(conn, "windows", WIN_SET)
        _insert_font_asset(conn, "macos", MAC_SET)
        _insert_pre_0013_profile(conn, "p-wrap-en", 1, locale="en-US", platform="windows")
        _insert_pre_0013_profile(conn, "p-wrap-zh", 2, locale="zh-CN", platform="macos")
        _insert_pre_0013_profile(conn, "p-flat", 3, locale="zh-CN", platform="windows")
        _insert_version(
            conn,
            "v-wrap-en",
            "p-wrap-en",
            1,
            json.dumps(
                {
                    "config": {
                        "name": "Wrapped EN",
                        "fingerprint_seed": 42,
                        "gpu_family": "auto",
                        "color_scheme": None,
                        "locale": "en-US",
                        "fingerprint_platform": "windows",
                        "font_set_id": None,
                    },
                    "proxy_credential_revision": 7,
                }
            ),
        )
        _insert_version(
            conn,
            "v-wrap-zh",
            "p-wrap-zh",
            1,
            json.dumps(
                {
                    "config": {
                        "name": "Wrapped ZH",
                        "fingerprint_seed": 77,
                        "gpu_family": "auto",
                        "color_scheme": "no-preference",
                        "locale": "zh-CN",
                        "fingerprint_platform": "macos",
                        "font_set_id": None,
                    },
                    "proxy_credential_revision": None,
                }
            ),
        )
        _insert_version(
            conn,
            "v-flat",
            "p-flat",
            1,
            json.dumps(
                {
                    "name": "Flat Legacy",
                    "fingerprint_seed": 88,
                    "gpu_family": "auto",
                    "color_scheme": None,
                    "locale": "zh-CN",
                    "fingerprint_platform": "windows",
                    "font_set_id": None,
                }
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_0013_upgrades_wrapped_and_flat_snapshots_without_outer_pollution(
    tmp_path: Path,
) -> None:
    db = tmp_path / "pre0013.db"
    _seed_pre_0013_db(db)
    command.upgrade(get_alembic_config(db), REVISION_0013)

    conn = sqlite3.connect(db)
    try:
        rows = {
            row_id: json.loads(raw)
            for row_id, raw in conn.execute(
                "SELECT id, snapshot FROM profile_config_versions"
            ).fetchall()
        }
        wrap_en = rows["v-wrap-en"]
        assert set(wrap_en) == {"config", "proxy_credential_revision"}
        assert wrap_en["proxy_credential_revision"] == 7
        assert "gpu_family" not in wrap_en["config"]
        assert wrap_en["config"]["color_scheme"] == "light"
        assert wrap_en["config"]["include_cjk_fonts"] is False
        assert wrap_en["config"]["font_set_id"] == WIN_SET
        ProfileConfig.model_validate(wrap_en["config"])

        wrap_zh = rows["v-wrap-zh"]
        assert set(wrap_zh) == {"config", "proxy_credential_revision"}
        assert wrap_zh["proxy_credential_revision"] is None
        assert "gpu_family" not in wrap_zh["config"]
        assert wrap_zh["config"]["color_scheme"] == "light"
        assert wrap_zh["config"]["include_cjk_fonts"] is True
        assert wrap_zh["config"]["font_set_id"] == MAC_SET
        ProfileConfig.model_validate(wrap_zh["config"])

        flat = rows["v-flat"]
        assert "config" not in flat
        assert "gpu_family" not in flat
        assert flat["color_scheme"] == "light"
        assert flat["include_cjk_fonts"] is True
        assert flat["font_set_id"] == WIN_SET
        ProfileConfig.model_validate(flat)
    finally:
        conn.close()


@pytest.mark.parametrize(
    "bad_id,bad_payload,expected_fragment",
    [
        (
            "bad-gpu",
            json.dumps(
                {
                    "config": {
                        "name": "Bad GPU",
                        "fingerprint_seed": 11,
                        "gpu_family": "nvidia",
                        "color_scheme": None,
                        "locale": "en-US",
                        "fingerprint_platform": "windows",
                    },
                    "proxy_credential_revision": 2,
                }
            ),
            "gpu_family='nvidia'",
        ),
        (
            "bad-font",
            json.dumps(
                {
                    "config": {
                        "name": "Bad Font",
                        "fingerprint_seed": 12,
                        "gpu_family": "auto",
                        "color_scheme": "light",
                        "locale": "en-US",
                        "fingerprint_platform": "windows",
                        "font_set_id": BAD_SET,
                    },
                    "proxy_credential_revision": 3,
                }
            ),
            "not a verified windows font set",
        ),
        (
            "bad-nested-config",
            json.dumps({"config": "corrupt", "proxy_credential_revision": 1}),
            "nested config",
        ),
        (
            "bad-json",
            "{not-json",
            "corrupt",
        ),
    ],
)
def test_0013_blocks_nested_wrapped_unmappable_or_corrupt_before_write(
    tmp_path: Path,
    bad_id: str,
    bad_payload: str,
    expected_fragment: str,
) -> None:
    db = tmp_path / f"{bad_id}.db"
    _seed_pre_0013_db(db)
    conn = sqlite3.connect(db)
    try:
        before_wrap = conn.execute(
            "SELECT snapshot FROM profile_config_versions WHERE id = 'v-wrap-en'"
        ).fetchone()[0]
        _insert_version(conn, bad_id, "p-wrap-en", 2, bad_payload)
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(RuntimeError) as exc:
        command.upgrade(get_alembic_config(db), REVISION_0013)
    assert expected_fragment in str(exc.value)

    conn = sqlite3.connect(db)
    try:
        ver = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert ver == REVISION_0013_PREDECESSOR
        profile_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(profiles)").fetchall()
        }
        assert "gpu_family" in profile_cols
        assert "include_cjk_fonts" not in profile_cols
        after_wrap = conn.execute(
            "SELECT snapshot FROM profile_config_versions WHERE id = 'v-wrap-en'"
        ).fetchone()[0]
        assert after_wrap == before_wrap
    finally:
        conn.close()


def _seed_polluted_legacy_head_db(db: Path) -> None:
    cfg = get_alembic_config(db)
    command.upgrade(cfg, REVISION_LEGACY_HEAD)
    conn = sqlite3.connect(db)
    try:
        _insert_font_asset(conn, "windows", WIN_SET)
        _insert_font_asset(conn, "macos", MAC_SET)
        _insert_post_0013_profile(conn, "p-en", 1, locale="en-US", platform="windows", font_set_id=WIN_SET)
        _insert_post_0013_profile(conn, "p-mac", 2, locale="zh-CN", platform="macos", font_set_id=MAC_SET)
        _insert_version(
            conn,
            "v-polluted-en",
            "p-en",
            1,
            json.dumps(
                {
                    "config": {
                        "name": "Legacy EN",
                        "fingerprint_seed": 42,
                        "gpu_family": "auto",
                        "color_scheme": None,
                        "locale": "en-US",
                        "fingerprint_platform": "windows",
                        "font_set_id": None,
                    },
                    "proxy_credential_revision": 5,
                    "color_scheme": "light",
                    "include_cjk_fonts": True,
                    "font_set_id": WIN_SET,
                }
            ),
        )
        _insert_version(
            conn,
            "v-polluted-mac",
            "p-mac",
            1,
            json.dumps(
                {
                    "config": {
                        "name": "Legacy ZH Mac",
                        "fingerprint_seed": 77,
                        "gpu_family": "auto",
                        "color_scheme": "no-preference",
                        "locale": "zh-CN",
                        "fingerprint_platform": "macos",
                        "font_set_id": None,
                    },
                    "proxy_credential_revision": None,
                    "color_scheme": "light",
                    "include_cjk_fonts": True,
                    "font_set_id": WIN_SET,
                }
            ),
        )
        _insert_version(
            conn,
            "v-clean-v2",
            "p-en",
            2,
            json.dumps(
                {
                    "config": {
                        "name": "Clean V2",
                        "fingerprint_seed": 99,
                        "locale": "en-US",
                        "color_scheme": "dark",
                        "include_cjk_fonts": False,
                        "fingerprint_platform": "windows",
                        "font_set_id": WIN_SET,
                    },
                    "proxy_credential_revision": 9,
                }
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_compensation_0014_repairs_polluted_snapshots_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "legacy_head.db"
    _seed_polluted_legacy_head_db(db)
    en_dir = tmp_path / "user_data" / "p-en"
    mac_dir = tmp_path / "user_data" / "p-mac"
    (en_dir / "Default").mkdir(parents=True)
    (mac_dir / "Default").mkdir(parents=True)
    en_sentinel = en_dir / "Default" / "Preferences"
    mac_sentinel = mac_dir / "Default" / "Preferences"
    en_sentinel.write_bytes(b'{"profile":"en-sentinel"}')
    mac_sentinel.write_bytes(b'{"profile":"mac-sentinel"}')
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "UPDATE profiles SET user_data_dir = ? WHERE id = ?",
            (str(en_dir), "p-en"),
        )
        conn.execute(
            "UPDATE profiles SET user_data_dir = ? WHERE id = ?",
            (str(mac_dir), "p-mac"),
        )
        conn.commit()
    finally:
        conn.close()

    cfg = get_alembic_config(db)
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [REVISION_HEAD]

    run_database_migrations(db)

    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == REVISION_HEAD
        dirs = dict(conn.execute("SELECT id, user_data_dir FROM profiles").fetchall())
        assert dirs == {
            "p-en": str(en_dir),
            "p-mac": str(mac_dir),
        }
        assert en_sentinel.read_bytes() == b'{"profile":"en-sentinel"}'
        assert mac_sentinel.read_bytes() == b'{"profile":"mac-sentinel"}'
        rows = {
            row_id: json.loads(raw)
            for row_id, raw in conn.execute(
                "SELECT id, snapshot FROM profile_config_versions"
            ).fetchall()
        }
        en_v1 = rows["v-polluted-en"]
        assert set(en_v1) == {"config", "proxy_credential_revision"}
        assert en_v1["proxy_credential_revision"] == 5
        assert "gpu_family" not in en_v1["config"]
        assert en_v1["config"]["color_scheme"] == "light"
        assert en_v1["config"]["include_cjk_fonts"] is False
        assert en_v1["config"]["font_set_id"] == WIN_SET
        ProfileConfig.model_validate(en_v1["config"])

        mac_v1 = rows["v-polluted-mac"]
        assert set(mac_v1) == {"config", "proxy_credential_revision"}
        assert mac_v1["proxy_credential_revision"] is None
        assert "gpu_family" not in mac_v1["config"]
        assert mac_v1["config"]["color_scheme"] == "light"
        assert mac_v1["config"]["include_cjk_fonts"] is True
        assert mac_v1["config"]["font_set_id"] == MAC_SET
        ProfileConfig.model_validate(mac_v1["config"])

        clean_v2 = rows["v-clean-v2"]
        assert clean_v2["config"]["color_scheme"] == "dark"
        assert clean_v2["config"]["include_cjk_fonts"] is False
        assert clean_v2["proxy_credential_revision"] == 9

        raw_once = dict(
            conn.execute("SELECT id, snapshot FROM profile_config_versions").fetchall()
        )
    finally:
        conn.close()

    # Re-running 0014 / run_database_migrations must be idempotent.
    run_database_migrations(db)
    command.check(cfg)
    conn = sqlite3.connect(db)
    try:
        raw_twice = dict(
            conn.execute("SELECT id, snapshot FROM profile_config_versions").fetchall()
        )
        assert raw_twice == raw_once
    finally:
        conn.close()


def test_compensation_0014_blocks_unmappable_nested_entry_before_writes(
    tmp_path: Path,
) -> None:
    db = tmp_path / "blocked_0014.db"
    _seed_polluted_legacy_head_db(db)
    conn = sqlite3.connect(db)
    try:
        _insert_version(
            conn,
            "v-bad-nested",
            "p-en",
            3,
            json.dumps(
                {
                    "config": {
                        "name": "Bad GPU",
                        "fingerprint_seed": 55,
                        "gpu_family": "intel",
                        "color_scheme": None,
                        "locale": "en-US",
                        "fingerprint_platform": "windows",
                    },
                    "proxy_credential_revision": 1,
                    "color_scheme": "light",
                }
            ),
        )
        conn.commit()
        before = dict(
            conn.execute("SELECT id, snapshot FROM profile_config_versions").fetchall()
        )
    finally:
        conn.close()

    with pytest.raises(RuntimeError) as exc:
        run_database_migrations(db)
    assert "gpu_family='intel'" in str(exc.value)

    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == REVISION_LEGACY_HEAD
        after = dict(
            conn.execute("SELECT id, snapshot FROM profile_config_versions").fetchall()
        )
        assert after == before
    finally:
        conn.close()


def test_compensation_0014_allows_clean_post0013_db_with_null_and_failed_font_sets(
    tmp_path: Path,
) -> None:
    db = tmp_path / "clean_post0013.db"
    command.upgrade(get_alembic_config(db), REVISION_LEGACY_HEAD)
    conn = sqlite3.connect(db)
    try:
        _insert_font_asset(conn, "macos", MAC_SET, state="failed")
        _insert_post_0013_profile(
            conn,
            "p-no-font",
            1,
            locale="en-US",
            platform="windows",
            font_set_id="",
        )
        conn.execute("UPDATE profiles SET font_set_id = NULL WHERE id = 'p-no-font'")
        _insert_post_0013_profile(
            conn,
            "p-failed-font",
            2,
            locale="zh-CN",
            platform="macos",
            font_set_id=MAC_SET,
        )
        _insert_version(
            conn,
            "v-null-set",
            "p-no-font",
            1,
            json.dumps(
                {
                    "config": {
                        "name": "Created Without Fonts Dir",
                        "fingerprint_seed": 101,
                        "locale": "en-US",
                        "color_scheme": "light",
                        "include_cjk_fonts": False,
                        "fingerprint_platform": "windows",
                        "font_set_id": None,
                    },
                    "proxy_credential_revision": None,
                }
            ),
        )
        _insert_version(
            conn,
            "v-failed-set",
            "p-failed-font",
            1,
            json.dumps(
                {
                    "config": {
                        "name": "Later Failed Font Audit",
                        "fingerprint_seed": 202,
                        "locale": "zh-CN",
                        "color_scheme": "dark",
                        "include_cjk_fonts": True,
                        "fingerprint_platform": "macos",
                        "font_set_id": MAC_SET,
                    },
                    "proxy_credential_revision": 3,
                }
            ),
        )
        conn.commit()
        before = dict(
            conn.execute("SELECT id, snapshot FROM profile_config_versions").fetchall()
        )
    finally:
        conn.close()

    run_database_migrations(db)

    conn = sqlite3.connect(db)
    try:
        assert (
            conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == REVISION_HEAD
        )
        after = dict(
            conn.execute("SELECT id, snapshot FROM profile_config_versions").fetchall()
        )
        assert after == before
    finally:
        conn.close()


def test_pre_0013_wrapped_snapshots_upgrade_directly_to_head(tmp_path: Path) -> None:
    db = tmp_path / "pre0013_direct_head.db"
    _seed_pre_0013_db(db)

    run_database_migrations(db)

    conn = sqlite3.connect(db)
    try:
        assert (
            conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == REVISION_HEAD
        )
        rows = {
            row_id: json.loads(raw)
            for row_id, raw in conn.execute(
                "SELECT id, snapshot FROM profile_config_versions"
            ).fetchall()
        }
        assert set(rows["v-wrap-en"]) == {"config", "proxy_credential_revision"}
        assert rows["v-wrap-en"]["proxy_credential_revision"] == 7
        assert rows["v-wrap-en"]["config"]["font_set_id"] == WIN_SET
        ProfileConfig.model_validate(rows["v-wrap-en"]["config"])
        assert set(rows["v-wrap-zh"]) == {"config", "proxy_credential_revision"}
        assert rows["v-wrap-zh"]["config"]["font_set_id"] == MAC_SET
        ProfileConfig.model_validate(rows["v-wrap-zh"]["config"])
        assert "config" not in rows["v-flat"]
        ProfileConfig.model_validate(rows["v-flat"])
        raw_once = dict(
            conn.execute("SELECT id, snapshot FROM profile_config_versions").fetchall()
        )
    finally:
        conn.close()

    run_database_migrations(db)
    conn = sqlite3.connect(db)
    try:
        raw_twice = dict(
            conn.execute("SELECT id, snapshot FROM profile_config_versions").fetchall()
        )
        assert raw_twice == raw_once
    finally:
        conn.close()
