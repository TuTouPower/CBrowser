"""Database migration and initialization utilities using Alembic and SQLAlchemy."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


def get_alembic_config(db_path: Path | str) -> Config:
    backend_dir = Path(__file__).resolve().parent.parent.parent.parent
    ini_path = backend_dir / "migrations" / "alembic.ini"
    script_loc = backend_dir / "migrations"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(script_loc))
    resolved_db = Path(db_path).resolve()
    resolved_db.parent.mkdir(parents=True, exist_ok=True)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{resolved_db}")
    return cfg


def run_database_migrations(db_path: Path | str) -> None:
    """Run alembic upgrade head on the target SQLite database path.

    Configures database with WAL and busy_timeout=5000.
    """
    resolved_db = Path(db_path).resolve()
    resolved_db.parent.mkdir(parents=True, exist_ok=True)

    # Pre-configure pragmas on connection
    conn = sqlite3.connect(str(resolved_db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.close()

    cfg = get_alembic_config(resolved_db)
    command.upgrade(cfg, "head")
