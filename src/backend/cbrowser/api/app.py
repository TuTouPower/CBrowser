"""FastAPI Application factory for CBrowser."""

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
from cbrowser.api.internal_edge import edge_router, read_edge_proof
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
from cbrowser.api.v1.router import get_profile_service, v1_router
from cbrowser.network_config import DEFAULT_HTTPS_PORT, derive_origin_whitelist
from cbrowser.shared.client_ip import parse_trusted_proxy_cidrs
from cbrowser.shared.viewer_grants import ViewerGrantAuthority
from cbrowser.auth.dependencies import get_auth_service
from cbrowser.auth.service import AuthService
from cbrowser.service_errors import ServiceNotConfiguredError
from cbrowser.services.artifact_service import ArtifactService, ArtifactStore
from cbrowser.services.control_service import ProfileControlService
from cbrowser.adapters.database.db_errors import classify_dbapi_error
from cbrowser.services.profile_service import (
    ConstraintViolationError,
    DatabaseLockError,
    DatabaseUnavailableError,
    ProfileService,
    ReferenceValidationError,
)
from cbrowser.services.tunnel_registry import AutomationTunnelRegistry
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("cbrowser.api")


def _deploy_https_port() -> int:
    """Deployment HTTPS port: CBROWSER_HTTPS_PORT or the single default.

    A malformed value fails startup loudly instead of silently serving a
    different port's origins (t054): the port is a deploy-time input, and
    a wrong Origin whitelist is a security-relevant misconfiguration.
    """
    raw = os.environ.get("CBROWSER_HTTPS_PORT")
    if not raw:
        return DEFAULT_HTTPS_PORT
    try:
        port = int(raw)
    except ValueError:
        raise ValueError(
            f"CBROWSER_HTTPS_PORT must be an integer, got {raw!r}"
        ) from None
    if not 1 <= port <= 65535:
        raise ValueError(
            f"CBROWSER_HTTPS_PORT must be between 1 and 65535, got {port}"
        )
    return port


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
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    503: "database_busy",
    507: "insufficient_storage",
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
    """Build the unified ErrorResponse body for an HTTPException.

    t056 A15: the body is always ``error`` / ``message`` / ``retryable``
    plus optional structured ``details``.  A dict detail contributes its
    ``code`` / ``message`` / ``retryable`` to the top level and any
    *remaining* keys to ``details`` — the whole dict is never nested
    again under ``detail``.  A 429 maps to ``rate_limited`` (the
    Retry-After header travels on the response, set by the raiser).
    """
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
            "details": [{"loc": ["body"], "msg": text, "type": "value_error"}],
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
        body: dict[str, Any] = {
            "error": error,
            "message": message,
            "retryable": retryable,
        }
        extra = {
            key: value
            for key, value in detail.items()
            if key not in {"code", "message", "retryable"}
        }
        if extra:
            body["details"] = extra
        return body
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
    edge_proof_file: Path | str | None = None,
    viewer_grant_key_file: Path | str | None = None,
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
        # t064: edge authorization state for the Caddy forward_auth
        # resolver. Unconfigured (no files) leaves both None and the
        # resolver fails closed with 503.
        app.state.edge_proof = read_edge_proof(
            edge_proof_file or os.environ.get("CBROWSER_EDGE_PROOF_FILE")
        )
        grant_key_file = viewer_grant_key_file or os.environ.get(
            "CBROWSER_VIEWER_GRANT_KEY_FILE"
        )
        app.state.viewer_grant_authority = (
            ViewerGrantAuthority(grant_key_file) if grant_key_file else None
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
            db_path or os.environ.get("CBROWSER_DB_PATH", "/data/db/cbrowser.db")
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

        # t052: egress probes run in the Supervisor helper (Browser
        # network perspective).  Without a Supervisor the service records
        # a failed observation instead of probing from this process.
        service.set_egress_probe_runner(coordinator.egress_probe_runner())

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

        # t054: the Origin whitelist is derived from the deployment
        # HTTPS port (CBROWSER_HTTPS_PORT, default DEFAULT_HTTPS_PORT) —
        # the same input Gateway uses. There is no runtime network state,
        # no apply path, and no recovery loop.
        app.state.allowed_origins = derive_origin_whitelist(_deploy_https_port())

        yield
        if coordinator:
            await coordinator.stop()
        if engine:
            await engine.dispose()

    app = FastAPI(
        title="CBrowser Control API",
        version="2.0.0",
        description=(
            "Minimal coherent Control API for profile lifecycle and runtime "
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
        # Never log str(exc.orig): the DBAPI message carries SQL text and
        # bound parameters.  Only the numeric code, the SQLite error name
        # and the request line are safe to log.
        classification = classify_dbapi_error(exc)
        if classification.transient:
            logger.warning(
                "Transient database error: sqlite_errorcode=%s "
                "sqlite_errorname=%s method=%s path=%s",
                classification.primary_code,
                classification.error_name,
                request.method,
                request.url.path,
            )
            message = (
                "Database is temporarily locked, retryable operation"
                if classification.kind in ("busy", "locked")
                else "Database is temporarily unavailable, retryable operation"
            )
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                headers={"Retry-After": "1"},
                content={
                    "error": classification.error_code,
                    "message": message,
                    "retryable": True,
                },
            )
        logger.error(
            "Database error: sqlite_errorcode=%s sqlite_errorname=%s "
            "method=%s path=%s",
            classification.primary_code,
            classification.error_name,
            request.method,
            request.url.path,
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

    @app.exception_handler(DatabaseUnavailableError)
    async def db_unavailable_handler(
        request: Request, exc: DatabaseUnavailableError
    ):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": "1"},
            content={
                "error": "database_unavailable",
                "message": "Database is temporarily unavailable, retryable operation",
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
                "message": str(exc),
                "details": [
                    {
                        "loc": ["body", "config_version"],
                        "msg": str(exc),
                        "type": "value_error",
                    }
                ],
                "retryable": False,
            },
        )

    @app.exception_handler(ReferenceValidationError)
    async def reference_validation_handler(
        request: Request, exc: ReferenceValidationError
    ):
        # t056 A28: field-level 422, same shape as RequestValidationError.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error": "validation_error",
                "message": str(exc),
                "details": exc.details,
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
                "details": sanitized_errors,
                "retryable": False,
            },
        )

    # Registered under Starlette's HTTPException (t056 A15): FastAPI's
    # HTTPException subclasses it, so this catches both route-raised
    # errors and routing 404s (which Starlette raises itself).
    @app.exception_handler(StarletteHTTPException)
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
    app.include_router(edge_router, include_in_schema=include_internal_schema)

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
        # ErrorResponse carries its shape from the domain model
        # (error/message/retryable + optional structured details); no
        # hand-patched properties here.
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
        # t056 R1 f001: the runtime 422 body is the unified shape
        # (error/message/details/retryable, i.e. ValidationErrorResponse),
        # never FastAPI's auto-generated HTTPValidationError ({"detail":
        # [...]}). setdefault() cannot overwrite the auto-generated 422
        # entry, so every 422 response is assigned directly here — for
        # operations that declare their own 422 as well as for the ones
        # (GET routes, internal routes) that only have the generated one.
        validation_ref = {"$ref": "#/components/schemas/ValidationErrorResponse"}
        for path, methods in schema.get("paths", {}).items():
            for method, operation in methods.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                responses = operation.get("responses", {})
                if "422" not in responses:
                    continue
                responses["422"] = {
                    "description": responses["422"].get("description")
                    or "Invalid request payload",
                    "content": {
                        "application/json": {"schema": validation_ref}
                    },
                }
        # The auto-generated validation error models are now unreferenced;
        # drop them so no HTTPValidationError trace remains in the tree.
        schemas = schema.get("components", {}).get("schemas", {})
        refs: set[str] = set()

        def _collect_refs(node: Any) -> None:
            if isinstance(node, dict):
                ref = node.get("$ref")
                if isinstance(ref, str):
                    refs.add(ref)
                for value in node.values():
                    _collect_refs(value)
            elif isinstance(node, list):
                for item in node:
                    _collect_refs(item)

        _collect_refs(schema.get("paths", {}))
        _collect_refs(
            {
                name: model
                for name, model in schemas.items()
                if name not in {"HTTPValidationError", "ValidationError"}
            }
        )
        for orphan in ("HTTPValidationError", "ValidationError"):
            if f"#/components/schemas/{orphan}" not in refs:
                schemas.pop(orphan, None)
        app.openapi_schema = schema
        return schema

    app.openapi = contracted_openapi
    return app
