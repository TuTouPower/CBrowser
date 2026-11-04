"""Database session and engine lifecycle for SQLite WAL + busy_timeout=5000."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@asynccontextmanager
async def write_transaction(session: AsyncSession):
    """Context manager for write transactions.

    Explicitly executes BEGIN IMMEDIATE.
    """
    await session.connection(execution_options={"sqlite_write": True})
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise


def create_engine_and_maker(
    db_path: Path | str,
    *,
    echo: bool = False,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Create async SQLAlchemy engine and sessionmaker.

    Configured with WAL mode and busy_timeout=5000.
    """
    db_path_obj = Path(db_path).resolve()
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite+aiosqlite:///{db_path_obj}"

    engine = create_async_engine(
        db_url,
        echo=echo,
        future=True,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        # busy_timeout must precede journal_mode: the latter may need to
        # wait for another connection's write transaction, and without a
        # timeout already installed SQLite fails immediately with BUSY.
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _do_begin(conn):
        is_write = conn.get_execution_options().get("sqlite_write", False)
        if is_write:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            conn.exec_driver_sql("BEGIN")

    session_maker = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    return engine, session_maker
