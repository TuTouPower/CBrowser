"""FastAPI Application factory for CBrowser v2."""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from cbrowser.adapters.database.artifact_repository import ArtifactRepository
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import (
    IdempotencyConflictError,
    InstanceConflictError,
    InvalidConfigVersionError,
    ProfileRepository,
)
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.internal_artifacts import internal_artifact_router
from cbrowser.api.internal_gateway import gateway_router, read_gateway_token
from cbrowser.api.internal_supervisor import read_supervisor_token, supervisor_router
from cbrowser.api.runtime_coordinator import RuntimeCoordinator
from cbrowser.api.v1.artifact_router import artifact_router
from cbrowser.api.v1.auth_router import auth_router
from cbrowser.api.v1.automation_router import (
    automation_router,
    legacy_cdp_router,
)
from cbrowser.api.v1.router import get_profile_service, v1_router
from cbrowser.auth.client_ip import parse_trusted_proxy_cidrs
from cbrowser.auth.dependencies import get_auth_service
from cbrowser.auth.service import AuthService
from cbrowser.gateway.endpoint import normalize_origins
from cbrowser.services.artifact_service import ArtifactService, ArtifactStore
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


def _env_int(name: str, fallback: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return fallback
    try:
        value = int(raw)
    except ValueError:
        return fallback
    return value if value > 0 else fallback


def create_app(
    db_path: Path | str | None = None,
    service: ProfileService | None = None,
    supervisor_token_file: Path | str | None = None,
    admin_password_file: Path | str | None = None,
    gateway_token_file: Path | str | None = None,
    allowed_origins: list[str] | str | None = None,
    supervisor_url: str | None = None,
    require_supervisor: bool = False,
    artifacts_root: Path | str | None = None,
    max_artifact_bytes: int = 256 * 1024 * 1024,
    max_artifacts_per_profile: int = 200,
    max_profile_artifact_bytes: int = 2 * 1024 * 1024 * 1024,
    include_internal_schema: bool = False,
) -> FastAPI:
    docs_enabled = os.environ.get("CBROWSER_API_DOCS", "0") == "1"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal service
        engine = None
        coordinator = None
        app.state.supervisor_token = read_supervisor_token(
            supervisor_token_file or os.environ.get("CBROWSER_SUPERVISOR_TOKEN_FILE")
        )
        app.state.gateway_token = read_gateway_token(
            gateway_token_file or os.environ.get("CBROWSER_GATEWAY_API_TOKEN_FILE")
        )

        raw_origins = allowed_origins or os.environ.get("CBROWSER_ALLOWED_ORIGINS")
        if raw_origins:
            app.state.allowed_origins = normalize_origins(raw_origins)
        else:
            app.state.allowed_origins = []
        if not app.state.allowed_origins:
            raise RuntimeError(
                "CBROWSER_ALLOWED_ORIGINS must list at least one browser origin"
            )

        # Configure event logger to output to stderr
        event_logger = logging.getLogger("cbrowser.events")
        event_logger.setLevel(logging.INFO)
        if not event_logger.handlers:
            h = logging.StreamHandler(sys.stderr)
            h.setFormatter(logging.Formatter("%(message)s"))
            event_logger.addHandler(h)

        resolved_db = Path(
            db_path or os.environ.get("CBROWSER_DB_PATH", "/data/cbrowser.db")
        ).resolve()
        resolved_db.parent.mkdir(parents=True, exist_ok=True)
        run_database_migrations(resolved_db)
        engine, session_maker = create_engine_and_maker(resolved_db)

        if service is None:
            repo = ProfileRepository(session_maker)
            service = ProfileService(repo)
        resolved_artifacts_root = Path(
            artifacts_root or resolved_db.parent / "artifacts"
        )
        app.state.artifact_service = ArtifactService(
            ArtifactRepository(session_maker),
            ArtifactStore(resolved_artifacts_root),
            max_artifact_bytes=_env_int("ARTIFACT_MAX_BYTES", max_artifact_bytes),
            max_artifacts_per_profile=_env_int(
                "ARTIFACT_MAX_COUNT", max_artifacts_per_profile
            ),
            max_profile_bytes=_env_int(
                "ARTIFACT_MAX_TOTAL_BYTES", max_profile_artifact_bytes
            ),
        )

        app.state.trusted_proxy_cidrs = parse_trusted_proxy_cidrs(
            os.environ.get("CBROWSER_TRUSTED_PROXY_CIDRS")
        )
        auth_service = AuthService(session_maker)
        app.state.auth_service = auth_service
        app.dependency_overrides[get_auth_service] = lambda: auth_service
        app.dependency_overrides[get_profile_service] = lambda: service

        resolved_sup_url = supervisor_url or os.environ.get("CBROWSER_SUPERVISOR_URL")
        resolved_require_sup = require_supervisor or os.environ.get(
            "CBROWSER_REQUIRE_SUPERVISOR", ""
        ).lower() in ("1", "true")
        coordinator = RuntimeCoordinator(
            supervisor_url=resolved_sup_url,
            supervisor_token=app.state.supervisor_token,
            profile_service=service,
            require_supervisor=resolved_require_sup,
        )
        app.state.coordinator = coordinator
        await coordinator.start()

        resolved_admin_pwd_file = admin_password_file or os.environ.get(
            "CBROWSER_ADMIN_PASSWORD_FILE"
        )
        await auth_service.init_admin_password(resolved_admin_pwd_file)

        yield
        if coordinator:
            await coordinator.stop()
        if engine:
            await engine.dispose()

    app = FastAPI(
        title="CBrowser Control API",
        version="2.0.0",
        description=(
            "Minimal coherent v2 Control API for profile lifecycle and runtime "
            "convergence."
        ),
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
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
        # Sanitize validation errors: omit raw input values to avoid leaking secrets
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
    app.include_router(artifact_router)
    app.include_router(automation_router)
    app.include_router(legacy_cdp_router, include_in_schema=False)
    app.include_router(auth_router)
    app.include_router(
        supervisor_router, include_in_schema=include_internal_schema
    )
    app.include_router(
        internal_artifact_router, include_in_schema=include_internal_schema
    )
    app.include_router(
        gateway_router, include_in_schema=include_internal_schema
    )

    original_openapi = app.openapi

    def contracted_openapi() -> dict:
        if getattr(app, "openapi_schema", None):
            return app.openapi_schema
        schema = original_openapi()
        components = schema.setdefault("components", {})
        components.setdefault("securitySchemes", {}).update(
            {
                "sessionCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "cbrowser_session",
                },
                "csrfHeader": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-CSRF-Token",
                },
                "serviceBearer": {
                    "type": "http",
                    "scheme": "bearer",
                },
            }
        )
        error_ref = {"$ref": "#/components/schemas/ErrorResponse"}
        for path, methods in schema.get("paths", {}).items():
            for method, operation in methods.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                if path in {"/api/v1/health", "/api/v1/auth/login"}:
                    security = []
                elif path.startswith("/api/v1/internal/"):
                    security = [{"serviceBearer": []}]
                elif method in {"post", "put", "patch", "delete"}:
                    security = [{"sessionCookie": [], "csrfHeader": []}]
                else:
                    security = [{"sessionCookie": []}]
                if security:
                    operation["security"] = security
                responses = operation.setdefault("responses", {})
                codes = {"401": "Authentication required"}
                if path.startswith("/api/v1/internal/"):
                    codes.update(
                        {"403": "Service authorization denied", "503": "Service unavailable"}
                    )
                    if "{" in path:
                        codes["404"] = "Resource not found"
                    if path.endswith(("/runtimes/bind", "/runtimes/observed")):
                        codes.update(
                            {"404": "Profile not found", "409": "Instance conflict"}
                        )
                    if path.endswith("/runtime/desired-state"):
                        codes["409"] = "Lifecycle conflict"
                    if "/artifacts/" in path:
                        codes["404"] = "Profile or artifact not found"
                else:
                    codes.update(
                        {
                            "403": "Authorization or CSRF check failed",
                            "503": "Service unavailable or database busy",
                        }
                    )
                    if method in {"post", "put", "patch", "delete"}:
                        codes["422"] = "Invalid request payload"
                    if "{" in path:
                        codes["404"] = "Resource not found"
                    if path == "/api/v1/auth/login":
                        codes["429"] = "Too many failed login attempts"
                    if "/artifacts" in path:
                        codes.update(
                            {
                                "400": "Invalid artifact request",
                                "413": "Artifact exceeds per-file limit",
                                "507": "Artifact quota exceeded",
                            }
                        )
                for code, description in codes.items():
                    responses.setdefault(
                        code, {"description": description, "content": {"application/json": {"schema": error_ref}}}
                    )
        app.openapi_schema = schema
        return schema

    app.openapi = contracted_openapi
    return app
