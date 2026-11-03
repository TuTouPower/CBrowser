"""A failed immutable-version RPC must never fall back to guessed config."""

import httpx
import pytest
from aiohttp import web
from cbrowser.supervisor.recovery_coordinator import RecoveryCoordinator


class _CoreStub:
    """The exact SupervisorCore surface RecoveryCoordinator consumes here:
    an ``api`` client plus an ``_auth_headers()`` call (t024 AC-014/A43 --
    an explicit stub, not the builtin ``dict`` type standing in as the
    headers callable)."""

    def __init__(self, api: httpx.AsyncClient) -> None:
        self.api = api

    def _auth_headers(self) -> dict[str, str]:
        return {}


@pytest.mark.asyncio
async def test_failed_snapshot_rpc_aborts_instead_of_constructing_defaults():
    app = web.Application()
    app.router.add_get(
        "/api/v1/internal/supervisor/profiles/profile/versions/1",
        lambda request: web.json_response({"detail": "unavailable"}, status=503),
    )
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}", trust_env=False
        ) as api:
            coordinator = RecoveryCoordinator(_CoreStub(api))
            with pytest.raises(httpx.HTTPStatusError):
                await coordinator._load_profile_config(
                    "profile", 1, {"name": "must_not_launch"}
                )
    finally:
        await runner.cleanup()
