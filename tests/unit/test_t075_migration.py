"""t075 AC-004: profile identity migration (alembic 0013).

Old-shape databases are rewritten to the single new identity shape:
gpu_family dropped, color_scheme converged to light/dark, the CJK
switch backfilled from the old effective exposure, unbound profiles
bound to the platform catalog default, and config-version snapshots
rewritten in step.  Entries that cannot be mapped equivalently block
the upgrade *before* anything is written, with an itemised list.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory

from cbrowser.adapters.database.migrations import get_alembic_config

REVISION_0012 = "c81f0a11b001"
REVISION_0013 = "d75a0013f001"
# t083's runtime_state_revision: numbered 0013 on its own branch; on
# main the merge-time rechain puts it between REVISION_0012 and this
# migration, so an upgrade blocked by this migration's guard stops
# stamped at this predecessor revision.
REVISION_PREDECESSOR_ON_MAIN = "d83a2c12b083"

WIN_SET = "a" * 64
MAC_SET = "b" * 64
FAILED_SET = "c" * 64


def _build_old_db(db: Path) -> None:
    cfg = get_alembic_config(db)
    command.upgrade(cfg, REVISION_0012)


def _insert_asset(
    conn: sqlite3.Connection,
    platform: str,
    set_id: str,
    state: str,
    verified_at: str | None,
) -> None:
    conn.execute(
        "INSERT INTO font_set_assets (platform, set_id, source, source_version,"
        " file_count, total_bytes, integrity, state, revision, state_seq,"
        " verified_at, audited_at, created_at, updated_at)"
        " VALUES (?, ?, 'test', 'v1', 4, 100, '{}', ?, 1, 1, ?, NULL,"
        " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
        (platform, set_id, state, verified_at),
    )


_DISPLAY_SEQ = [100]


def _insert_profile(
    conn: sqlite3.Connection,
    profile_id: str,
    *,
    gpu_family: str = "auto",
    color_scheme: str | None = None,
    locale: str | None = "en-US",
    platform: str = "windows",
    font_set_id: str | None = None,
) -> None:
    _DISPLAY_SEQ[0] += 1
    conn.execute(
        "INSERT INTO profiles (id, name, fingerprint_seed, user_data_dir,"
        " created_at, updated_at, display_number, gpu_family, color_scheme,"
        " locale, fingerprint_platform, font_set_id)"
        " VALUES (?, ?, 1234, ?, '2026-01-01T00:00:00+00:00',"
        " '2026-01-01T00:00:00+00:00', ?, ?, ?, ?, ?, ?)",
        (
            profile_id,
            f"name-{profile_id}",
            f"/data/{profile_id}",
            _DISPLAY_SEQ[0],
            gpu_family,
            color_scheme,
            locale,
            platform,
            font_set_id,
        ),
    )


def _seed_clean_db(db: Path) -> None:
    _build_old_db(db)
    conn = sqlite3.connect(db)
    try:
        _insert_asset(conn, "windows", WIN_SET, "verified", "2026-01-02T00:00:00+00:00")
        _insert_asset(conn, "macos", MAC_SET, "verified", "2026-01-02T00:00:00+00:00")
        _insert_asset(conn, "windows", FAILED_SET, "failed", None)
        _insert_profile(conn, "p-en-unbound")
        _insert_profile(
            conn,
            "p-zh-bound",
            color_scheme="no-preference",
            locale="zh-CN",
            font_set_id=WIN_SET,
        )
        _insert_profile(
            conn,
            "p-mac-dark",
            color_scheme="dark",
            locale=None,
            platform="macos",
            font_set_id=MAC_SET,
        )
        conn.execute(
            "INSERT INTO profile_config_versions (id, profile_id, version,"
            " snapshot, created_at) VALUES ('v1', 'p-en-unbound', 1, ?,"
            " '2026-01-01T00:00:00+00:00')",
            (
                json.dumps(
                    {
                        "name": "name-p-en-unbound",
                        "gpu_family": "auto",
                        "color_scheme": None,
                        "locale": "en-US",
                        "fingerprint_platform": "windows",
                        "font_set_id": None,
                        "fingerprint_seed": 1234,
                    }
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _columns(conn: sqlite3.Connection, table: str) -> dict[str, dict]:
    return {
        row[1]: {"notnull": bool(row[3]), "default": row[4]}
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _version(conn: sqlite3.Connection) -> str:
    return conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def test_head_is_0013_and_single(tmp_path: Path) -> None:
    cfg = get_alembic_config(tmp_path / "head.db")
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == [REVISION_0013]


def test_upgrade_rewrites_profiles_and_snapshots(tmp_path: Path) -> None:
    db = tmp_path / "clean.db"
    _seed_clean_db(db)
    command.upgrade(get_alembic_config(db), "head")

    conn = sqlite3.connect(db)
    try:
        assert _version(conn) == REVISION_0013
        cols = _columns(conn, "profiles")
        assert "gpu_family" not in cols
        assert cols["include_cjk_fonts"]["notnull"] is True
        assert cols["color_scheme"]["notnull"] is True

        rows = {
            row[0]: row[1:]
            for row in conn.execute(
                "SELECT id, color_scheme, include_cjk_fonts, font_set_id"
                " FROM profiles"
            ).fetchall()
        }
        # en-US unbound: bound to the windows default, CJK off, light.
        assert rows["p-en-unbound"] == ("light", 0, WIN_SET)
        # zh-CN bound: binding kept, CJK on, no-preference -> light.
        assert rows["p-zh-bound"] == ("light", 1, WIN_SET)
        # NULL locale was never CJK-rejected: CJK on, dark preserved.
        assert rows["p-mac-dark"] == ("dark", 1, MAC_SET)

        snapshot = json.loads(
            conn.execute(
                "SELECT snapshot FROM profile_config_versions WHERE id='v1'"
            ).fetchone()[0]
        )
        assert "gpu_family" not in snapshot
        assert snapshot["color_scheme"] == "light"
        assert snapshot["include_cjk_fonts"] is False
        assert snapshot["font_set_id"] == WIN_SET
        assert snapshot["fingerprint_seed"] == 1234
    finally:
        conn.close()


def test_upgrade_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "clean.db"
    _seed_clean_db(db)
    cfg = get_alembic_config(db)
    command.upgrade(cfg, "head")
    conn = sqlite3.connect(db)
    before = conn.execute("SELECT * FROM profiles ORDER BY id").fetchall()
    snap_before = conn.execute(
        "SELECT snapshot FROM profile_config_versions"
    ).fetchall()
    conn.close()
    command.upgrade(cfg, "head")
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT * FROM profiles ORDER BY id").fetchall() == before
        assert (
            conn.execute("SELECT snapshot FROM profile_config_versions").fetchall()
            == snap_before
        )
    finally:
        conn.close()


def test_forced_gpu_blocks_before_any_write(tmp_path: Path) -> None:
    db = tmp_path / "blocked.db"
    _build_old_db(db)
    conn = sqlite3.connect(db)
    _insert_asset(conn, "windows", WIN_SET, "verified", "2026-01-02T00:00:00+00:00")
    _insert_profile(conn, "p-nvidia", gpu_family="nvidia")
    _insert_profile(conn, "p-clean")
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError) as excinfo:
        command.upgrade(get_alembic_config(db), "head")
    assert "p-nvidia" in str(excinfo.value)
    assert "nvidia" in str(excinfo.value)

    conn = sqlite3.connect(db)
    try:
        # This migration wrote nothing: still stamped at its on-main
        # predecessor, old shape and values intact.
        assert _version(conn) == REVISION_PREDECESSOR_ON_MAIN
        assert "gpu_family" in _columns(conn, "profiles")
        assert "include_cjk_fonts" not in _columns(conn, "profiles")
        row = conn.execute(
            "SELECT color_scheme, font_set_id FROM profiles WHERE id='p-clean'"
        ).fetchone()
        assert row == (None, None)
    finally:
        conn.close()


def test_dangling_binding_blocks(tmp_path: Path) -> None:
    db = tmp_path / "dangling.db"
    _build_old_db(db)
    conn = sqlite3.connect(db)
    _insert_asset(conn, "windows", WIN_SET, "verified", "2026-01-02T00:00:00+00:00")
    _insert_profile(conn, "p-dangling", font_set_id=FAILED_SET)
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError) as excinfo:
        command.upgrade(get_alembic_config(db), "head")
    assert "p-dangling" in str(excinfo.value)


def test_unbound_without_platform_set_blocks(tmp_path: Path) -> None:
    db = tmp_path / "noset.db"
    _build_old_db(db)
    conn = sqlite3.connect(db)
    _insert_profile(conn, "p-mac-unbound", platform="macos")
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError) as excinfo:
        command.upgrade(get_alembic_config(db), "head")
    assert "p-mac-unbound" in str(excinfo.value)


def test_backup_restore_drill(tmp_path: Path) -> None:
    db = tmp_path / "drill.db"
    _seed_clean_db(db)
    backup = tmp_path / "drill-backup.db"
    shutil.copyfile(db, backup)

    # Browser user data is outside the database; the migration must
    # never touch it, on upgrade or on restore.
    user_data = tmp_path / "userdata"
    user_data.mkdir()
    sentinel = user_data / "Cookies"
    sentinel.write_bytes(b"session-bytes")
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE profiles SET user_data_dir = ? WHERE id='p-zh-bound'",
        (str(user_data),),
    )
    conn.commit()
    conn.close()

    command.upgrade(get_alembic_config(db), "head")
    conn = sqlite3.connect(db)
    assert _version(conn) == REVISION_0013
    conn.close()
    assert sentinel.read_bytes() == b"session-bytes"

    # Restore = put the pre-upgrade file back; the old shape returns
    # wholesale (config, bindings and version stamp alike).
    shutil.copyfile(backup, db)
    conn = sqlite3.connect(db)
    try:
        assert _version(conn) == REVISION_0012
        assert "gpu_family" in _columns(conn, "profiles")
        row = conn.execute(
            "SELECT gpu_family, font_set_id FROM profiles WHERE id='p-zh-bound'"
        ).fetchone()
        assert row == ("auto", WIN_SET)
    finally:
        conn.close()
    assert sentinel.read_bytes() == b"session-bytes"


def _insert_snapshot(
    conn: sqlite3.Connection,
    row_id: str,
    profile_id: str,
    snapshot: str,
) -> None:
    conn.execute(
        "INSERT INTO profile_config_versions (id, profile_id, version,"
        " snapshot, created_at) VALUES (?, ?, 1, ?,"
        " '2026-01-01T00:00:00+00:00')",
        (row_id, profile_id, snapshot),
    )


def test_snapshot_forced_gpu_blocks(tmp_path: Path) -> None:
    # t075 review code f001: a historical version that forced a GPU
    # vendor blocks the upgrade just like a live profile row does.
    db = tmp_path / "snap-gpu.db"
    _build_old_db(db)
    conn = sqlite3.connect(db)
    _insert_asset(conn, "windows", WIN_SET, "verified", "2026-01-02T00:00:00+00:00")
    _insert_profile(conn, "p-clean")
    _insert_snapshot(
        conn,
        "v-old",
        "p-clean",
        json.dumps(
            {
                "name": "name-p-clean",
                "gpu_family": "nvidia",
                "color_scheme": "light",
                "locale": "en-US",
                "fingerprint_platform": "windows",
                "font_set_id": WIN_SET,
                "fingerprint_seed": 1234,
            }
        ),
    )
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError) as excinfo:
        command.upgrade(get_alembic_config(db), "head")
    assert "v-old" in str(excinfo.value)
    assert "nvidia" in str(excinfo.value)
    conn = sqlite3.connect(db)
    try:
        # Blocked before any write by this migration: still stamped
        # at its on-main predecessor.
        assert _version(conn) == REVISION_PREDECESSOR_ON_MAIN
    finally:
        conn.close()


def test_snapshot_dangling_binding_blocks(tmp_path: Path) -> None:
    db = tmp_path / "snap-dangling.db"
    _build_old_db(db)
    conn = sqlite3.connect(db)
    _insert_asset(conn, "windows", WIN_SET, "verified", "2026-01-02T00:00:00+00:00")
    _insert_profile(conn, "p-clean")
    _insert_snapshot(
        conn,
        "v-old",
        "p-clean",
        json.dumps(
            {
                "name": "name-p-clean",
                "gpu_family": "auto",
                "color_scheme": "light",
                "locale": "en-US",
                "fingerprint_platform": "windows",
                "font_set_id": FAILED_SET,
                "fingerprint_seed": 1234,
            }
        ),
    )
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError) as excinfo:
        command.upgrade(get_alembic_config(db), "head")
    assert "v-old" in str(excinfo.value)
    assert FAILED_SET in str(excinfo.value)


def test_snapshot_corrupt_json_blocks(tmp_path: Path) -> None:
    db = tmp_path / "snap-corrupt.db"
    _build_old_db(db)
    conn = sqlite3.connect(db)
    _insert_asset(conn, "windows", WIN_SET, "verified", "2026-01-02T00:00:00+00:00")
    _insert_profile(conn, "p-clean")
    _insert_snapshot(conn, "v-old", "p-clean", "{not json")
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError) as excinfo:
        command.upgrade(get_alembic_config(db), "head")
    assert "v-old" in str(excinfo.value)
    assert "corrupt" in str(excinfo.value)


def test_snapshot_unbound_without_platform_set_blocks(tmp_path: Path) -> None:
    db = tmp_path / "snap-noset.db"
    _build_old_db(db)
    conn = sqlite3.connect(db)
    _insert_asset(conn, "windows", WIN_SET, "verified", "2026-01-02T00:00:00+00:00")
    # The live row is clean (windows unbound, default available); only
    # the historical macos version has nowhere to bind.
    _insert_profile(conn, "p-clean")
    _insert_snapshot(
        conn,
        "v-old",
        "p-clean",
        json.dumps(
            {
                "name": "name-p-clean",
                "gpu_family": "auto",
                "color_scheme": "light",
                "locale": "en-US",
                "fingerprint_platform": "macos",
                "font_set_id": None,
                "fingerprint_seed": 1234,
            }
        ),
    )
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError) as excinfo:
        command.upgrade(get_alembic_config(db), "head")
    assert "v-old" in str(excinfo.value)
