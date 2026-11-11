"""Stream Gateway service for CBrowser."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import GatewayConfig
    from .server import create_gateway_app

__all__ = ["GatewayConfig", "create_gateway_app"]


def __getattr__(name: str):
    if name == "GatewayConfig":
        from .config import GatewayConfig

        return GatewayConfig
    if name == "create_gateway_app":
        from .server import create_gateway_app

        return create_gateway_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
