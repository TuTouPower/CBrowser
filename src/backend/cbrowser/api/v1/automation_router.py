"""Independent automation-token CDP endpoint proxied through Supervisor."""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Annotated
from urllib.parse import quote, urlsplit

import websockets
from cbrowser.adapters.database.models import SessionModel
from cbrowser.api.v1.router import get_profile_service
from cbrowser.auth.dependencies import require_user_session
from cbrowser.domain.models import AutomationEndpointResponse
from cbrowser.services.profile_service import ProfileNotFoundError, ProfileService
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from pydantic import SecretStr

automation_router = APIRouter(prefix="/api/v1", tags=["automation"])
legacy_cdp_router = APIRouter(prefix="/api", include_in_schema=False)
logger = logging.getLogger("cbrowser.api.automation")


def _cdp_path(profile_id: str) -> str:
    return f"/api/v1/automation/profiles/{profile_id}/cdp"


def _bearer_token(authorization: str) -> str:
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


@automation_router.get(
    "/profiles/{profile_id}/automation",
    response_model=AutomationEndpointResponse,
)
async def automation_status(
    profile_id: str,
    request: Request,
    session: Annotated[SessionModel, Depends(require_user_session)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
):
    try:
        runtime = await service.get_runtime(profile_id)
    except ProfileNotFoundError:
        raise HTTPException(404, f"Profile {profile_id} not found") from None
    coordinator = getattr(request.app.state, "coordinator", None)
    return AutomationEndpointResponse(
        profile_id=profile_id,
        cdp_ws_path=_cdp_path(profile_id),
        supervisor_configured=bool(coordinator and coordinator.is_enabled()),
        runtime_observed_state=runtime.observed_state,
        runtime_instance_id=runtime.runtime_instance_id,
    )


def _supervisor_ws_url(base_url: str, profile_id: str) -> str:
    parsed = urlsplit(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/supervisor/v1/profiles/{quote(profile_id, safe='')}/cdp"


def _websocket_kwargs() -> dict:
    kwargs = {
        "max_size": 32 * 1024 * 1024,
        "ping_interval": 10,
        "ping_timeout": 10,
    }
    if "proxy" in inspect.signature(websockets.connect).parameters:
        kwargs["proxy"] = None
    return kwargs


@automation_router.websocket("/automation/profiles/{profile_id}/cdp")
async def automation_cdp(websocket: WebSocket, profile_id: str):
    token = _bearer_token(websocket.headers.get("authorization", ""))
    auth_service = getattr(websocket.app.state, "auth_service", None)
    if auth_service is None or not token:
        logger.warning("Automation CDP rejected: missing token")
        await websocket.close(code=4401)
        return
    from cbrowser.auth.client_ip import resolve_client_ip

    client_ip = resolve_client_ip(
        websocket.client.host if websocket.client else None,
        websocket.headers.get("x-forwarded-for"),
        getattr(websocket.app.state, "trusted_proxy_cidrs", []),
    )
    allowed, reason = await auth_service.authorize_automation(
        token, profile_id, client_ip=client_ip
    )
    if not allowed:
        logger.warning(
            "Automation CDP rejected: profile=%s reason=%s", profile_id, reason
        )
        await websocket.close(code=4408 if reason == "rate_limited" else 4401)
        return

    coordinator = getattr(websocket.app.state, "coordinator", None)
    supervisor_token = getattr(websocket.app.state, "supervisor_token", None)
    if (
        coordinator is None
        or not coordinator.is_enabled()
        or not isinstance(supervisor_token, SecretStr)
    ):
        await websocket.close(code=1011)
        return

    # t031: the handshake performs the implicit control claim (token
    # identity). A conflict (second agent, or reclaim blocked after a
    # takeover) rejects the tunnel before it opens; a success renews
    # or moves control to this agent and yields the generation that is
    # forwarded to the Supervisor as a stale-handshake fence.
    control_generation: int | None = None
    control_service = getattr(websocket.app.state, "control_service", None)
    if control_service is not None:
        token_id = await auth_service.resolve_automation_token_id(token)
        try:
            state, _ = await control_service.claim(
                profile_id, token_id, None
            )
            control_generation = state.generation
        except Exception as exc:  # noqa: BLE001 - mapped to close codes
            from cbrowser.services.control_service import (
                ControlConflictError,
                ControlNotFoundError,
            )

            if isinstance(exc, ControlNotFoundError):
                await websocket.close(code=4404)
            elif isinstance(exc, ControlConflictError):
                logger.warning(
                    "Automation CDP rejected by control: profile=%s code=%s",
                    profile_id,
                    exc.code,
                )
                await websocket.close(code=4403, reason="control_revoked")
            else:
                logger.warning(
                    "Automation CDP control claim failed: profile=%s error=%s",
                    profile_id,
                    type(exc).__name__,
                )
                await websocket.close(code=1011)
            return
    else:
        logger.warning(
            "Automation CDP without control service: profile=%s "
            "(pre-t031 degraded path)",
            profile_id,
        )

    await websocket.accept()
    registry = getattr(websocket.app.state, "automation_tunnels", None)
    tunnel_record = None
    if registry is not None:
        tunnel_record = registry.register(
            profile_id,
            lambda: websocket.close(
                code=4403, reason="control_revoked"
            ),
            generation=control_generation,
            agent_instance_id=None,
            agent_session_id=None,
        )
    upstream = None
    tasks = []
    try:
        forward_headers = {
            "Authorization": f"Bearer {supervisor_token.get_secret_value()}"
        }
        if control_generation is not None:
            # The Supervisor rejects forwarded handshakes at or below
            # its fenced generation (stale API processes after takeover).
            forward_headers["X-CBrowser-Control-Generation"] = str(
                control_generation
            )
        upstream = await websockets.connect(
            _supervisor_ws_url(coordinator.supervisor_url, profile_id),
            additional_headers=forward_headers,
            **_websocket_kwargs(),
        )

        async def client_to_supervisor():
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return
                if message.get("text") is not None:
                    await upstream.send(message["text"])
                elif message.get("bytes") is not None:
                    await upstream.send(message["bytes"])

        async def supervisor_to_client():
            async for message in upstream:
                if isinstance(message, bytes):
                    await websocket.send_bytes(message)
                else:
                    await websocket.send_text(message)

        tasks = [
            asyncio.create_task(client_to_supervisor(), name="client_to_supervisor"),
            asyncio.create_task(supervisor_to_client(), name="supervisor_to_client"),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        logger.warning(
            "Automation CDP task finished: profile=%s done=%s",
            profile_id,
            [task.get_name() for task in done],
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            task.result()
    except Exception as exc:  # noqa: BLE001 - tunnel teardown must not crash the API
        logger.warning(
            "Automation CDP tunnel closed: profile=%s error_type=%s",
            profile_id,
            type(exc).__name__,
        )
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if upstream is not None:
            await upstream.close()
        if tunnel_record is not None and registry is not None:
            registry.unregister(tunnel_record.tunnel_id)
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001 - already-closed client socket is harmless
            pass


legacy_cdp_router.add_api_websocket_route(
    "/profiles/{profile_id}/cdp", automation_cdp, name="legacy_cdp_proxy"
)
