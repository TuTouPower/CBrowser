"""Export Supervisor control RPC models as a reproducible JSON schema."""

import json
from pathlib import Path

from cbrowser.supervisor.protocol import (
    ProfileRuntimeStatus,
    ResetBlockedRequest,
    ResetBlockedResponse,
    StartProfileRequest,
    StartProfileResponse,
    StopProfileRequest,
    StopProfileResponse,
)
from pydantic import TypeAdapter


def supervisor_protocol_schema() -> dict:
    schema = TypeAdapter(
        StartProfileRequest
        | StartProfileResponse
        | StopProfileRequest
        | StopProfileResponse
        | ResetBlockedRequest
        | ResetBlockedResponse
        | ProfileRuntimeStatus
    ).json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "SupervisorControlProtocol"
    return schema


if __name__ == "__main__":
    destination = (
        Path(__file__).resolve().parents[1] / "schemas/runtime/supervisor_protocol.json"
    )
    destination.write_text(json.dumps(supervisor_protocol_schema(), indent=2) + "\n")
