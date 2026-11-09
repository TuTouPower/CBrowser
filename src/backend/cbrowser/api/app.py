"""FastAPI Application factory for CBrowser v2."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

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
from cbrowser.api.v1.preview_router import preview_router
from cbrowser.api.v1.auth_router import auth_router
from cbrowser.api.v1.automation_router import automation_router
from cbrowser.api.v1.control_router import (
    control_router,
    get_control_service,
    get_optional_control_service,
)
from cbrowser.api.v1.font_sets_router import font_set_router
from cbrowser.api.v1.network_router import (
    create_network_router,
    get_network_service,
)
from cbrowser.api.v1.router import get_profile_service, v1_router
from cbrowser.network_config import derive_origin_whitelist
from cbrowser.services.network_service import GatewayPublicationClient, NetworkService
from cbrowser.auth.client_ip import parse_trusted_proxy_cidrs
from cbrowser.auth.dependencies import get_auth_service
from cbrowser.auth.service import AuthService
from cbrowser.gateway.config import NetworkPublicationAuthority
from cbrowser.gateway.endpoint import normalize_origins
from cbrowser.service_errors import ServiceNotConfiguredError
from cbrowser.services.artifact_service import ArtifactService, ArtifactStore
from cbrowser.services.control_service import ProfileControlService
from cbrowser.services.profile_service import (
    ConstraintViolationError,
    DatabaseLockError,
    ProfileService,
)
from cbrowser.services.tunnel_registry import AutomationTunnelRegistry
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


_STATUS_ERROR_NAMES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    503: "database_busy",
}

_STATUS_MESSAGES = {
    400: "Bad request",
    401: "Authentication required",
    403: "Forbidden",
    404: "Not found",
    409: "Conflict",
    422: "Invalid request payload",
    503: "Service unavailable",
}


def _http_error_content(exc: HTTPException) -> dict[str, Any]:
    status_code = exc.status_code
    error_name = _STATUS_ERROR_NAMES.get(status_code, "http_error")
    generic_message = _STATUS_MESSAGES.get(status_code, "Request failed")
    detail = exc.detail
    if status_code == 422:
        text = detail.get("message") if isinstance(detail, dict) else detail
        if not isinstance(text, str) or not text:
            text = generic_message
        return {
            "error": "validation_error",
            "message": text,
            "detail": [{"loc": ["body"], "msg": text, "type": "value_error"}],
            "retryable": False,
        }
    if isinstance(detail, dict):
        code = detail.get("code")
        error = code if isinstance(code, str) and code else error_name
        message = detail.get("message")
        if not isinstance(message, str) or not message:
            message = generic_message
        retryable = detail.get("retryable")
        if not isinstance(retryable, bool):
            retryable = status_code == 503
        return {
            "error": error,
            "message": message,
            "detail": detail,
            "retryable": retryable,
        }
    return {
        "error": error_name,
        "message": detail if isinstance(detail, str) else generic_message,
        "retryable": status_code == 503,
    }


def create_app(
    db_path: Path | str | None = None,
    service: ProfileService | None = None,
    supervisor_token_file: Path | str | None = None,
    admin_password_file: Path | str | None = None,
    gateway_token_file: Path | str | None = None,
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
        app.state.allowed_origins = []

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

        repo = getattr(service, "repo", None) or ProfileRepository(session_maker)
        if service is None:
            service = ProfileService(repo, data_root=resolved_db.parent)
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
        # Finish artifact deletions whose durable intent survived a
        # previous process exit; failures keep their intent for next time.
        await app.state.artifact_service.resume_pending_deletions()

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

        # t031: human-priority control state. The API is the sole
        # business-DB writer; the service's hooks close tunnels (API
        # registry here, Supervisor over HTTP) and publish SSE before
        # any observer sees the new state.
        automation_tunnels = AutomationTunnelRegistry(layer="api")
        app.state.automation_tunnels = automation_tunnels

        async def _close_api_tunnels(
            profile_id: str, generation: int
        ) -> bool:
            await automation_tunnels.close_all_for_profile(
                profile_id, generation=generation
            )
            return True

        control_service = ProfileControlService(
            session_maker,
            publish_profile_change=coordinator.publish_profile_change,
            close_supervisor_tunnels=coordinator.close_supervisor_tunnels,
            close_api_tunnels=_close_api_tunnels,
        )
        coordinator.control_service = control_service
        app.state.control_service = control_service
        app.dependency_overrides[get_control_service] = lambda: control_service
        app.dependency_overrides[get_optional_control_service] = (
            lambda: control_service
        )

        await coordinator.start()

        resolved_admin_pwd_file = admin_password_file or os.environ.get(
            "CBROWSER_ADMIN_PASSWORD_FILE"
        )
        await auth_service.init_admin_password(resolved_admin_pwd_file)

        # t042: Network Access Service and Applied Configuration
        export_network_dir = resolved_db.parent / "network"
        publication_authority = NetworkPublicationAuthority()
        gateway_publication_client = None
        if app.state.gateway_token is not None:
            gateway_publication_client = GatewayPublicationClient(
                base_url=os.environ.get(
                    "CBROWSER_GATEWAY_PUBLICATION_URL", "http://gateway:18080"
                ),
                token=app.state.gateway_token,
            )
        network_service = NetworkService(
            repo=repo,
            auth_service=auth_service,
            supervisor_client=coordinator,
            export_dir=export_network_dir,
            on_origins_updated=lambda origins: setattr(app.state, "allowed_origins", list(origins)),
            gateway=publication_authority,
            gateway_client=gateway_publication_client,
        )
        app.state.network_service = network_service
        app.state.network_publication_authority = publication_authority
        app.dependency_overrides[get_network_service] = lambda: network_service
        app.state.caddy_ca_dir = Path(
            os.environ.get("CBROWSER_CADDY_CA_DIR", "/data/caddy/pki/authorities/local")
        )

        initializer = getattr(repo, "initialize_network_from_disk", None)
        if callable(initializer):
            await initializer(export_network_dir)
        applied_settings = await network_service.get_settings()
        app.state.allowed_origins = derive_origin_whitelist(applied_settings.applied_version)
        publication_authority.import_baseline(
            list(app.state.allowed_origins),
            generation=applied_settings.applied_version.version - 1,
            snapshot_hash=applied_settings.applied_version.caddyfile_sha256,
        )
        # P1-3: never run recovery once synchronously before Gateway /
        # Supervisor are ready. Retry in the background until the pending
        # transaction (if any) reaches a recovery-complete state, so a
        # recovery_complete=False txn cannot block applies with 409 forever.
        async def _network_recovery_loop() -> None:
            attempt = 0
            while True:
                attempt += 1
                try:
                    verdict = await network_service.recover_pending_operation()
                except Exception as exc:
                    logger.warning(
                        "Network recovery attempt %d failed: error_type=%s; retrying",
                        attempt,
                        type(exc).__name__,
                    )
                    await asyncio.sleep(5.0)
                    continue
                try:
                    current = await repo.get_current_network_transaction()
                except Exception as exc:
                    # Transient DB failure must not look like a completed
                    # recovery: keep retrying instead of returning.
                    logger.warning(
                        "Network recovery state read failed: error_type=%s; retrying",
                        type(exc).__name__,
                    )
                    await asyncio.sleep(5.0)
                    continue
                if current is None or current.recovery_complete:
                    logger.info(
                        "Network recovery complete: verdict=%s attempt=%d",
                        verdict,
                        attempt,
                    )
                    return
                logger.warning(
                    "Network recovery incomplete: verdict=%s attempt=%d "
                    "recovery_complete=False; retrying",
                    verdict,
                    attempt,
                )
                await asyncio.sleep(5.0)

        recovery_task = asyncio.create_task(_network_recovery_loop())

        yield
        recovery_task.cancel()
        try:
            await recovery_task
        except (asyncio.CancelledError, Exception):
            pass
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
        logger.exception(
            "Database error: %s (%s)", type(exc).__name__, getattr(exc, "orig", "")
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "database_error",
                "message": "A database error occurred",
                "retryable": False,
            },
        )

    @app.exception_handler(ServiceNotConfiguredError)
    async def service_not_configured_handler(
        request: Request, exc: ServiceNotConfiguredError
    ):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": "service_not_configured",
                "message": str(exc),
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error": "validation_error",
                "message": _STATUS_MESSAGES.get(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, "Request failed"
                ),
                "detail": sanitized_errors,
                "retryable": False,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content=_http_error_content(exc),
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
    app.include_router(font_set_router)
    app.include_router(artifact_router)
    app.include_router(preview_router)
    app.include_router(create_network_router())
    app.include_router(automation_router)
    app.include_router(control_router)
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
        """Build the contracted schema.

        An optional request field carrying a server-applied ``default`` is not
        emitted with that keyword: openapi-typescript treats ``default`` as a
        required client-side member, which would misrepresent an omittable
        field such as ``fingerprint_platform``.
        """
        if getattr(app, "openapi_schema", None):
            return app.openapi_schema
        schema = original_openapi()
        for component in schema.get("components", {}).get("schemas", {}).values():
            platform = component.get("properties", {}).get("fingerprint_platform")
            if isinstance(platform, dict):
                platform.pop("default", None)
        components = schema.setdefault("components", {})
        error_schema = components.setdefault("schemas", {}).get("ErrorResponse")
        if isinstance(error_schema, dict):
            error_schema.setdefault("properties", {})["detail"] = {}
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
                "SupervisorServiceBearer": {
                    "type": "http",
                    "scheme": "bearer",
                },
                "GatewayServiceBearer": {
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
                elif path.startswith("/api/v1/internal/supervisor"):
                    # Supervisor RPC and the Artifact ingest surface both
                    # authenticate with the Supervisor service identity.
                    security = [{"SupervisorServiceBearer": []}]
                elif path.startswith("/api/v1/internal/gateway"):
                    security = [{"GatewayServiceBearer": []}]
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
