"""t027: the Gateway health route used by the compose healthcheck.

Unauthenticated liveness: GET /gateway/v1/health returns 200 with the
service identity and requires no credentials, mirroring the API
/api/v1/health contract.
"""

from __future__ import annotations

from pathlib import Path

import aiohttp
import pytest

from test_gateway_fixtures import GatewayHarness


@pytest.mark.asyncio
async def test_gateway_health_route(tmp_path: Path) -> None:
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{harness.base_url}/gateway/v1/health") as resp:
                assert resp.status == 200
                payload = await resp.json()
        assert payload == {"status": "ok", "role": "gateway"}
    finally:
        await harness.stop()
