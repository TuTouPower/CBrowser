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
import logging
import sys
from pathlib import Path
from typing import get_args

from cbrowser.stream_agent.protocol import GatewayWireMessage
from pydantic import TypeAdapter

logger = logging.getLogger(__name__)


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
    schema = TypeAdapter(GatewayWireMessage).json_schema()
    return _entry_index_document(
        schema, [model.__name__ for model in get_args(GatewayWireMessage)]
    )


def render_stream_protocol() -> str:
    return json.dumps(stream_protocol_schema(), indent=2) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    destination = (
        Path(__file__).resolve().parents[1] / "schemas/stream/agent_protocol.json"
    )
    rendered = render_stream_protocol()
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        if destination.read_text(encoding="utf-8") != rendered:
            logger.error("protocol drift: %s is out of date", destination)
            raise SystemExit(1)
        logger.info("%s is up to date", destination)
    else:
        destination.write_text(rendered, encoding="utf-8")
