"""t051 Area E: container-side deploy scripts (db_inspect / db_backup /
db_restore / check_font_sets).

These scripts run inside the API image via `docker run` during deploy;
they are unit-tested here on the host against real files.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,  # callers assert on returncode/output
    )


def _stamp_db(path: Path, revision: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        conn.execute(
            "INSERT INTO alembic_version (version_num) VALUES (?)", (revision,)
        )
        conn.commit()
    finally:
        conn.close()


def _db_stamp(path: Path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else ""
    finally:
        conn.close()


# ---------------------------------------------------------------- db_inspect

def test_db_inspect_absent_file_prints_empty_stamp(tmp_path: Path):
    result = _run("db_inspect.py", "stamp", "--db", str(tmp_path / "nope.db"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_db_inspect_stamped_db_prints_revision(tmp_path: Path):
    db = tmp_path / "cbrowser.db"
    _stamp_db(db, "b7e1c9d4a2f3")
    result = _run("db_inspect.py", "stamp", "--db", str(db))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "b7e1c9d4a2f3"


def test_db_inspect_unstamped_db_prints_empty_stamp(tmp_path: Path):
    db = tmp_path / "cbrowser.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (x INT)")
    conn.commit()
    conn.close()
    result = _run("db_inspect.py", "stamp", "--db", str(db))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_db_inspect_unreadable_db_fails_closed(tmp_path: Path):
    db = tmp_path / "cbrowser.db"
    db.write_text("not a sqlite database", encoding="utf-8")
    result = _run("db_inspect.py", "stamp", "--db", str(db))
    assert result.returncode != 0
    assert "cbrowser.db" in result.stderr


# ---------------------------------------------------------------- db_backup

def test_db_backup_round_trip_preserves_stamp_and_source(tmp_path: Path):
    db = tmp_path / "cbrowser.db"
    _stamp_db(db, "b7e1c9d4a2f3")
    before = db.read_bytes()
    out = tmp_path / "cbrowser-20261111000000.db"
    result = _run("db_backup.py", "--db", str(db), "--out", str(out))
    assert result.returncode == 0, result.stderr
    assert out.is_file()
    assert _db_stamp(out) == "b7e1c9d4a2f3"
    assert db.read_bytes() == before


def test_db_backup_missing_source_fails(tmp_path: Path):
    result = _run(
        "db_backup.py",
        "--db",
        str(tmp_path / "nope.db"),
        "--out",
        str(tmp_path / "out.db"),
    )
    assert result.returncode != 0
    assert not (tmp_path / "out.db").exists()


# ---------------------------------------------------------------- db_restore

def test_db_restore_copies_backup_and_removes_wal_shm(tmp_path: Path):
    backup = tmp_path / "cbrowser-20261111000000.db"
    _stamp_db(backup, "b7e1c9d4a2f3")
    db = tmp_path / "cbrowser.db"
    db.write_text("corrupt replacement", encoding="utf-8")
    (tmp_path / "cbrowser.db-wal").write_text("wal", encoding="utf-8")
    (tmp_path / "cbrowser.db-shm").write_text("shm", encoding="utf-8")
    result = _run("db_restore.py", "--backup", str(backup), "--db", str(db))
    assert result.returncode == 0, result.stderr
    assert _db_stamp(db) == "b7e1c9d4a2f3"
    assert not (tmp_path / "cbrowser.db-wal").exists()
    assert not (tmp_path / "cbrowser.db-shm").exists()


def test_db_restore_missing_backup_fails_and_keeps_db(tmp_path: Path):
    db = tmp_path / "cbrowser.db"
    _stamp_db(db, "b7e1c9d4a2f3")
    result = _run(
        "db_restore.py", "--backup", str(tmp_path / "nope.db"), "--db", str(db)
    )
    assert result.returncode != 0
    assert _db_stamp(db) == "b7e1c9d4a2f3"


# ---------------------------------------------------------------- check_font_sets

def _valid_font_set(root: Path) -> Path:
    font = b"fake font bytes"
    set_dir = root / "windows" / "set-1"
    set_dir.mkdir(parents=True)
    (set_dir / "Arial.ttf").write_bytes(font)
    manifest = {
        "files": [
            {"name": "Arial.ttf", "sha256": hashlib.sha256(font).hexdigest()}
        ]
    }
    (set_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return set_dir


def test_check_font_sets_missing_dir_warns_without_blocking(tmp_path: Path):
    result = _run("check_font_sets.py", "--fonts-dir", str(tmp_path / "fonts"))
    assert result.returncode == 0
    assert "WARNING" in result.stdout
    assert "fonts" in result.stdout.lower()


def test_check_font_sets_valid_set_reports_ok(tmp_path: Path):
    fonts = tmp_path / "fonts"
    _valid_font_set(fonts)
    result = _run("check_font_sets.py", "--fonts-dir", str(fonts))
    assert result.returncode == 0, result.stderr
    assert "WARNING" not in result.stdout
    assert "ok" in result.stdout.lower()
    assert "windows/set-1" in result.stdout


def test_check_font_sets_invalid_set_warns_without_blocking(tmp_path: Path):
    fonts = tmp_path / "fonts"
    set_dir = fonts / "macos" / "broken"
    set_dir.mkdir(parents=True)
    (set_dir / "manifest.json").write_text(
        json.dumps({"files": [{"name": "Missing.ttf", "sha256": "0" * 64}]}),
        encoding="utf-8",
    )
    result = _run("check_font_sets.py", "--fonts-dir", str(fonts))
    assert result.returncode == 0
    assert "WARNING" in result.stdout
    assert "macos/broken" in result.stdout
