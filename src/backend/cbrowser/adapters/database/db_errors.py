"""SQLite/SQLAlchemy DBAPI error classification and bounded retry.

A transient SQLite failure is one the caller may safely retry: the
database is busy, locked, or hit an I/O error.  Classification uses the
SQLite *primary* error code (extended code & 0xFF) so extended codes such
as ``SQLITE_BUSY_SNAPSHOT`` (261) or ``SQLITE_IOERR_READ`` (778) classify
the same as their primary code.  The error name is only a fallback for
drivers that do not expose the numeric code.

The API never logs ``str(exc.orig)``: the DBAPI message can carry SQL
text and bound parameters.  Only the numeric code, the SQLite error name
and the request line are logged.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from functools import wraps
from typing import Literal

from sqlalchemy.exc import DBAPIError

logger = logging.getLogger("cbrowser.db")

#: Primary SQLite codes that are safe to retry (BUSY, LOCKED, IOERR).
TRANSIENT_PRIMARY_CODES = frozenset({5, 6, 10})
MAX_DB_ATTEMPTS = 3
#: Backoff between attempts 1->2 and 2->3; short on purpose — the SQLite
#: busy timeout already absorbs brief contention, this only bridges gaps.
DB_RETRY_BACKOFFS = (0.05, 0.1)

_BUSY_NAMES = {"SQLITE_BUSY"}
_LOCKED_NAMES = {"SQLITE_LOCKED"}
_IOERR_NAMES = {"SQLITE_IOERR"}


@dataclass(frozen=True)
class DbErrorClassification:
    primary_code: int | None
    error_name: str | None
    kind: Literal["busy", "locked", "io_error", "constraint", "other"]
    transient: bool
    #: Stable API error code (``database_busy`` / ``database_unavailable``
    #: / ``database_error``).
    error_code: str
    http_status: int


def _primary_code(exc: BaseException) -> tuple[int | None, str | None]:
    orig = getattr(exc, "orig", None)
    for source in (orig, exc):
        if source is None:
            continue
        code = getattr(source, "sqlite_errorcode", None)
        name = getattr(source, "sqlite_errorname", None)
        if isinstance(code, int):
            return code & 0xFF, name or None
        if name:
            return None, name
    return None, None


def classify_dbapi_error(exc: BaseException) -> DbErrorClassification:
    primary_code, error_name = _primary_code(exc)
    if primary_code is not None:
        kind: Literal["busy", "locked", "io_error", "constraint", "other"]
        if primary_code == 5:
            kind = "busy"
        elif primary_code == 6:
            kind = "locked"
        elif primary_code == 10:
            kind = "io_error"
        elif primary_code == 19:
            kind = "constraint"
        else:
            kind = "other"
    elif error_name in _BUSY_NAMES:
        kind = "busy"
    elif error_name in _LOCKED_NAMES:
        kind = "locked"
    elif error_name in _IOERR_NAMES:
        kind = "io_error"
    elif error_name == "SQLITE_CONSTRAINT":
        kind = "constraint"
    else:
        kind = "other"
    transient = kind in ("busy", "locked", "io_error")
    if kind in ("busy", "locked"):
        error_code = "database_busy"
    elif kind == "io_error":
        error_code = "database_unavailable"
    else:
        error_code = "database_error"
    return DbErrorClassification(
        primary_code=primary_code,
        error_name=error_name,
        kind=kind,
        transient=transient,
        error_code=error_code,
        http_status=503 if transient else 500,
    )


def retry_transient_db_errors(fn):
    """Retry an async DB call on transient SQLite errors, at most 3 attempts.

    The whole wrapped coroutine is re-run, so each attempt opens a fresh
    session.  Only ``DBAPIError`` classified transient is retried;
    deterministic errors surface immediately.
    """

    @wraps(fn)
    async def wrapper(*args, **kwargs):
        for attempt in range(1, MAX_DB_ATTEMPTS + 1):
            try:
                return await fn(*args, **kwargs)
            except DBAPIError as exc:
                classification = classify_dbapi_error(exc)
                if not classification.transient or attempt == MAX_DB_ATTEMPTS:
                    raise
                logger.warning(
                    "Transient database error, retrying: "
                    "sqlite_errorcode=%s sqlite_errorname=%s attempt=%s/%s",
                    classification.primary_code,
                    classification.error_name,
                    attempt,
                    MAX_DB_ATTEMPTS,
                )
                await asyncio.sleep(DB_RETRY_BACKOFFS[attempt - 1])

    return wrapper
