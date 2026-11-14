#!/usr/bin/env python3
"""Inspect the control-plane database's Alembic stamp (t051).

Runs inside the API image during deploy/rollback so the host never opens
the database file directly:

    docker run --rm -v <db-volume>:/db:ro -v <repo>/scripts:/scripts:ro \\
        <api-image> python3 /scripts/db_inspect.py stamp --db /db/cbrowser.db

Semantics (A44, fail-closed):
- absent file            -> print "" and exit 0 (fresh install; the API
                              creates the schema on startup).
- present, stamped       -> print the alembic_version revision.
- present, unstamped     -> print "" and exit 0.
- present but unreadable -> print an error to stderr and exit non-zero.
  A corrupt/unreadable database must refuse the deploy, never be
  silently treated as "no database".
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote


def _read_stamp(db_path: Path) -> str:
    conn = sqlite3.connect("file:" + quote(str(db_path)) + "?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='alembic_version'"
        ).fetchone()
        if row is None:
            return ""
        stamped = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return stamped[0] if stamped is not None and stamped[0] else ""
    finally:
        conn.close()


def stamp(db_path: Path) -> str | None:
    """Return the Alembic revision, "" when unstamped/absent, None on error."""
    if not db_path.is_file():
        return ""
    try:
        return _read_stamp(db_path)
    except sqlite3.OperationalError:
        try:
            with db_path.open("rb") as handle:
                handle.read(1)
        except OSError:
            return None
        try:
            with tempfile.TemporaryDirectory() as scratch:
                tmp_db = Path(scratch) / db_path.name
                shutil.copy2(db_path, tmp_db)
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(f"{db_path}{suffix}")
                    if sidecar.is_file():
                        shutil.copy2(sidecar, Path(f"{tmp_db}{suffix}"))
                return _read_stamp(tmp_db)
        except (OSError, sqlite3.DatabaseError):
            return None
    except sqlite3.DatabaseError:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["stamp"])
    parser.add_argument("--db", required=True, help="SQLite database file")
    args = parser.parse_args(argv)
    result = stamp(Path(args.db))
    if result is None:
        print(f"db_inspect: cannot read database at {args.db}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
