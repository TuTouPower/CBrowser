"""Export StreamAgent wire envelopes from their Pydantic definitions."""

import json
from pathlib import Path

from cbrowser.stream_agent.protocol import (
    GatewayControlEnvelope,
    GatewayRegisterResponse,
    GatewayTunnelEnvelope,
    ProtocolEnvelope,
)
from pydantic import TypeAdapter


def stream_protocol_schema() -> dict:
    schema = TypeAdapter(
        ProtocolEnvelope
        | GatewayRegisterResponse
        | GatewayTunnelEnvelope
        | GatewayControlEnvelope
    ).json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "StreamAgentGatewayWireProtocol"
    return schema


if __name__ == "__main__":
    destination = (
        Path(__file__).resolve().parents[1] / "schemas/stream/agent_protocol.json"
    )
    destination.write_text(json.dumps(stream_protocol_schema(), indent=2) + "\n")
