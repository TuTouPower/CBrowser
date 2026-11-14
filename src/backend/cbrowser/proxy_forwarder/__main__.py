"""Run the proxy auth-forwarder (t065).

Entry point for the forwarder container:
``python3 -m cbrowser.proxy_forwarder --config /run/cbrowser/proxy_credentials.json``.
The config file is mounted read-only into this container alone. Any config
problem fails closed before the listen socket opens.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from cbrowser.proxy_forwarder.forwarder import (
    PROXY_FORWARDER_PORT,
    load_upstream_config,
    serve,
)

logger = logging.getLogger("cbrowser.proxy_forwarder")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CBrowser proxy auth-forwarder")
    parser.add_argument("--config", required=True, help="upstream credentials JSON")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=PROXY_FORWARDER_PORT)
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        config = load_upstream_config(args.config)
    except Exception as exc:  # noqa: BLE001 - fail closed with a fixed reason
        logger.error("forwarder refuses to start: %s", type(exc).__name__)
        return 1

    async def run() -> None:
        server = await serve(config, args.listen_host, args.listen_port)
        loop = asyncio.get_running_loop()
        stop = loop.create_future()

        def _stop() -> None:
            if not stop.done():
                stop.set_result(None)

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, _stop)
            except NotImplementedError:
                pass
        logger.info(
            "proxy forwarder listening on %s:%d (upstream %s:%d)",
            args.listen_host,
            args.listen_port,
            config.host,
            config.port,
        )
        await stop
        server.close()
        await server.wait_closed()

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
