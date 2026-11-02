"""Standalone CLI entrypoint for CBrowser Stream Gateway."""

import logging
import sys

from aiohttp import web

from .config import GatewayConfig
from .server import create_gateway_app

logger = logging.getLogger("cbrowser.gateway")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Initializing CBrowser Stream Gateway Service...")

    try:
        config = GatewayConfig.from_env()
    except Exception as e:  # noqa: BLE001 - CLI entrypoint catches config errors to exit with status 1
        logger.error("Configuration error: %s", e)
        sys.exit(1)

    app = create_gateway_app(config)
    logger.info("Starting Gateway listening on %s:%d", config.host, config.port)
    web.run_app(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
