"""Stream Gateway service for CBrowser v2."""

from .config import GatewayConfig
from .server import create_gateway_app

__all__ = ["GatewayConfig", "create_gateway_app"]
