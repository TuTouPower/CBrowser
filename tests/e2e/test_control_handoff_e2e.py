"""Human-priority control handoff E2E (t031 AC-002/AC-004/AC-005).

Collectable entries for the handoff matrix. The cloud gate collects
them (no Docker here); the real topology run is t032's. Each test
skips cleanly when the Docker topology or the required images are
unavailable, and fails for real when they are available.

Only harness APIs verified in-tree are used: GatewayTopologyHarness
(start, login_api, create_and_start_profile), the admin REST session,
automation-token creation, and a raw websockets CDP tunnel client.
"""

from __future__ import annotations

import asyncio
import json
import ssl
from pathlib import Path

import httpx
import pytest
import websockets

from e2e_env import require_e2e_env
from gateway_probe.topology import GatewayTopologyHarness

pytestmark = [pytest.mark.serial, pytest.mark.e2e_images('CBROWSER_API_TEST_IMAGE', 'CBROWSER_CADDY_TEST_IMAGE', 'CBROWSER_GATEWAY_IMAGE', 'CBROWSER_RUNTIME_TEST_IMAGE', 'CBROWSER_STREAM_TEST_IMAGE', 'CBROWSER_SUPERVISOR_TEST_IMAGE')]


async def _setup(tmp_path: Path):
    """Start the real topology, or fail/skip when Docker is unavailable.

    Docker availability is gated through e2e_env (fail in required mode,
    skip otherwise); the harness constructor resolves image/cache env.
    A start() failure -- readiness timeout, unexposed port, unregistered
    Stream Agent -- is a real failure and must propagate, not become a
    skip (review t031_test_f002).
    """
    require_e2e_env(docker=True)
    harness = GatewayTopologyHarness(tmp_path)
    await harness.start()
    return harness


def _ws_url(harness: GatewayTopologyHarness, profile_id: str) -> str:
    origin = harness.origin.replace("https://", "wss://")
    return f"{origin}/api/v1/automation/profiles/{profile_id}/cdp"


async def _automation_token(
    harness: GatewayTopologyHarness, profile_id: str, name: str
) -> str:
    headers = await harness.login_api()
    async with httpx.AsyncClient(
        base_url=harness.origin,
        headers=headers,
        verify=False,
        trust_env=False,
    ) as client:
        resp = await client.post(
            "/api/v1/automation/tokens",
            json={"name": name, "profile_ids": [profile_id]},
        )
        resp.raise_for_status()
        return resp.json()["token"]


@pytest.mark.asyncio
async def test_handoff_closes_established_tunnel_and_refuses_reconnect(
    tmp_path: Path,
) -> None:
    harness = await _setup(tmp_path)
    try:
        profile = await harness.create_and_start_profile("handoff_profile")
        profile_id = profile["profile_id"]
        token = await _automation_token(harness, profile_id, "handoff-bot")
        ssl_ctx = ssl._create_unverified_context()

        # Establish a real tunnel through API -> Supervisor -> Agent.
        async with websockets.connect(
            _ws_url(harness, profile_id),
            additional_headers={"Authorization": f"Bearer {token}"},
            ssl=ssl_ctx,
            max_size=None,
        ) as ws:
            await ws.send(
                json.dumps({"id": 1, "method": "Target.getTargets"})
            )
            first = json.loads(
                await asyncio.wait_for(ws.recv(), timeout=15)
            )
            assert first.get("id") == 1, "tunnel did not answer getTargets"

            # Human takeover through the real API control path.
            headers = await harness.login_api()
            async with httpx.AsyncClient(
                base_url=harness.origin,
                headers=headers,
                verify=False,
                trust_env=False,
            ) as client:
                handoff = await client.post(
                    f"/api/v1/profiles/{profile_id}/control/handoff",
                    json={"reason": "cli_handoff"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert handoff.status_code == 200
                assert handoff.json()["owner"] == "user"

            # The established tunnel must be closed by the takeover.
            with pytest.raises(websockets.exceptions.ConnectionClosed) as exc:
                await asyncio.wait_for(ws.recv(), timeout=15)
            assert exc.value.rcvd.code == 4403

        # A reconnect while reclaim is blocked is refused during the
        # handshake. Starlette cannot send a 4403 close before accepting,
        # so the fail-closed refusal surfaces as HTTP 403.
        with pytest.raises(websockets.exceptions.InvalidStatus) as refused:
            await websockets.connect(
                _ws_url(harness, profile_id),
                additional_headers={"Authorization": f"Bearer {token}"},
                ssl=ssl_ctx,
                max_size=None,
            )
        assert refused.value.response.status_code == 403

        # Explicit human restore re-enables the agent path.
        headers = await harness.login_api()
        async with httpx.AsyncClient(
            base_url=harness.origin,
            headers=headers,
            verify=False,
            trust_env=False,
        ) as client:
            restore = await client.post(
                f"/api/v1/profiles/{profile_id}/control/restore",
                headers=headers,
            )
            assert restore.status_code == 200
            assert restore.json()["owner"] == "agent"
        async with websockets.connect(
            _ws_url(harness, profile_id),
            additional_headers={"Authorization": f"Bearer {token}"},
            ssl=ssl_ctx,
            max_size=None,
        ) as ws3:
            await ws3.send(
                json.dumps({"id": 1, "method": "Target.getTargets"})
            )
            first = json.loads(
                await asyncio.wait_for(ws3.recv(), timeout=15)
            )
            assert first.get("id") == 1
    finally:
        await harness.cleanup()


@pytest.mark.asyncio
async def test_second_agent_claim_conflicts_on_real_topology(
    tmp_path: Path,
) -> None:
    harness = await _setup(tmp_path)
    try:
        profile = await harness.create_and_start_profile("contention_profile")
        profile_id = profile["profile_id"]
        token1 = await _automation_token(harness, profile_id, "bot-1")
        token2 = await _automation_token(harness, profile_id, "bot-2")
        headers = await harness.login_api()
        async with httpx.AsyncClient(
            base_url=harness.origin,
            headers=headers,
            verify=False,
            trust_env=False,
        ) as client:
            first = await client.post(
                f"/api/v1/profiles/{profile_id}/control/claim",
                json={"agent_session_id": "exec-1"},
                headers={"Authorization": f"Bearer {token1}"},
            )
            assert first.status_code == 200
            second = await client.post(
                f"/api/v1/profiles/{profile_id}/control/claim",
                json={"agent_session_id": "exec-2"},
                headers={"Authorization": f"Bearer {token2}"},
            )
            assert second.status_code == 409
    finally:
        await harness.cleanup()


@pytest.mark.asyncio
async def test_takeover_does_not_stop_browser_page(tmp_path: Path) -> None:
    """AC-004 API-visible part: takeover closes tunnels, not the browser.

    Viewer media/input continuity over real WebRTC/X11 is t032's.
    """
    harness = await _setup(tmp_path)
    try:
        profile = await harness.create_and_start_profile("takeover_profile")
        profile_id = profile["profile_id"]
        token = await _automation_token(harness, profile_id, "takeover-bot")
        headers = await harness.login_api()
        async with httpx.AsyncClient(
            base_url=harness.origin,
            headers=headers,
            verify=False,
            trust_env=False,
        ) as client:
            before = await client.get(
                f"/api/v1/profiles/{profile_id}/runtime"
            )
            assert before.status_code == 200
            handoff = await client.post(
                f"/api/v1/profiles/{profile_id}/control/handoff",
                json={"reason": "cli_handoff"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert handoff.status_code == 200
            after = await client.get(
                f"/api/v1/profiles/{profile_id}/runtime"
            )
            assert after.status_code == 200
            body = after.json()
            assert body["control"]["owner"] == "user"
            # The runtime itself keeps running: takeover is not a stop.
            assert body.get("runtime_instance_id") == (
                profile["runtime_instance_id"]
            )
    finally:
        await harness.cleanup()
