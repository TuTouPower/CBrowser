"""Database migration and initialization utilities using Alembic and SQLAlchemy."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

# Single baseline revision (t035).  Membership in the shipped revision
# chain is decided by the chain itself (see run_database_migrations):
# a database stamped with a revision that no shipped file names is from
# the retired 0001-0009 schema generation and must NOT be upgraded in
# place.  A stamp equal to the baseline is only the pre-first-deploy
# state; after the first deploy the live database sits at the chain head.
BASELINE_REVISION = "b7e1c9d4a2f3"
REBUILD_GUIDANCE = (
    "This database was created by a retired CBrowser schema generation "
    "(0001-0009). Rebuild the data directory from scratch: stop the stack, "
    "move the old data root aside, then start with an empty data directory "
    "so the baseline schema is created fresh. No in-place data migration "
    "is provided (project decision: no formal users before t035)."
)

# Business tables owned by the baseline schema.  A database file that
# already holds any of these but carries no usable Alembic stamp is a
# legacy/interrupted database, never a fresh one: fail closed instead of
# letting Alembic stamp it to head over unknown content (t056 A29).
BUSINESS_TABLES = frozenset(
    {
        "profiles",
        "profile_groups",
        "proxies",
        "profile_runtimes",
        "profile_config_versions",
        "profile_controls",
        "audit_events",
        "runtime_events",
        "settings",
        "artifacts",
        "sessions",
        "admins",
        "automation_tokens",
        "proxy_egress_observations",
        "profile_display_sequence",
    }
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
    with a revision outside the shipped chain, or when it already holds
    business tables but carries no usable Alembic stamp (missing
    alembic_version table, or a table with no rows / an empty version):
    such a database is a legacy or interrupted one and must be rebuilt,
    never stamped to head over unknown content (t035 AC-002, t056 A29).
    Sets WAL mode on the database file here (it persists in the file);
    busy_timeout is NOT persisted and is applied per connection by the
    engine factory in session.py.
    """
    resolved_db = Path(db_path).resolve()
    resolved_db.parent.mkdir(parents=True, exist_ok=True)

    if resolved_db.is_file():
        check = sqlite3.connect(str(resolved_db))
        try:
            existing_tables = {
                row[0]
                for row in check.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            has_business_tables = bool(existing_tables & BUSINESS_TABLES)
            row = check.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='alembic_version'"
            ).fetchone()
            current = None
            if row is not None:
                current = check.execute(
                    "SELECT version_num FROM alembic_version"
                ).fetchone()
            if has_business_tables and (
                row is None or current is None or not current[0]
            ):
                raise LegacySchemaError(
                    "Database holds business tables but no usable Alembic "
                    f"stamp. {REBUILD_GUIDANCE}"
                )
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

    # Pre-configure pragmas on connection: busy_timeout FIRST, then the
    # WAL switch (same order as session.py).  The order alone is not
    # enough: PRAGMA journal_mode=WAL does NOT honour the busy handler —
    # while another connection holds a write transaction it fails
    # immediately with SQLITE_BUSY instead of waiting (verified by
    # experiment in t056).  So the switch is retried until the same
    # busy_timeout deadline, which is what makes AC-001 hold: a
    # migration that starts while another connection writes waits out
    # the lock and completes the switch instead of failing BUSY.
    conn = sqlite3.connect(str(resolved_db))
    conn.execute("PRAGMA busy_timeout=5000")
    _switch_to_wal(conn, timeout_seconds=5.0)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.close()

    cfg = get_alembic_config(resolved_db)
    command.upgrade(cfg, "head")


def _switch_to_wal(conn: sqlite3.Connection, timeout_seconds: float) -> None:
    """Switch the database to WAL mode, retrying while it is locked.

    ``PRAGMA journal_mode=WAL`` needs an exclusive lock and returns
    SQLITE_BUSY immediately instead of waiting on the busy handler, so
    a single attempt would fail a migration that starts while another
    connection holds a write transaction.  Retry on lock/busy errors
    until the deadline, then re-raise the last error.
    """
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "locked" not in message and "busy" not in message:
                raise
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.05)
