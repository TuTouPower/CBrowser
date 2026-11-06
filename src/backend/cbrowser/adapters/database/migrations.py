"""Database migration and initialization utilities using Alembic and SQLAlchemy."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

# Single baseline revision (t035).  A database stamped with any other
# revision belongs to the retired 0001-0009 schema generation and must NOT
# be upgraded in place: the old and new schemas are not compatible.
BASELINE_REVISION = "b7e1c9d4a2f3"
REBUILD_GUIDANCE = (
    "This database was created by a retired CBrowser schema generation "
    "(0001-0009). Rebuild the data directory from scratch: stop the stack, "
    "move the old data root aside, then start with an empty data directory "
    "so the baseline schema is created fresh. No in-place data migration "
    "is provided (project decision: no formal users before t035)."
)


class LegacySchemaError(RuntimeError):
    """Raised when a database from the retired schema generation is detected."""


def get_alembic_config(db_path: Path | str) -> Config:
    backend_dir = Path(__file__).resolve().parent.parent.parent.parent
    ini_path = backend_dir / "migrations" / "alembic.ini"
    script_loc = backend_dir / "migrations"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(script_loc))
    cfg.set_main_option("path_separator", "os")
    resolved_db = Path(db_path).resolve()
    resolved_db.parent.mkdir(parents=True, exist_ok=True)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{resolved_db}")
    return cfg


def run_database_migrations(db_path: Path | str) -> None:
    """Run alembic upgrade head on the target SQLite database path.

    Fails closed (without touching the database) when the file is stamped
    with a revision from the retired 0001-0009 chain (t035 AC-002).
    Sets WAL mode on the database file here (it persists in the file);
    busy_timeout is NOT persisted and is applied per connection by the
    engine factory in session.py.
    """
    resolved_db = Path(db_path).resolve()
    resolved_db.parent.mkdir(parents=True, exist_ok=True)

    if resolved_db.is_file():
        check = sqlite3.connect(str(resolved_db))
        try:
            row = check.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='alembic_version'"
            ).fetchone()
            if row is not None:
                current = check.execute(
                    "SELECT version_num FROM alembic_version"
                ).fetchone()
                if current is not None and current[0]:
                    script = ScriptDirectory.from_config(
                        get_alembic_config(resolved_db)
                    )
                    known = {rev.revision for rev in script.walk_revisions()}
                    if current[0] not in known:
                        raise LegacySchemaError(
                            f"Legacy schema revision {current[0]!r}. "
                            f"{REBUILD_GUIDANCE}"
                        )
        finally:
            check.close()

    # Pre-configure pragmas on connection
    conn = sqlite3.connect(str(resolved_db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.close()

    cfg = get_alembic_config(resolved_db)
    command.upgrade(cfg, "head")
