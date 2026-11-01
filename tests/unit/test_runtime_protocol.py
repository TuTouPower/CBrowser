"""Unit tests for Browser Runtime Agent schemas and protocol models."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cbrowser.runtime_agent.protocol import (
    ConfigVersionResponse,
    ControlRequest,
    ControlResponse,
    DownloadEventRecord,
    HealthResponse,
    RuntimeEventRecord,
    RuntimeStateRecord,
)
from pydantic import ValidationError


def test_schema_json_file_validity() -> None:
    """Verify that schemas/runtime/agent_protocol.json is valid JSON."""
    schema_path = Path("schemas/runtime/agent_protocol.json")
    assert schema_path.exists(), "Schema file does not exist"
    with open(schema_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["title"] == "BrowserAgentProtocol"
    defs = data.get("$defs", {})
    assert "HealthResponse" in defs
    assert "ConfigVersionResponse" in defs
    assert "ControlRequest" in defs
    assert "ControlResponse" in defs
    assert "RuntimeEventRecord" in defs
    assert "DownloadEventRecord" in defs


def test_health_response_valid() -> None:
    resp = HealthResponse(
        status="ok",
        ready=True,
        display_ready=True,
        browser_ready=True,
        audio_ready=True,
        cdp_ready=True,
        profile_id="prof_01",
        runtime_instance_id="inst_01",
        config_version=2,
        details={"fps": 60},
    )
    assert resp.status == "ok"
    assert resp.ready is True
    assert resp.config_version == 2
    assert resp.details["fps"] == 60


def test_health_response_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        HealthResponse(  # type: ignore[call-arg]
            status="ok",
            ready=True,
            display_ready=True,
            browser_ready=True,
            audio_ready=True,
            cdp_ready=True,
            profile_id="prof_01",
            runtime_instance_id="inst_01",
            config_version=1,
            unauthorized_extra_field="malicious",
        )


def test_config_version_response() -> None:
    resp = ConfigVersionResponse(
        profile_id="prof_abc",
        runtime_instance_id="inst_xyz",
        config_version=3,
    )
    assert resp.profile_id == "prof_abc"
    assert resp.config_version == 3

    with pytest.raises(ValidationError):
        ConfigVersionResponse(  # type: ignore[call-arg]
            profile_id="prof_abc",
            runtime_instance_id="inst_xyz",
            config_version=0,  # ge=1
        )


def test_control_request_allowlist() -> None:
    req_close = ControlRequest(action="close")
    assert req_close.action == "close"

    req_rearm = ControlRequest(action="rearm_downloads")
    assert req_rearm.action == "rearm_downloads"

    # Any non-whitelisted action must be rejected by Pydantic validation
    with pytest.raises(ValidationError):
        ControlRequest(action="execute_shell_command")  # type: ignore[arg-type]


def test_control_response() -> None:
    resp = ControlResponse(status="ok", action="close", message="closing")
    assert resp.status == "ok"
    assert resp.message == "closing"


def test_runtime_event_record_validation() -> None:
    evt = RuntimeEventRecord(
        event_id="evt_exit_12345",
        profile_id="prof_01",
        runtime_instance_id="inst_01",
        event_type="exit",
        exit_code=0,
        exit_reason="normal",
        config_version=1,
        payload={"code": 0},
    )
    assert evt.event_id == "evt_exit_12345"
    assert evt.exit_code == 0
    assert evt.exit_reason == "normal"

    # Invalid event_id characters (spaces, special symbols)
    with pytest.raises(ValidationError):
        RuntimeEventRecord(
            event_id="bad event id with spaces!",
            profile_id="prof_01",
            runtime_instance_id="inst_01",
            event_type="exit",
            config_version=1,
        )

    # Invalid event_type (download has its own record)
    with pytest.raises(ValidationError):
        RuntimeEventRecord(
            event_id="evt_01",
            profile_id="prof_01",
            runtime_instance_id="inst_01",
            event_type="download",  # type: ignore[arg-type]
            config_version=1,
        )


def test_download_event_record_validation() -> None:
    dl_evt = DownloadEventRecord(
        event_id="dl_comp_001",
        profile_id="prof_01",
        runtime_instance_id="inst_01",
        guid="guid-1111-2222",
        url="https://example.com/file.zip",
        suggested_filename="file.zip",
        download_path="/exchange/downloads/guid-1111-2222",
        state="completed",
        received_bytes=1024,
        total_bytes=1024,
    )
    assert dl_evt.guid == "guid-1111-2222"
    assert dl_evt.state == "completed"
    assert dl_evt.received_bytes == 1024

    with pytest.raises(ValidationError):
        DownloadEventRecord(
            event_id="dl_002",
            profile_id="prof_01",
            runtime_instance_id="inst_01",
            guid="guid-3333",
            state="unknown_state",  # type: ignore[arg-type]
        )


def test_runtime_state_record() -> None:
    state = RuntimeStateRecord(
        profile_id="prof_01",
        runtime_instance_id="inst_01",
        config_version=1,
        state="stopped",
        exit_code=0,
        exit_reason="normal",
        browser_pid=1234,
    )
    assert state.state == "stopped"
    assert state.exit_code == 0
    assert state.browser_pid == 1234
