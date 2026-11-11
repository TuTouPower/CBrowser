"""t056 migration tests: A1 (pragma order), A21 (display_number NOT NULL),
A29 (empty/missing alembic_version guard), A60 (tolerance removal +
downgrade throws).

The t056 golden schema file (tests/unit/data/t056_fresh_schema_before.txt)
is the fresh-DB ``sqlite_master`` dump taken before these changes; the
AC-013 test asserts the only structural difference after them is the
intended display_number NOT NULL change (plus a foreign-key clause
reorder emitted by the batch table rebuild, which carries no meaning).
"""

from __future__ import annotations

import importlib.util
import sqlite3
import threading
import time
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from pydantic import ValidationError

from cbrowser.adapters.database import migrations
from cbrowser.adapters.database.migrations import (
    LegacySchemaError,
    get_alembic_config,
    run_database_migrations,
)
from cbrowser.domain.models import Profile, ProfileConfig, ProfileRuntime

GOLDEN_SCHEMA = Path(__file__).resolve().parent / "data" / "t056_fresh_schema_before.txt"
REVISION_0002 = "c41f0a2b7d93"
REVISION_0003 = "a35c0f1e7b42"
REVISION_0008 = "3751fed02a4a"
VERSIONS_DIR = (
    Path(__file__).resolve().parents[2]
    / "src" / "backend" / "migrations" / "versions"
)


def _dump_schema(db_path: Path) -> dict[tuple[str, str], str]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            # The golden fixture encodes a NULL sql as the literal "None"
            # (f-string of the original dump); keep the same encoding.
            (t, n): ("None" if s is None else s.replace("\n", "\\n"))
            for t, n, s in conn.execute(
                "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
            ).fetchall()
        }
    finally:
        conn.close()


def _normalized_sql_lines(sql: str) -> list[str]:
    """CREATE TABLE text with per-line trailing commas stripped and lines
    sorted: the batch table rebuild reorders FOREIGN KEY clauses, which
    is formatting, not structure."""
    sql = sql.replace("\\n", "\n")
    lines = [line.strip().rstrip(",") for line in sql.splitlines()]
    return sorted(line for line in lines if line)


# ---------------------------------------------------------------- A1


class _RecordingConnection:
    """sqlite3 connection proxy that records executed SQL text."""

    def __init__(self, real, log: list[str]):
        self._real = real
        self._log = log

    def execute(self, sql, *args, **kwargs):
        if isinstance(sql, str) and sql.strip().upper().startswith("PRAGMA"):
            self._log.append(sql.strip())
        return self._real.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_pragma_order_busy_timeout_before_wal(tmp_path: Path, monkeypatch) -> None:
    """A1 / AC-001: the migration connection sets busy_timeout before
    switching to WAL (same order as session.py)."""
    import sqlite3 as sqlite3_module

    log: list[str] = []
    real_connect = sqlite3_module.connect

    def recording_connect(*args, **kwargs):
        return _RecordingConnection(real_connect(*args, **kwargs), log)

    monkeypatch.setattr(migrations.sqlite3, "connect", recording_connect)
    run_database_migrations(tmp_path / "order.db")
    pragmas = [entry for entry in log if "busy_timeout" in entry or "journal_mode" in entry]
    assert pragmas[0].startswith("PRAGMA busy_timeout"), pragmas
    assert pragmas[1].startswith("PRAGMA journal_mode=WAL"), pragmas


def test_migration_waits_out_busy_timeout(tmp_path: Path) -> None:
    """A1 / AC-001: with another connection holding a write transaction,
    the migration waits for the busy timeout instead of failing BUSY
    immediately, and the database ends up in WAL mode."""
    db = tmp_path / "busy.db"
    run_database_migrations(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
    finally:
        conn.close()

    released = threading.Event()

    def _hold_write_lock() -> None:
        holder = sqlite3.connect(db)
        try:
            holder.execute("BEGIN IMMEDIATE")
            holder.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at)"
                " VALUES ('t056.hold', '1', '2026-01-01T00:00:00+00:00')"
            )
            time.sleep(0.7)
            holder.commit()
        finally:
            holder.close()
            released.set()

    thread = threading.Thread(target=_hold_write_lock, daemon=True)
    thread.start()
    time.sleep(0.15)  # let the holder take the write lock first
    started = time.monotonic()
    try:
        run_database_migrations(db)
    finally:
        elapsed = time.monotonic() - started
        thread.join(timeout=10)
    assert released.is_set()
    # t056_test_f002: the migration must have actually contended with
    # the holder (which releases ~0.7s after starting, i.e. ~0.55s
    # after the migration began). Without contention the call returns
    # in milliseconds; asserting on the duration proves the bounded
    # retry path ran instead of the test passing on an empty run.
    assert elapsed >= 0.5, f"migration did not wait out the holder: {elapsed:.3f}s"
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        conn.close()


# ---------------------------------------------------------------- A29


def _business_table_db(tmp_path: Path, name: str) -> Path:
    db = tmp_path / name
    conn = sqlite3.connect(db)
    try:
        conn.execute("CREATE TABLE profiles (id TEXT PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()
    return db


def test_legacy_schema_error_missing_alembic_version(tmp_path: Path) -> None:
    """A29 / AC-011: business tables but no alembic_version table."""
    db = _business_table_db(tmp_path, "missing-version.db")
    with pytest.raises(LegacySchemaError, match="Rebuild the data directory"):
        run_database_migrations(db)


def test_legacy_schema_error_empty_alembic_version(tmp_path: Path) -> None:
    """A29 / AC-011: alembic_version table exists but holds no rows."""
    db = _business_table_db(tmp_path, "empty-version.db")
    conn = sqlite3.connect(db)
    try:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(LegacySchemaError, match="Rebuild the data directory"):
        run_database_migrations(db)


def test_legacy_schema_error_blank_version_num(tmp_path: Path) -> None:
    """A29 / AC-011: alembic_version holds an empty version string."""
    db = _business_table_db(tmp_path, "blank-version.db")
    conn = sqlite3.connect(db)
    try:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('')")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(LegacySchemaError, match="Rebuild the data directory"):
        run_database_migrations(db)


def test_empty_db_without_tables_still_upgrades(tmp_path: Path) -> None:
    """A29: a database file with no business tables is a fresh database,
    not a legacy one: the guard must not fire."""
    db = tmp_path / "fresh.db"
    db.touch()
    run_database_migrations(db)
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        conn.close()


# ---------------------------------------------------------------- A60


def test_0003_leaves_legacy_operation_rows_untouched(tmp_path: Path) -> None:
    """A60: 0003 no longer backfills or repairs network operation rows.
    The generation counter is still seeded; the pre-A35 records stay
    byte-identical and no current pointer is created."""
    db = tmp_path / "op-rows.db"
    cfg = get_alembic_config(db)
    command.upgrade(cfg, REVISION_0002)
    now = "2026-01-01T00:00:00+00:00"
    legacy_op = (
        '{"operation_id": "op-crash", "target_version": 2, "phase": "pending",'
        ' "error_reason": null, "new_entry_url": null, "created_at": "'
        + now
        + '", "updated_at": "'
        + now
        + '"}'
    )
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            ("network.operation.op-crash", legacy_op, now),
        )
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            ("network.active_operation", legacy_op, now),
        )
        conn.commit()
    finally:
        conn.close()
    command.upgrade(cfg, REVISION_0003)
    conn = sqlite3.connect(db)
    try:
        assert (
            conn.execute(
                "SELECT value FROM settings WHERE key = 'network.operation.op-crash'"
            ).fetchone()[0]
            == legacy_op
        )
        assert (
            conn.execute(
                "SELECT value FROM settings WHERE key = 'network.active_operation'"
            ).fetchone()[0]
            == legacy_op
        )
        assert (
            conn.execute(
                "SELECT value FROM settings WHERE key = 'network.transaction.current'"
            ).fetchone()
            is None
        )
        assert (
            conn.execute(
                "SELECT value FROM settings WHERE key = 'network.execution_generation'"
            ).fetchone()[0]
            == "0"
        )
    finally:
        conn.close()


def test_0004_fails_when_column_exists_with_wrong_definition(tmp_path: Path) -> None:
    """A60 / AC-013: 0004 adds its columns unconditionally. A database
    whose tables already carry one of them in a different shape fails
    instead of being silently stamped to head."""
    db = tmp_path / "wrong-shape.db"
    cfg = get_alembic_config(db)
    command.upgrade(cfg, REVISION_0002)
    conn = sqlite3.connect(db)
    try:
        # capture_preview_epoch exists but as nullable TEXT, not the
        # NOT NULL INTEGER with server default 0 that 0004 defines.
        conn.execute(
            "ALTER TABLE profiles ADD COLUMN capture_preview_epoch TEXT"
        )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(Exception):
        run_database_migrations(db)
    conn = sqlite3.connect(db)
    try:
        stamp = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        # 0003 ran, then 0004 failed: the stamp must not advance past 0003.
        assert stamp == REVISION_0003
    finally:
        conn.close()


def test_every_revision_downgrade_raises(tmp_path: Path) -> None:
    """A60 / AC-013: every shipped revision's downgrade() throws a clear
    unsupported-downgrade error."""
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name.startswith("__"):
            continue
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with pytest.raises(RuntimeError, match="not supported"):
            module.downgrade()


def test_fresh_db_schema_matches_before_except_display_number(
    tmp_path: Path,
) -> None:
    """A60 / AC-013: a fresh database upgraded to head has the same
    structure as before these changes, except the intended A21 change
    (display_number becomes NOT NULL)."""
    db = tmp_path / "fresh.db"
    run_database_migrations(db)
    before = {}
    for line in GOLDEN_SCHEMA.read_text().splitlines():
        type_, name, sql = line.split("|", 2)
        before[(type_, name)] = sql
    after = _dump_schema(db)
    assert set(after) == set(before)
    for key in before:
        if key == ("table", "profiles"):
            continue
        assert after[key] == before[key], key
    before_lines = _normalized_sql_lines(before[("table", "profiles")])
    after_lines = _normalized_sql_lines(after[("table", "profiles")])
    assert sorted(set(after_lines) - set(before_lines)) == [
        "display_number INTEGER NOT NULL"
    ]
    assert sorted(set(before_lines) - set(after_lines)) == [
        "display_number INTEGER"
    ]


# ---------------------------------------------------------------- A21


def test_display_number_null_row_rejected_by_database(tmp_path: Path) -> None:
    """A21 / AC-006: a NULL display_number cannot be written."""
    db = tmp_path / "null-number.db"
    run_database_migrations(db)
    conn = sqlite3.connect(db)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            conn.execute(
                "INSERT INTO profiles (id, display_number, name,"
                " fingerprint_seed, user_data_dir, created_at, updated_at)"
                " VALUES (?, NULL, ?, ?, ?, ?, ?)",
                (
                    "null-1",
                    "Null",
                    1,
                    "/data/profiles/null-1/profile",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
    finally:
        conn.close()


def test_0009_backfill_skips_existing_numbers_with_gaps(
    tmp_path: Path,
) -> None:
    """A21 / AC-006 (t056_code_f003): 0009's NULL backfill must not
    collide with surviving display numbers when deletions left gaps.
    Rows at 1 and 3 plus one NULL row: the migration succeeds and the
    NULL row gets max+1 (4) — numbering all rows would assign it 3 and
    violate the unique index."""
    db = tmp_path / "gap-backfill.db"
    cfg = get_alembic_config(db)
    command.upgrade(cfg, REVISION_0008)
    conn = sqlite3.connect(db)
    try:
        for pid, number, name, day in [
            ("gap-a", 1, "Gap A", "01"),
            ("gap-b", 3, "Gap B", "02"),
            ("gap-c", None, "Gap C", "03"),
        ]:
            conn.execute(
                "INSERT INTO profiles (id, display_number, name,"
                " fingerprint_seed, user_data_dir, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    pid,
                    number,
                    name,
                    1,
                    f"/data/profiles/{pid}/profile",
                    f"2026-01-{day}T00:00:00+00:00",
                    f"2026-01-{day}T00:00:00+00:00",
                ),
            )
        conn.commit()
    finally:
        conn.close()
    run_database_migrations(db)
    conn = sqlite3.connect(db)
    try:
        numbers = dict(
            conn.execute("SELECT id, display_number FROM profiles").fetchall()
        )
    finally:
        conn.close()
    assert numbers == {"gap-a": 1, "gap-b": 3, "gap-c": 4}


def test_domain_models_require_display_number() -> None:
    """A21 / AC-006: the domain models no longer default a missing
    display_number to 1; construction without one fails."""
    config = ProfileConfig(name="t")
    with pytest.raises(ValidationError):
        Profile(
            id="p1",
            config=config,
            user_data_dir="/data/profiles/p1/profile",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
    with pytest.raises(ValidationError):
        ProfileRuntime(profile_id="p1")
