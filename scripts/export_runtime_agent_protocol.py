"""Export Browser Runtime Agent UDS contract as a reproducible JSON schema."""

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
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "BrowserAgentProtocol"
    schema["description"] = (
        "Cross-service Unix Domain Socket contract for CBrowser Runtime Agent"
    )
    schema["version"] = "2.0.0"
    return schema


if __name__ == "__main__":
    destination = (
        Path(__file__).resolve().parents[1] / "schemas/runtime/agent_protocol.json"
    )
    destination.write_text(json.dumps(agent_protocol_schema(), indent=2) + "\n")
