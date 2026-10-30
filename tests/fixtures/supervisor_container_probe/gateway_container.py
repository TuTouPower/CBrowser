"""Run the authenticated test Gateway on its private Docker network."""

import asyncio
import os
import signal
from pathlib import Path

from aiohttp import web
from cbrowser.supervisor.agent_credentials import AgentCredentials
from gateway_fixture import SupervisorGatewayFixture


async def main():
    gateway = SupervisorGatewayFixture(
        18097,
        AgentCredentials(Path(os.environ["PROBE_AGENT_KEY_FILE"])),
        Path(os.environ["PROBE_GATEWAY_KEY_FILE"]),
    )
    gateway._app.router.add_get(
        "/healthz", lambda request: web.json_response({"status": "ok"})
    )
    gateway._runner = web.AppRunner(gateway._app)
    await gateway._runner.setup()
    gateway._site = web.TCPSite(gateway._runner, "0.0.0.0", 18097)
    await gateway._site.start()
    stopped = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stopped.set)
    try:
        await stopped.wait()
    finally:
        await gateway.stop()


if __name__ == "__main__":
    asyncio.run(main())
