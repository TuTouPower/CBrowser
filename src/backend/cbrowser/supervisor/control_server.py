"""FastAPI Internal Control Server for CBrowser Supervisor.

AC-003:
- Authenticated HTTP control plane using Bearer token from external token file.
- Unauthorized requests rejected with 401.
- Endpoints:
  - GET /supervisor/v1/health
  - POST /supervisor/v1/profiles/start
  - POST /supervisor/v1/profiles/stop
  - GET /supervisor/v1/profiles/{profile_id}/status
  - POST /supervisor/v1/profiles/reset-blocked
"""

from __future__ import annotations

import asyncio
import hmac
import inspect
import logging
from pathlib import Path
from typing import Annotated, Any

import websockets
from cbrowser.domain.models import ProfileConfig
from cbrowser.secret_files import read_secret_file
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.port_allocator import PortPoolExhaustedError
from cbrowser.supervisor.protocol import (
    ProfileRuntimeStatus,
    ResetBlockedRequest,
    ResetBlockedResponse,
    StartProfileRequest,
    StartProfileResponse,
    StopProfileRequest,
    StopProfileResponse,
)
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, status
from pydantic import SecretStr

logger = logging.getLogger("cbrowser.supervisor.control_server")


def _bearer_token(authorization: str) -> str:
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def create_control_app(
    core: SupervisorCore,
    token_file: Path | str,
) -> FastAPI:
    app = FastAPI(title="CBrowser Supervisor Control API", version="1.0.0")

    try:
        expected_token = SecretStr(
            read_secret_file(
                token_file,
                label="Supervisor control token",
                minimum_bytes=32,
            )
        )
    except RuntimeError as exc:
        raise ValueError(str(exc)) from None

    def verify_token(authorization: Annotated[str | None, Header()] = None) -> None:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid Bearer authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )
        provided_token = authorization[len("Bearer ") :].strip()
        if not hmac.compare_digest(
            provided_token.encode("utf-8"),
            expected_token.get_secret_value().encode("utf-8"),
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized supervisor token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/supervisor/v1/health", dependencies=[Depends(verify_token)])
    async def health():
        return {"status": "ok", "role": "supervisor"}

    @app.post(
        "/supervisor/v1/profiles/start",
        response_model=StartProfileResponse,
        dependencies=[Depends(verify_token)],
    )
    async def start_profile(req: StartProfileRequest):
        # Fetch profile configuration from API
        try:
            cfg_resp = await core.api.get(
                f"/api/v1/internal/supervisor/profiles/{req.profile_id}/versions/{req.config_version}",
                headers=core._auth_headers(),
            )
            if cfg_resp.status_code != 200:
                raise HTTPException(
                    status_code=cfg_resp.status_code,
                    detail="Immutable configuration is unavailable",
                )
            snapshot = cfg_resp.json()
            if (
                snapshot["profile_id"] != req.profile_id
                or snapshot["version"] != req.config_version
            ):
                raise ValueError("Immutable configuration identity mismatch")
            cfg_data = snapshot["config"]
            cfg = ProfileConfig(**cfg_data)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 - config fetch/decode error mapped to 502 Bad Gateway
            logger.error("Configuration query failed: error_type=%s", type(e).__name__)
            raise HTTPException(502, "Configuration query failed") from None

        try:
            session = await core.start_profile(
                profile_id=req.profile_id,
                config=cfg,
                config_version=req.config_version,
                force=req.force,
                operation_id=req.operation_id,
            )
            b_container = core.docker.get_browser_container_name(req.profile_id)
            s_container = core.docker.get_stream_container_name(req.profile_id)
            return StartProfileResponse(
                profile_id=req.profile_id,
                status="running",
                runtime_instance_id=session.runtime_instance_id,
                udp_mux_port=session.udp_mux_port,
                browser_container=b_container,
                stream_container=s_container,
            )
        except PortPoolExhaustedError:
            raise HTTPException(503, "UDP mux port pool exhausted") from None
        except Exception as e:  # noqa: BLE001 - runtime start failure mapped to 500 Internal Server Error
            logger.error("Runtime start failed: error_type=%s", type(e).__name__)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Runtime start failed",
            ) from None

    @app.post(
        "/supervisor/v1/profiles/stop",
        response_model=StopProfileResponse,
        dependencies=[Depends(verify_token)],
    )
    async def stop_profile(req: StopProfileRequest):
        try:
            result = await core.stop_profile(
                req.profile_id,
                expected_instance=req.runtime_instance_id,
                operation_id=req.operation_id,
            )
            return StopProfileResponse(**result)
        except ValueError:
            raise HTTPException(409, "Conflicting lifecycle operation") from None
        except Exception as e:  # noqa: BLE001 - runtime stop failure mapped to 500 Internal Server Error
            logger.error("Runtime stop failed: error_type=%s", type(e).__name__)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Runtime stop failed",
            ) from None

    @app.get(
        "/supervisor/v1/profiles/{profile_id}/status",
        response_model=ProfileRuntimeStatus,
        dependencies=[Depends(verify_token)],
    )
    async def get_status(profile_id: str):
        session = core._sessions.get(profile_id)
        try:
            response = await core.api.get(
                f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime",
                headers=core._auth_headers(),
            )
            response.raise_for_status()
            runtime = response.json()
        except Exception:  # noqa: BLE001 - runtime state query failure mapped to 503 Service Unavailable
            raise HTTPException(503, "Persisted runtime state is unavailable") from None
        if session and session.runtime_instance_id == runtime["runtime_instance_id"]:
            return ProfileRuntimeStatus(
                profile_id=profile_id,
                runtime_instance_id=session.runtime_instance_id,
                observed_state=session.observed_state,
                desired_state=runtime["desired_state"],
                udp_mux_port=session.udp_mux_port,
                browser_container_id=session.browser_container_id,
                stream_container_id=session.stream_container_id,
                restart_blocked=runtime["restart_blocked"],
                failure_count=runtime["failure_count"],
            )
        else:
            return ProfileRuntimeStatus(
                profile_id=profile_id,
                runtime_instance_id=runtime["runtime_instance_id"],
                observed_state=runtime["observed_state"],
                desired_state=runtime["desired_state"],
                udp_mux_port=None,
                browser_container_id=None,
                stream_container_id=None,
                restart_blocked=runtime["restart_blocked"],
                failure_count=runtime["failure_count"],
            )

    @app.post(
        "/supervisor/v1/profiles/reset-blocked",
        response_model=ResetBlockedResponse,
        dependencies=[Depends(verify_token)],
    )
    async def reset_blocked(
        req: ResetBlockedRequest,
        operation_id: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    ):
        await core.reset_blocked(req.profile_id, operation_id)
        return ResetBlockedResponse(profile_id=req.profile_id)

    @app.get(
        "/supervisor/v1/profiles/{profile_id}/resources",
        dependencies=[Depends(verify_token)],
    )
    async def resources(profile_id: str):
        from dataclasses import asdict

        decision = (
            core.resource_monitor.policy.get_decision(profile_id)
            if core.resource_monitor is not None
            else None
        )
        return {
            "profile_id": profile_id,
            "decision": asdict(decision) if decision else None,
        }

    @app.websocket("/supervisor/v1/profiles/{profile_id}/cdp")
    async def cdp_proxy(websocket: WebSocket, profile_id: str):
        """Proxy an authorized CDP WebSocket to this Profile's Agent UDS."""
        await websocket.accept()
        token = _bearer_token(websocket.headers.get("authorization", ""))
        if not token or not hmac.compare_digest(
            token.encode("utf-8"),
            expected_token.get_secret_value().encode("utf-8"),
        ):
            logger.warning("CDP WebSocket rejected: invalid supervisor token")
            await websocket.close(code=4401)
            return

        session = core._sessions.get(profile_id)
        if session is None or session.observed_state != "running":
            logger.warning("CDP WebSocket rejected: profile is not running")
            await websocket.close(code=4404)
            return

        try:
            runtime_dir = core.docker.validator.get_runtime_dir(profile_id)
            sock_path = core.docker.validator.validate_runtime_source(
                profile_id, runtime_dir / "agent.sock"
            )
        except Exception:  # noqa: BLE001 - invalid runtime path is closed without leaking details
            await websocket.close(code=1011)
            return
        if not sock_path.is_socket():
            await websocket.close(code=1011)
            return

        upstream = None
        tasks: list[Any] = []
        try:
            upstream = await websockets.unix_connect(
                str(sock_path),
                uri="ws://localhost/cdp",
                max_size=32 * 1024 * 1024,
                ping_interval=10,
                ping_timeout=10,
                **(
                    {"proxy": None}
                    if "proxy" in inspect.signature(websockets.connect).parameters
                    else {}
                ),
            )

            async def client_to_upstream():
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    if message.get("text") is not None:
                        await upstream.send(message["text"])
                    elif message.get("bytes") is not None:
                        await upstream.send(message["bytes"])

            async def upstream_to_client():
                async for message in upstream:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            tasks = [
                asyncio.create_task(client_to_upstream(), name="client_to_upstream"),
                asyncio.create_task(upstream_to_client(), name="upstream_to_client"),
            ]
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            logger.warning(
                "CDP task finished: profile=%s done=%s pending=%s",
                profile_id,
                [task.get_name() for task in done],
                [task.get_name() for task in pending],
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
        except Exception as exc:  # noqa: BLE001 - tunnel teardown never crashes the control service
            logger.info(
                "CDP tunnel closed: profile=%s error_type=%s detail=%s",
                profile_id,
                type(exc).__name__,
                str(exc)[:200],
            )
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if upstream is not None:
                await upstream.close()
            try:
                await websocket.close()
            except Exception:  # noqa: BLE001 - already-closed client socket is harmless
                pass

    return app
