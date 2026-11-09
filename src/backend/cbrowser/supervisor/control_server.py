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
from urllib.parse import quote

import websockets
from cbrowser.domain.models import (
    PreviewPolicySyncRequest,
    ProfileConfig,
    ProfileRuntimeResponse,
)
from cbrowser.network_config import compute_caddyfile_sha256
from cbrowser.secret_files import read_secret_file
from cbrowser.services.tunnel_registry import AutomationTunnelRegistry
from cbrowser.supervisor.core import (
    LifecycleConflictError,
    RuntimeUnavailableError,
    SupervisorCore,
)
from cbrowser.supervisor.docker_adapter import DockerSandboxError
from cbrowser.supervisor.path_validator import (
    managed_socket_target,
    resolve_socket_root,
)
from cbrowser.supervisor.port_allocator import PortPoolExhaustedError
from cbrowser.supervisor.protocol import (
    ConvergeStreamsRequest,
    ProfileRuntimeStatus,
    ReadinessResponse,
    RebuildEdgeRequest,
    ReconcileAllResponse,
    ResetBlockedRequest,
    ResetBlockedResponse,
    PreviewPolicySyncResponse,
    SearchDefaultsRetryRequest,
    SearchDefaultsStatusResponse,
    StartProfileRequest,
    StartProfileResponse,
    StopProfileRequest,
    StopProfileResponse,
    TransportObservationResponse,
    AnswerAttendantDialogRequest,
    AnswerAttendantDialogResponse,
    AttendantDialogsResponse,
    CloseTunnelsRequest,
    CloseTunnelsResponse,
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

    # t031: live Supervisor-layer tunnels + the generation fence.
    # Direct Supervisor-token holders are infrastructure-trusted (the
    # token is the inter-service credential); automation clients are
    # fenced at the API proxy, and forwarded handshakes carrying a
    # generation at or below the fence are stale and rejected here.
    app.state.supervisor_tunnels = AutomationTunnelRegistry(
        layer="supervisor"
    )

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
                f"/api/v1/internal/supervisor/profiles/{quote(req.profile_id, safe='')}/versions/{req.config_version}",
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
        except LifecycleConflictError:
            raise HTTPException(409, "Conflicting lifecycle operation") from None
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
                f"/api/v1/internal/supervisor/profiles/{quote(profile_id, safe='')}/runtime",
                headers=core._auth_headers(),
            )
            response.raise_for_status()
            runtime = ProfileRuntimeResponse.model_validate(response.json())
        except Exception:  # noqa: BLE001 - runtime state query failure mapped to 503 Service Unavailable
            raise HTTPException(503, "Persisted runtime state is unavailable") from None
        if session and session.runtime_instance_id == runtime.runtime_instance_id:
            return ProfileRuntimeStatus(
                profile_id=profile_id,
                runtime_instance_id=session.runtime_instance_id,
                observed_state=session.observed_state,
                desired_state=runtime.desired_state,
                udp_mux_port=session.udp_mux_port,
                browser_container_id=session.browser_container_id,
                stream_container_id=session.stream_container_id,
                restart_blocked=runtime.restart_blocked,
                failure_count=runtime.failure_count,
            )
        else:
            return ProfileRuntimeStatus(
                profile_id=profile_id,
                runtime_instance_id=runtime.runtime_instance_id,
                observed_state=runtime.observed_state,
                desired_state=runtime.desired_state,
                udp_mux_port=None,
                browser_container_id=None,
                stream_container_id=None,
                restart_blocked=runtime.restart_blocked,
                failure_count=runtime.failure_count,
            )

    @app.get(
        "/supervisor/v1/profiles/{profile_id}/search-defaults",
        response_model=SearchDefaultsStatusResponse,
        dependencies=[Depends(verify_token)],
    )
    async def get_search_defaults(profile_id: str):
        instance_id, search_defaults = await core.get_search_defaults(profile_id)
        return SearchDefaultsStatusResponse(
            profile_id=profile_id,
            runtime_instance_id=instance_id,
            search_defaults=search_defaults,
        )

    @app.get(
        "/supervisor/v1/profiles/{profile_id}/transport",
        response_model=TransportObservationResponse,
        dependencies=[Depends(verify_token)],
    )
    async def get_transport(profile_id: str):
        observation = core.get_transport_observation(profile_id)
        return TransportObservationResponse(
            profile_id=profile_id,
            runtime_instance_id=observation.runtime_instance_id,
            transport=observation,
        )

    @app.post(
        "/supervisor/v1/reconcile",
        response_model=ReconcileAllResponse,
        dependencies=[Depends(verify_token)],
    )
    async def reconcile_all():
        return await core.reconcile_all()

    @app.get(
        "/supervisor/v1/readiness",
        response_model=ReadinessResponse,
        dependencies=[Depends(verify_token)],
    )
    async def readiness():
        return await core.readiness()

    @app.post(
        "/supervisor/v1/profiles/search-defaults/retry",
        dependencies=[Depends(verify_token)],
    )
    async def retry_search_defaults(req: SearchDefaultsRetryRequest):
        try:
            await core.retry_search_defaults(
                req.profile_id, req.runtime_instance_id, req.request_id
            )
        except LifecycleConflictError:
            raise HTTPException(409, "Conflicting lifecycle operation") from None
        except RuntimeUnavailableError:
            raise HTTPException(503, "Runtime agent unavailable") from None
        return {"status": "ok"}

    @app.post(
        "/supervisor/v1/profiles/{profile_id}/preview-policy",
        response_model=PreviewPolicySyncResponse,
        dependencies=[Depends(verify_token)],
    )
    async def sync_preview_policy(
        profile_id: str, req: PreviewPolicySyncRequest
    ):
        await core.apply_preview_policy(profile_id, req)
        return PreviewPolicySyncResponse()

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

    @app.post(
        "/supervisor/v1/profiles/{profile_id}/control/close-tunnels",
        response_model=CloseTunnelsResponse,
        dependencies=[Depends(verify_token)],
    )
    async def close_control_tunnels(
        profile_id: str, req: CloseTunnelsRequest
    ):
        """t031: close every live Supervisor tunnel for the profile.

        Called by the API coordinator during a takeover (control moves
        to the user). The generation fence advances even when no tunnel
        is live, so stale forwarded handshakes stay rejected. The
        resident dialog attendant is released best-effort through the
        Agent control channel; a False there degrades to the attendant's
        own release-on-stop path and never blocks the tunnel close.
        """
        registry = getattr(app.state, "supervisor_tunnels", None)
        closed: list[str] = []
        if registry is not None:
            closed = await registry.close_all_for_profile(
                profile_id, generation=req.generation
            )
        attendant_released = await core.release_dialog_attendant(profile_id)
        return CloseTunnelsResponse(
            profile_id=profile_id,
            generation=req.generation,
            closed_tunnel_ids=closed,
            attendant_released=attendant_released,
        )

    @app.get(
        "/supervisor/v1/profiles/{profile_id}/control/dialogs",
        response_model=AttendantDialogsResponse,
        dependencies=[Depends(verify_token)],
    )
    async def list_control_dialogs(profile_id: str):
        """t031: peek dialogs held by the resident attendant.

        A session attached after a dialog opened cannot observe it
        through its own CDP session, so this peek is how a later
        session discovers a held dialog before answering it.
        """
        dialogs = await core.list_attendant_dialogs(profile_id)
        return AttendantDialogsResponse(
            profile_id=profile_id,
            dialogs=dialogs if dialogs is not None else [],
        )

    @app.post(
        "/supervisor/v1/profiles/{profile_id}/control/answer-dialog",
        response_model=AnswerAttendantDialogResponse,
        dependencies=[Depends(verify_token)],
    )
    async def answer_control_dialog(
        profile_id: str, req: AnswerAttendantDialogRequest
    ):
        """t031: answer a held dialog on the attendant's session."""
        answered = await core.answer_attendant_dialog(
            profile_id,
            req.target_id,
            req.accept,
            req.prompt_text,
        )
        if answered is None:
            raise HTTPException(
                status_code=404, detail="no held dialog for target"
            )
        return AnswerAttendantDialogResponse(
            profile_id=profile_id,
            dialog=answered,
            action="accept" if req.accept else "dismiss",
        )

    @app.websocket("/supervisor/v1/profiles/{profile_id}/cdp")
    async def cdp_proxy(websocket: WebSocket, profile_id: str):
        """Proxy an authorized CDP WebSocket to this Profile's Agent UDS."""
        token = _bearer_token(websocket.headers.get("authorization", ""))
        if not token or not hmac.compare_digest(
            token.encode("utf-8"),
            expected_token.get_secret_value().encode("utf-8"),
        ):
            logger.warning("CDP WebSocket rejected: invalid supervisor token")
            await websocket.close(code=4401)
            return
        # t031: forwarded handshakes carry the control generation the
        # API proxy claimed with. At or below the fence means a stale
        # API process replaying a pre-takeover generation: reject.
        # Absent header = direct infrastructure caller (trusted token).
        registry = getattr(app.state, "supervisor_tunnels", None)
        presented_generation: int | None = None
        raw_generation = websocket.headers.get("x-cbrowser-control-generation")
        if raw_generation is not None:
            try:
                presented_generation = int(raw_generation)
            except ValueError:
                presented_generation = None
        if (
            registry is not None
            and registry.is_generation_fenced(profile_id, presented_generation)
        ):
            logger.warning(
                "CDP WebSocket rejected: stale control generation "
                "profile=%s generation=%s",
                profile_id,
                presented_generation,
            )
            await websocket.close(code=4403, reason="control_revoked")
            return
        await websocket.accept()

        session = core._sessions.get(profile_id)
        if session is None or session.observed_state != "running":
            logger.warning("CDP WebSocket rejected: profile is not running")
            await websocket.close(code=4404)
            return

        tunnel_record = None
        if registry is not None:
            tunnel_record = registry.register(
                profile_id,
                lambda: websocket.close(
                    code=4403, reason="control_revoked"
                ),
                generation=presented_generation,
            )

        root = (
            getattr(core, "socket_root", None)
            or getattr(core.docker.validator, "socket_root", None)
            or resolve_socket_root()
        )
        upstream = None
        tasks: list[Any] = []
        try:
            with managed_socket_target(
                root, profile_id, session.runtime_instance_id
            ) as uds_target:
                if not Path(uds_target).is_socket():
                    await websocket.close(code=1011)
                    return
                upstream = await websockets.unix_connect(
                    uds_target,
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
            if tunnel_record is not None and registry is not None:
                registry.unregister(tunnel_record.tunnel_id)
            try:
                await websocket.close()
            except Exception:  # noqa: BLE001 - already-closed client socket is harmless
                pass

    def _write_execution_receipt(
        operation_id: str,
        generation: int,
        candidate_hash: str,
        result: dict,
        *,
        restoring: bool,
    ) -> None:
        journal = getattr(core, "operations", None)
        if journal is None:
            return
        journal.record_network_execution(
            operation_id,
            generation,
            candidate_hash,
            result,
            restoring=restoring,
        )

    @app.post(
        "/supervisor/v1/network/rebuild-edge",
        dependencies=[Depends(verify_token)],
    )
    async def rebuild_edge(
        req: RebuildEdgeRequest,
        operation_id: Annotated[
            str | None, Header(alias="X-CBrowser-Operation-Id")
        ] = None,
        execution_generation: Annotated[
            str | None, Header(alias="X-CBrowser-Execution-Generation")
        ] = None,
        candidate_hash: Annotated[
            str | None, Header(alias="X-CBrowser-Candidate-Hash")
        ] = None,
        restore: Annotated[
            str | None, Header(alias="X-CBrowser-Restore")
        ] = None,
    ):
        generation: int | None = None
        if execution_generation is not None:
            try:
                generation = int(execution_generation)
            except ValueError:
                generation = None
        restoring = restore == "1"
        verified = bool(
            operation_id and generation is not None and candidate_hash
        )

        if verified and not restoring:
            try:
                actual_hash = compute_caddyfile_sha256(
                    Path(req.caddyfile_path).read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError):
                actual_hash = ""
            if actual_hash != candidate_hash:
                _write_execution_receipt(
                    operation_id,
                    generation,
                    candidate_hash,
                    {
                        "status": "rejected",
                        "reason": "candidate snapshot hash mismatch",
                        "docker_verified": False,
                        "operation_id": operation_id,
                        "execution_generation": generation,
                        "candidate_hash": candidate_hash,
                        "caddyfile_sha256": actual_hash,
                    },
                    restoring=False,
                )
                raise HTTPException(409, "candidate snapshot hash mismatch")

        try:
            if restoring:
                result = await core.restore_edge_proxy(
                    old_version=req.target_version,
                    bind_host=req.bind_host,
                    https_port=req.https_port,
                    caddyfile_path=req.caddyfile_path,
                    operation_id=operation_id,
                    execution_generation=generation,
                )
            else:
                result = await core.rebuild_edge_proxy(
                    target_version=req.target_version,
                    bind_host=req.bind_host,
                    https_port=req.https_port,
                    caddyfile_path=req.caddyfile_path,
                    operation_id=operation_id,
                    execution_generation=generation,
                    candidate_hash=candidate_hash if verified else None,
                    restoring=restoring,
                )
        except DockerSandboxError as exc:
            if verified:
                _write_execution_receipt(
                    operation_id,
                    generation,
                    candidate_hash,
                    {
                        "status": "rejected",
                        "reason": str(exc),
                        "docker_verified": False,
                        "operation_id": operation_id,
                        "execution_generation": generation,
                        "candidate_hash": candidate_hash,
                    },
                    restoring=restoring,
                )
            raise HTTPException(409, str(exc)) from None

        if verified:
            _write_execution_receipt(
                operation_id,
                generation,
                candidate_hash,
                {
                    "status": "ok",
                    "docker_verified": True,
                    "operation_id": operation_id,
                    "execution_generation": generation,
                    "candidate_hash": candidate_hash,
                    "restoring": restoring,
                },
                restoring=restoring,
            )
        return {
            **result,
            "receipt_verified": verified,
            "operation_id": operation_id,
            "execution_generation": generation,
            "candidate_hash": candidate_hash,
        }

    @app.post(
        "/supervisor/v1/network/converge-streams",
        dependencies=[Depends(verify_token)],
    )
    async def converge_streams(req: ConvergeStreamsRequest):
        return await core.converge_network_streams(
            target_version=req.target_version,
            bind_host=req.bind_host,
            advertised_ip=req.advertised_ip,
        )

    return app
