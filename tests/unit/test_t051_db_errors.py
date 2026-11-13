"""t051 Area B (AC-005/AC-006/AC-007): SQLite error classification, API
503 mapping and bounded auth retry.

Primary code = extended code & 0xFF.  Transient iff primary in
{5 BUSY, 6 LOCKED, 10 IOERR} — including extended codes such as
SQLITE_BUSY_SNAPSHOT (261) or SQLITE_IOERR_READ (778).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from api_auth import create_auth_context
from cbrowser.adapters.database.db_errors import (
    classify_dbapi_error,
    retry_transient_db_errors,
)
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.app import create_app
from cbrowser.auth.service import AuthService
from cbrowser.services.profile_service import (
    DatabaseLockError,
    DatabaseUnavailableError,
    ProfileService,
)
from sqlalchemy.exc import DBAPIError, OperationalError


def _db_error(code: int | None, name: str | None) -> DBAPIError:
    orig = SimpleNamespace(sqlite_errorcode=code, sqlite_errorname=name)
    return OperationalError("SELECT 1", None, orig)


# ---------------------------------------------------------------- classification

@pytest.mark.parametrize(
    ("code", "name", "kind", "transient", "error_code", "status"),
    [
        (5, "SQLITE_BUSY", "busy", True, "database_busy", 503),
        (6, "SQLITE_LOCKED", "locked", True, "database_busy", 503),
        (10, "SQLITE_IOERR", "io_error", True, "database_unavailable", 503),
        # Extended codes: primary code is the low byte.
        (261, "SQLITE_BUSY_SNAPSHOT", "busy", True, "database_busy", 503),
        (517, "SQLITE_BUSY_TIMEOUT", "busy", True, "database_busy", 503),
        (778, "SQLITE_IOERR_READ", "io_error", True, "database_unavailable", 503),
        (262, "SQLITE_LOCKED_SHAREDCACHE", "locked", True, "database_busy", 503),
        # Deterministic errors stay 500 / non-retryable.
        (19, "SQLITE_CONSTRAINT", "constraint", False, "database_error", 500),
        (1, "SQLITE_ERROR", "other", False, "database_error", 500),
        (11, "SQLITE_CORRUPT", "other", False, "database_error", 500),
    ],
)
def test_classify_dbapi_error_matrix(code, name, kind, transient, error_code, status):
    result = classify_dbapi_error(_db_error(code, name))
    assert result.primary_code == (code & 0xFF if code is not None else None)
    assert result.error_name == name
    assert result.kind == kind
    assert result.transient is transient
    assert result.error_code == error_code
    assert result.http_status == status


def test_classify_falls_back_to_error_name_when_code_missing():
    result = classify_dbapi_error(_db_error(None, "SQLITE_BUSY"))
    assert result.kind == "busy"
    assert result.transient is True
    assert result.error_code == "database_busy"


def test_classify_without_orig_is_non_transient():
    result = classify_dbapi_error(OperationalError("SELECT 1", None, None))
    assert result.primary_code is None
    assert result.transient is False
    assert result.error_code == "database_error"
    assert result.http_status == 500


# ---------------------------------------------------------------- bounded retry

@pytest.mark.asyncio
async def test_retry_succeeds_after_bounded_transient_failures():
    calls = 0

    @retry_transient_db_errors
    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise _db_error(5, "SQLITE_BUSY")
        return "ok"

    assert await flaky() == "ok"
    assert calls == 3


@pytest.mark.asyncio
async def test_retry_gives_up_after_three_attempts():
    calls = 0

    @retry_transient_db_errors
    async def always_busy() -> str:
        nonlocal calls
        calls += 1
        raise _db_error(10, "SQLITE_IOERR")

    with pytest.raises(DBAPIError):
        await always_busy()
    assert calls == 3


@pytest.mark.asyncio
async def test_retry_does_not_retry_deterministic_errors():
    calls = 0

    @retry_transient_db_errors
    async def constraint() -> str:
        nonlocal calls
        calls += 1
        raise _db_error(19, "SQLITE_CONSTRAINT")

    with pytest.raises(DBAPIError):
        await constraint()
    assert calls == 1


# ---------------------------------------------------------------- API handler

def _app(tmp_path: Path):
    ctx = create_auth_context(tmp_path)
    app = create_app(
        db_path=tmp_path / "db_errors.db",
        admin_password_file=ctx.admin_password_file,
        artifacts_root=tmp_path / "artifacts",
    )
    return app, ctx


def _body(response) -> dict:
    return json.loads(response.body)


def _request() -> MagicMock:
    request = MagicMock()
    request.method = "POST"
    request.url.path = "/api/v1/auth/login"
    return request


@pytest.mark.asyncio
async def test_api_handler_maps_busy_to_503_retryable(tmp_path: Path):
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[DBAPIError]
    resp = await handler(_request(), _db_error(5, "SQLITE_BUSY"))
    assert resp.status_code == 503
    assert resp.headers.get("Retry-After") == "1"
    body = _body(resp)
    assert body == {
        "error": "database_busy",
        "message": "Database is temporarily locked, retryable operation",
        "retryable": True,
    }


@pytest.mark.asyncio
async def test_api_handler_maps_ioerr_to_503_unavailable(tmp_path: Path):
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[DBAPIError]
    resp = await handler(_request(), _db_error(778, "SQLITE_IOERR_READ"))
    assert resp.status_code == 503
    assert resp.headers.get("Retry-After") == "1"
    body = _body(resp)
    assert body["error"] == "database_unavailable"
    assert body["retryable"] is True


@pytest.mark.asyncio
async def test_api_handler_keeps_deterministic_errors_at_500(tmp_path: Path):
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[DBAPIError]
    resp = await handler(_request(), _db_error(19, "SQLITE_CONSTRAINT"))
    assert resp.status_code == 500
    body = _body(resp)
    assert body["error"] == "database_error"
    assert body["retryable"] is False


@pytest.mark.asyncio
async def test_api_handler_logs_codes_not_sql_or_secrets(tmp_path: Path, caplog):
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[DBAPIError]
    secret_sql = "SELECT * FROM admins WHERE password_hash = 'topsecret'"
    exc = OperationalError(
        secret_sql, ("topsecret",), SimpleNamespace(
            sqlite_errorcode=5, sqlite_errorname="SQLITE_BUSY"
        )
    )
    with caplog.at_level(logging.WARNING, logger="cbrowser.api"):
        resp = await handler(_request(), exc)
    assert resp.status_code == 503
    assert "topsecret" not in caplog.text
    assert "password_hash" not in caplog.text
    assert "sqlite_errorcode=5" in caplog.text
    assert "SQLITE_BUSY" in caplog.text
    assert "POST" in caplog.text and "/api/v1/auth/login" in caplog.text


@pytest.mark.asyncio
async def test_api_handler_database_unavailable_error_is_503(tmp_path: Path):
    app, _ = _app(tmp_path)
    handler = app.exception_handlers[DatabaseUnavailableError]
    resp = await handler(_request(), DatabaseUnavailableError())
    assert resp.status_code == 503
    assert resp.headers.get("Retry-After") == "1"
    body = _body(resp)
    assert body["error"] == "database_unavailable"
    assert body["retryable"] is True


# ---------------------------------------------------------------- ProfileService

def test_profile_service_maps_ioerr_to_unavailable():
    service = ProfileService.__new__(ProfileService)
    with pytest.raises(DatabaseUnavailableError):
        service._handle_db_error(_db_error(10, "SQLITE_IOERR"))


def test_profile_service_still_maps_busy_to_lock_error():
    service = ProfileService.__new__(ProfileService)
    with pytest.raises(DatabaseLockError):
        service._handle_db_error(_db_error(261, "SQLITE_BUSY_SNAPSHOT"))


def test_profile_service_reraises_deterministic_errors():
    service = ProfileService.__new__(ProfileService)
    exc = _db_error(19, "SQLITE_CONSTRAINT")
    with pytest.raises(DBAPIError) as caught:
        service._handle_db_error(exc)
    assert caught.value is exc


# ---------------------------------------------------------------- AuthService retry

@pytest.fixture
async def auth_db(tmp_path: Path):
    db_file = tmp_path / "auth_retry_test.db"
    run_database_migrations(db_file)
    engine, session_maker = create_engine_and_maker(db_file)
    service = AuthService(session_maker)
    yield service, session_maker
    await engine.dispose()


class _FlakySession:
    """Wraps a real AsyncSession; fails the first N executes transiently."""

    def __init__(self, real, maker):
        self._real = real
        self._maker = maker

    async def __aenter__(self):
        await self._real.__aenter__()
        return self

    async def __aexit__(self, *args):
        return await self._real.__aexit__(*args)

    async def execute(self, *args, **kwargs):
        self._maker.execute_calls += 1
        if self._maker.failures_remaining > 0:
            self._maker.failures_remaining -= 1
            raise self._maker.error
        return await self._real.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _FlakySessionMaker:
    def __init__(self, real_maker, failures: int, error: DBAPIError):
        self._real_maker = real_maker
        self.failures_remaining = failures
        self.error = error
        self.execute_calls = 0

    def __call__(self):
        return _FlakySession(self._real_maker(), self)


@pytest.mark.asyncio
async def test_login_succeeds_after_bounded_transient_failures(
    auth_db, tmp_path: Path
):
    service, session_maker = auth_db
    password = "admin_secure_password_12345"
    password_file = tmp_path / "admin.pwd"
    password_file.write_text(password, encoding="utf-8")
    await service.init_admin_password(password_file)

    service._session_maker = _FlakySessionMaker(
        session_maker, failures=2, error=_db_error(5, "SQLITE_BUSY")
    )
    ok, reason = await service.authenticate_admin(password, "127.0.0.1")
    assert ok is True
    assert reason is None
    assert service._session_maker.execute_calls == 3
    # Transient failures must not count against the login rate limiter.
    assert "127.0.0.1" not in service.rate_limiter._failures


@pytest.mark.asyncio
async def test_login_persistent_transient_failure_raises_after_three_attempts(
    auth_db, tmp_path: Path
):
    service, session_maker = auth_db
    password = "admin_secure_password_12345"
    password_file = tmp_path / "admin.pwd"
    password_file.write_text(password, encoding="utf-8")
    await service.init_admin_password(password_file)

    maker = _FlakySessionMaker(
        session_maker, failures=10, error=_db_error(10, "SQLITE_IOERR")
    )
    service._session_maker = maker
    with pytest.raises(DBAPIError):
        await service.authenticate_admin(password, "127.0.0.1")
    assert maker.execute_calls == 3


@pytest.mark.asyncio
async def test_has_admin_retries_transient_failure(auth_db):
    service, session_maker = auth_db
    maker = _FlakySessionMaker(
        session_maker, failures=1, error=_db_error(6, "SQLITE_LOCKED")
    )
    service._session_maker = maker
    assert await service.has_admin() is False
    assert maker.execute_calls == 2
