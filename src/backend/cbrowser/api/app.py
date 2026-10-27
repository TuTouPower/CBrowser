"""FastAPI Application factory for CBrowser v2."""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import (
    IdempotencyConflictError,
    InstanceConflictError,
    InvalidConfigVersionError,
    ProfileRepository,
)
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.v1.router import get_profile_service, v1_router
from cbrowser.services.profile_service import (
    ConstraintViolationError,
    DatabaseLockError,
    ProfileService,
)
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError

logger = logging.getLogger("cbrowser.api")


def create_app(
    db_path: Path | str | None = None,
    service: ProfileService | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal service
        engine = None

        # Configure event logger to output to stderr
        event_logger = logging.getLogger("cbrowser.events")
        event_logger.setLevel(logging.INFO)
        if not event_logger.handlers:
            h = logging.StreamHandler(sys.stderr)
            h.setFormatter(logging.Formatter("%(message)s"))
            event_logger.addHandler(h)

        if service is None:
            resolved_db = Path(
                db_path or os.environ.get("CBROWSER_DB_PATH", "/data/cbrowser.db")
            ).resolve()
            resolved_db.parent.mkdir(parents=True, exist_ok=True)
            run_database_migrations(resolved_db)
            engine, session_maker = create_engine_and_maker(resolved_db)
            repo = ProfileRepository(session_maker)
            service = ProfileService(repo)

        app.dependency_overrides[get_profile_service] = lambda: service
        yield
        if engine:
            await engine.dispose()

    app = FastAPI(
        title="CBrowser Control API",
        version="2.0.0",
        description="Minimal coherent v2 Control API for profile lifecycle and runtime convergence.",
        lifespan=lifespan,
    )

    @app.exception_handler(ConstraintViolationError)
    async def constraint_violation_handler(
        request: Request, exc: ConstraintViolationError
    ):
        logger.warning("Database constraint violation")
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": "constraint_violation",
                "message": "Database constraint violation occurred",
                "retryable": False,
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        logger.warning(
            "Database integrity constraint violation: %s", type(exc).__name__
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": "constraint_violation",
                "message": "Database constraint violation occurred",
                "retryable": False,
            },
        )

    @app.exception_handler(DBAPIError)
    async def dbapi_error_handler(request: Request, exc: DBAPIError):
        logger.error("Database error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "database_error",
                "message": "A database error occurred",
                "retryable": False,
            },
        )

    @app.exception_handler(DatabaseLockError)
    async def db_lock_handler(request: Request, exc: DatabaseLockError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": "1"},
            content={
                "error": "database_busy",
                "message": "Database is temporarily locked, retryable operation",
                "retryable": True,
            },
        )

    @app.exception_handler(IdempotencyConflictError)
    async def idempotency_conflict_handler(
        request: Request, exc: IdempotencyConflictError
    ):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": "idempotency_conflict",
                "message": str(exc),
                "retryable": False,
            },
        )

    @app.exception_handler(InstanceConflictError)
    async def instance_conflict_handler(request: Request, exc: InstanceConflictError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": "instance_conflict",
                "message": str(exc),
                "retryable": False,
            },
        )

    @app.exception_handler(InvalidConfigVersionError)
    async def invalid_config_version_handler(
        request: Request, exc: InvalidConfigVersionError
    ):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "validation_error",
                "detail": [
                    {
                        "loc": ["body", "config_version"],
                        "msg": str(exc),
                        "type": "value_error",
                    }
                ],
                "retryable": False,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        # Sanitize validation errors: omit raw input values to avoid leaking injected secrets in error bodies
        sanitized_errors = []
        for err in exc.errors():
            sanitized_errors.append(
                {
                    "loc": err.get("loc", []),
                    "msg": err.get("msg", "Invalid value"),
                    "type": err.get("type", "value_error"),
                }
            )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "validation_error",
                "detail": sanitized_errors,
                "retryable": False,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        error_name = {
            400: "bad_request",
            404: "not_found",
            409: "conflict",
            422: "validation_error",
            503: "database_busy",
        }.get(exc.status_code, "http_error")
        if exc.status_code == 422:
            return JSONResponse(
                status_code=422,
                headers=exc.headers,
                content={
                    "error": "validation_error",
                    "message": str(exc.detail),
                    "detail": [
                        {"loc": ["body"], "msg": str(exc.detail), "type": "value_error"}
                    ],
                    "retryable": False,
                },
            )
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content={
                "error": error_name,
                "message": str(exc.detail),
                "retryable": exc.status_code == 503,
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled API error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_server_error",
                "message": "An internal server error occurred",
                "retryable": False,
            },
        )

    app.include_router(v1_router)
    return app
