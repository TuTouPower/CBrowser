"""Export the Policy Agent UDS contract as a reproducible JSON schema.

Follows the shared protocol-schema convention (A41): the canonical
model definitions live under ``$defs`` and consumers enter through the
``messages`` index.  The document ``version`` is maintained per
protocol and does not claim to be a wire-negotiated version.
"""

import json
from pathlib import Path

from cbrowser.supervisor.policy_agent_protocol import (
    PolicyAgentIdentity,
    PolicyAgentRequest,
    PolicyAgentResponse,
    ResolveRequest,
)
from pydantic import TypeAdapter

_MESSAGES = (
    PolicyAgentIdentity,
    ResolveRequest,
    PolicyAgentRequest,
    PolicyAgentResponse,
)


def _entry_index_document(union_schema: dict, message_names: list[str]) -> dict:
    defs = union_schema.get("$defs", {})
    missing = [name for name in message_names if name not in defs]
    if missing:
        raise ValueError(f"Union schema is missing message definitions: {missing}")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "PolicyAgentProtocol",
        "description": (
            "Cross-service Unix Domain Socket contract for the cbrowser "
            "per-namespace Policy Agent"
        ),
        "version": "1.0.0",
        "messages": {
            name: {"$id": f"#/$defs/{name}", "$ref": f"#/$defs/{name}"}
            for name in message_names
        },
        "$defs": defs,
    }


def policy_agent_protocol_schema() -> dict:
    schema = TypeAdapter(
        PolicyAgentIdentity | ResolveRequest | PolicyAgentRequest | PolicyAgentResponse
    ).json_schema()
    return _entry_index_document(schema, [model.__name__ for model in _MESSAGES])


if __name__ == "__main__":
    import sys

    destination = (
        Path(__file__).resolve().parents[1]
        / "schemas/runtime/policy_agent_protocol.json"
    )
    rendered = json.dumps(policy_agent_protocol_schema(), indent=2) + "\n"
    if "--check" in sys.argv:
        if destination.read_text() != rendered:
            raise SystemExit("policy agent protocol schema is stale; re-export")
    else:
        destination.write_text(rendered)
