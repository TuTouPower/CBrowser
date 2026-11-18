"""Export the minimal batch state protocol as a reproducible JSON schema.

Follows the shared protocol-schema convention (A41): the canonical
model definitions live under ``$defs`` and consumers enter through the
``messages`` index.  The document ``version`` is maintained per
protocol and does not claim to be a wire-negotiated version.
"""

import json
from pathlib import Path

from cbrowser.shared.state_protocol import (
    StateChangeNotice,
    StateSnapshot,
    SupervisorProfileState,
)
from pydantic import TypeAdapter

_MESSAGES = (
    SupervisorProfileState,
    StateSnapshot,
    StateChangeNotice,
)


def _entry_index_document(union_schema: dict, message_names: list[str]) -> dict:
    defs = union_schema.get("$defs", {})
    missing = [name for name in message_names if name not in defs]
    if missing:
        raise ValueError(f"Union schema is missing message definitions: {missing}")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "SupervisorStateProtocol",
        "description": (
            "Minimal batch state contract between the cbrowser API and "
            "the Supervisor (snapshot + change notices)"
        ),
        "version": "1.0.0",
        "messages": {
            name: {"$id": f"#/$defs/{name}", "$ref": f"#/$defs/{name}"}
            for name in message_names
        },
        "$defs": defs,
    }


def state_protocol_schema() -> dict:
    schema = TypeAdapter(
        SupervisorProfileState | StateSnapshot | StateChangeNotice
    ).json_schema()
    return _entry_index_document(schema, [model.__name__ for model in _MESSAGES])


if __name__ == "__main__":
    import sys

    destination = (
        Path(__file__).resolve().parents[1]
        / "schemas/runtime/state_protocol.json"
    )
    rendered = json.dumps(state_protocol_schema(), indent=2) + "\n"
    if "--check" in sys.argv:
        if destination.read_text() != rendered:
            raise SystemExit("state protocol schema is stale; re-export")
    else:
        destination.write_text(rendered)
