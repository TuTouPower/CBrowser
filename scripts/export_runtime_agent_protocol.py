"""Export Browser Runtime Agent UDS contract as a reproducible JSON schema.

All protocol schema documents share one convention (A41): the canonical
model definitions live under ``$defs`` (kept exactly as the union
generates them), and consumers enter through the ``messages`` index,
which maps each message name to a stable ``$id`` plus a ``$ref`` of
its definition instead of relying on a fragile positional
top-level ``anyOf``. The document ``version`` is maintained per protocol
and does not claim to be a wire-negotiated version.
"""

import json
from pathlib import Path

from cbrowser.runtime_agent.protocol import (
    ConfigVersionResponse,
    ControlRequest,
    ControlResponse,
    DownloadEventRecord,
    HealthResponse,
    RuntimeEventRecord,
    RuntimeStateRecord,
)
from pydantic import TypeAdapter

_MESSAGES = (
    HealthResponse,
    ConfigVersionResponse,
    ControlRequest,
    ControlResponse,
    RuntimeEventRecord,
    DownloadEventRecord,
    RuntimeStateRecord,
)


def _entry_index_document(union_schema: dict, message_names: list[str]) -> dict:
    defs = union_schema.get("$defs", {})
    missing = [name for name in message_names if name not in defs]
    if missing:
        raise ValueError(f"Union schema is missing message definitions: {missing}")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "BrowserAgentProtocol",
        "description": (
            "Cross-service Unix Domain Socket contract for CBrowser Runtime Agent"
        ),
        "version": "2.0.0",
        "messages": {
            name: {"$id": f"#/$defs/{name}", "$ref": f"#/$defs/{name}"}
            for name in message_names
        },
        "$defs": defs,
    }


def agent_protocol_schema() -> dict:
    schema = TypeAdapter(
        HealthResponse
        | ConfigVersionResponse
        | ControlRequest
        | ControlResponse
        | RuntimeEventRecord
        | DownloadEventRecord
        | RuntimeStateRecord
    ).json_schema()
    return _entry_index_document(schema, [model.__name__ for model in _MESSAGES])


if __name__ == "__main__":
    destination = (
        Path(__file__).resolve().parents[1] / "schemas/runtime/agent_protocol.json"
    )
    destination.write_text(json.dumps(agent_protocol_schema(), indent=2) + "\n")
