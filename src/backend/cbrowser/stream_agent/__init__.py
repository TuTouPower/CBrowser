"""
Module package exports for StreamAgent.
Defers sub-module imports to avoid importing Selkies/GStreamer SDK
at package initialization.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import StreamAgent, setup_service_logging
    from .boundary import SecurityError, verify_stream_runtime_boundaries
    from .config import StreamAgentConfig
    from .policy import (
        LiveCapturePolicyAgent,
        sanitize_settings_message,
        should_block_client_verb,
    )
    from .protocol import AgentAction, ProtocolEnvelope

__all__ = [
    "AgentAction",
    "LiveCapturePolicyAgent",
    "ProtocolEnvelope",
    "SecurityError",
    "StreamAgent",
    "StreamAgentConfig",
    "sanitize_settings_message",
    "setup_service_logging",
    "should_block_client_verb",
    "verify_stream_runtime_boundaries",
]


def __getattr__(name: str):
    if name == "StreamAgent":
        from .agent import StreamAgent

        return StreamAgent
    if name == "setup_service_logging":
        from .agent import setup_service_logging

        return setup_service_logging
    if name == "StreamAgentConfig":
        from .config import StreamAgentConfig

        return StreamAgentConfig
    if name == "LiveCapturePolicyAgent":
        from .policy import LiveCapturePolicyAgent

        return LiveCapturePolicyAgent
    if name == "sanitize_settings_message":
        from .policy import sanitize_settings_message

        return sanitize_settings_message
    if name == "should_block_client_verb":
        from .policy import should_block_client_verb

        return should_block_client_verb
    if name == "SecurityError":
        from .boundary import SecurityError

        return SecurityError
    if name == "verify_stream_runtime_boundaries":
        from .boundary import verify_stream_runtime_boundaries

        return verify_stream_runtime_boundaries
    if name in (
        "AgentAction",
        "ProtocolEnvelope",
        "GatewayTunnelEnvelope",
        "GatewayControlEnvelope",
        "GatewayRegisterResponse",
        "AgentRegisterPayload",
        "SupervisorQuotaPayload",
    ):
        from . import protocol

        return getattr(protocol, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
