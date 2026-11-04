"""t031 coordinator close-tunnels flag semantics (code f001).

The control record's pending flag must clear only when the Supervisor
confirms BOTH the tunnel close and the attendant release: a 200 whose
body reports attendant_released False is an unconfirmed cascade, and
the next reconcile round must retry it.
"""

from __future__ import annotations

import httpx
import pytest
from cbrowser.api.runtime_coordinator import RuntimeCoordinator


def _coordinator(handler) -> RuntimeCoordinator:
    transport = httpx.MockTransport(handler)
    return RuntimeCoordinator(
        supervisor_url="http://supervisor:18081",
        supervisor_token="t" * 40,
        profile_service=None,
        transport=transport,
    )


@pytest.mark.asyncio
async def test_close_confirmed_only_with_attendant_release():
    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "profile_id": "p1",
                "generation": 3,
                "closed_tunnel_ids": ["s1"],
                "attendant_released": True,
            },
        )

    assert await _coordinator(ok).close_supervisor_tunnels("p1", 3) is True


@pytest.mark.asyncio
async def test_close_unconfirmed_when_attendant_release_failed():
    def unreleased(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "profile_id": "p1",
                "generation": 3,
                "closed_tunnel_ids": ["s1"],
                "attendant_released": False,
            },
        )

    assert (
        await _coordinator(unreleased).close_supervisor_tunnels("p1", 3)
        is False
    )


@pytest.mark.asyncio
async def test_close_unconfirmed_on_error_status_or_bad_body():
    def error_status(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    def bad_body(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json{")

    assert (
        await _coordinator(error_status).close_supervisor_tunnels("p1", 3)
        is False
    )
    assert (
        await _coordinator(bad_body).close_supervisor_tunnels("p1", 3)
        is False
    )
