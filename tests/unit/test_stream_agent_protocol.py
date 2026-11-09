"""Registration fields, heartbeat payload and per-action wire contract."""

import pytest
from cbrowser.stream_agent.protocol import (
    AgentAction,
    AgentHeartbeatEnvelope,
    AgentHeartbeatPayload,
    AgentRegisterEnvelope,
    AgentRegisterPayload,
    GatewayControlEnvelope,
    GatewayTunnelEnvelope,
    validate_agent_envelope,
)
from pydantic import TypeAdapter, ValidationError

REGISTER = {
    "hostname": "stream-a",
    "profile_id": "profile_a",
    "runtime_instance_id": "inst_a",
    "udp_port": 30000,
    "selkies_version": "2.1.0",
    "runtime_state": "ready",
    "config_version": 3,
}

HEARTBEAT = {
    "runtime_state": "ready",
    "viewer_count": 2,
    "unpaused_video_consumers": 1,
    "capture_running": True,
}


def test_registration_requires_plan_fields():
    payload = AgentRegisterPayload.model_validate(REGISTER)
    assert (payload.selkies_version, payload.runtime_state, payload.config_version) == (
        "2.1.0",
        "ready",
        3,
    )
    for field in ("selkies_version", "runtime_state", "config_version"):
        broken = {key: value for key, value in REGISTER.items() if key != field}
        with pytest.raises(ValidationError):
            AgentRegisterPayload.model_validate(broken)


@pytest.mark.parametrize(
    "field,value",
    [("config_version", 0), ("runtime_state", "running"), ("selkies_version", "")],
)
def test_registration_rejects_invalid_values(field, value):
    with pytest.raises(ValidationError):
        AgentRegisterPayload.model_validate({**REGISTER, field: value})


def test_registration_carries_no_turn_or_duplicate_fps_fields():
    for field in ("turn_host", "turn_port", "max_fps", "min_fps"):
        assert field not in AgentRegisterPayload.model_fields
    with pytest.raises(ValidationError):
        AgentRegisterPayload.model_validate({**REGISTER, "max_fps": 30})


def test_heartbeat_reports_selkies_video_state_strictly():
    beat = AgentHeartbeatPayload.model_validate(HEARTBEAT)
    assert (beat.viewer_count, beat.unpaused_video_consumers) == (2, 1)
    assert beat.capture_running is True
    valid = beat.model_dump()
    for broken in (
        {"runtime_state": "ready", "viewer_count": 2},
        {**valid, "viewer_count": -1},
        {**valid, "unpaused_video_consumers": -1},
        {**valid, "capture_running": "true"},
        {**valid, "token": "x"},
    ):
        with pytest.raises(ValidationError):
            AgentHeartbeatPayload.model_validate(broken)


def test_actions_are_limited_to_the_implemented_contract():
    assert {action.value for action in AgentAction} == {
        "register",
        "supervisor_quota",
        "heartbeat",
        # t031: human-input takeover report (Stream -> Gateway -> API).
        "human_input_takeover",
    }
    for removed in ("visibility_update", "rtc_config", "ice_restart"):
        assert removed not in {action.value for action in AgentAction}


def test_gateway_control_is_quota_only_and_validated():
    env = GatewayControlEnvelope(
        version="v2",
        action=AgentAction.SUPERVISOR_QUOTA,
        profile_id="profile_a",
        runtime_instance_id="inst_a",
        agent_session_id="session_a",
        payload={"max_fps_cap": 15},
    )
    assert env.payload.max_fps_cap == 15.0
    with pytest.raises(ValidationError):
        GatewayControlEnvelope.model_validate(
            {
                "version": "v2",
                "action": "visibility_update",
                "profile_id": "profile_a",
                "runtime_instance_id": "inst_a",
                "agent_session_id": "session_a",
                "payload": {"viewer_id": "viewer_a", "visible": True},
            }
        )
    with pytest.raises(ValidationError):
        GatewayControlEnvelope.model_validate(
            {
                "version": "v2",
                "action": "supervisor_quota",
                "profile_id": "profile_a",
                "runtime_instance_id": "inst_a",
                "agent_session_id": "session_a",
                "payload": {"max_fps_cap": 99},
            }
        )


def test_agent_envelopes_discriminate_payload_by_action():
    register = validate_agent_envelope(
        {
            "version": "v2",
            "action": "register",
            "profile_id": "profile_a",
            "runtime_instance_id": "inst_a",
            "payload": REGISTER,
        }
    )
    assert isinstance(register, AgentRegisterEnvelope)
    heartbeat = validate_agent_envelope(
        {
            "version": "v2",
            "action": "heartbeat",
            "profile_id": "profile_a",
            "runtime_instance_id": "inst_a",
            "agent_session_id": "session_a",
            "payload": HEARTBEAT,
        }
    )
    assert isinstance(heartbeat, AgentHeartbeatEnvelope)
    with pytest.raises(ValidationError):
        validate_agent_envelope(
            {
                "version": "v2",
                "action": "register",
                "profile_id": "profile_a",
                "runtime_instance_id": "inst_a",
                "payload": HEARTBEAT,
            }
        )


def test_tunnel_envelope_requires_data_for_msg():
    with pytest.raises(ValidationError):
        GatewayTunnelEnvelope(
            version="v2",
            type="msg",
            profile_id="profile_a",
            runtime_instance_id="inst_a",
            agent_session_id="session_a",
            conn_id="conn_a",
        )
    adapter = TypeAdapter(GatewayTunnelEnvelope)
    assert adapter.validate_python(
        {
            "version": "v2",
            "type": "open",
            "profile_id": "profile_a",
            "runtime_instance_id": "inst_a",
            "agent_session_id": "session_a",
            "conn_id": "conn_a",
        }
    ).type == "open"
