"""Export StreamAgent wire envelopes from their Pydantic definitions.

All protocol schema documents share one convention (A41): the canonical
model definitions live under ``$defs`` (kept exactly as the union
generates them), and consumers enter through the ``messages`` index,
which maps each message name to a stable ``$id`` plus a ``$ref`` of
its definition instead of relying on a fragile positional
top-level ``anyOf``. The document ``version`` matches the wire envelope
version literal (``v2``) and is maintained per protocol.
"""

import json
from pathlib import Path

from cbrowser.stream_agent.protocol import (
    AgentHeartbeatEnvelope,
    AgentRegisterEnvelope,
    GatewayControlEnvelope,
    GatewayRegisterResponse,
    GatewayTunnelEnvelope,
)
from pydantic import TypeAdapter

_MESSAGES = (
    AgentRegisterEnvelope,
    AgentHeartbeatEnvelope,
    GatewayRegisterResponse,
    GatewayTunnelEnvelope,
    GatewayControlEnvelope,
)


def _entry_index_document(union_schema: dict, message_names: list[str]) -> dict:
    defs = union_schema.get("$defs", {})
    missing = [name for name in message_names if name not in defs]
    if missing:
        raise ValueError(f"Union schema is missing message definitions: {missing}")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "StreamAgentGatewayWireProtocol",
        "version": "v2",
        "messages": {
            name: {"$id": f"#/$defs/{name}", "$ref": f"#/$defs/{name}"}
            for name in message_names
        },
        "$defs": defs,
    }


def stream_protocol_schema() -> dict:
    schema = TypeAdapter(
        AgentRegisterEnvelope
        | AgentHeartbeatEnvelope
        | GatewayRegisterResponse
        | GatewayTunnelEnvelope
        | GatewayControlEnvelope
    ).json_schema()
    return _entry_index_document(schema, [model.__name__ for model in _MESSAGES])


if __name__ == "__main__":
    destination = (
        Path(__file__).resolve().parents[1] / "schemas/stream/agent_protocol.json"
    )
    destination.write_text(json.dumps(stream_protocol_schema(), indent=2) + "\n")
