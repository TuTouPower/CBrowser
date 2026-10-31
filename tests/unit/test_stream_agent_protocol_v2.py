"""Plan 7.2 registration fields, health payload and RTC config control messages."""

import pytest
from cbrowser.stream_agent.protocol import (
    AgentAction,
    AgentHeartbeatPayload,
    AgentRegisterPayload,
    GatewayControlEnvelope,
    RtcConfigPayload,
)
from pydantic import ValidationError

REGISTER = {
    "hostname": "stream-a",
    "profile_id": "profile_a",
    "runtime_instance_id": "inst_a",
    "udp_port": 30000,
    "selkies_version": "2.1.0",
    "runtime_state": "ready",
    "config_version": 3,
    "turn_host": "10.0.0.1",
    "turn_port": 3478,
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


def test_registration_requires_turn_host_and_port():
    valid = {
        **REGISTER,
        "turn_host": "10.0.0.1",
        "turn_port": 3478,
    }
    payload = AgentRegisterPayload.model_validate(valid)
    assert payload.turn_host == "10.0.0.1"
    assert payload.turn_port == 3478

    # IPv6 test
    valid_ipv6 = {
        **REGISTER,
        "turn_host": "2001:db8::1",
        "turn_port": 3478,
    }
    payload_v6 = AgentRegisterPayload.model_validate(valid_ipv6)
    assert payload_v6.turn_host == "2001:db8::1"

    # Missing turn_host
    no_host = {k: v for k, v in REGISTER.items() if k != "turn_host"}
    with pytest.raises(ValidationError):
        AgentRegisterPayload.model_validate(no_host)

    # Missing turn_port
    no_port = {k: v for k, v in REGISTER.items() if k != "turn_port"}
    with pytest.raises(ValidationError):
        AgentRegisterPayload.model_validate(no_port)

    # Invalid turn_host (hostname or bad IP)
    for bad_host in ("coturn", "999.999.999.999", "not:an:ip:address:x"):
        with pytest.raises(ValidationError):
            AgentRegisterPayload.model_validate(
                {**REGISTER, "turn_host": bad_host, "turn_port": 3478}
            )

    # Invalid turn_port (< 1 or > 65535)
    for bad_port in (0, -1, 65536, 70000):
        with pytest.raises(ValidationError):
            AgentRegisterPayload.model_validate(
                {**REGISTER, "turn_host": "10.0.0.1", "turn_port": bad_port}
            )


def test_heartbeat_reports_selkies_video_state_strictly():
    beat = AgentHeartbeatPayload.model_validate(
        {
            "runtime_state": "ready",
            "viewer_count": 2,
            "unpaused_video_consumers": 1,
            "capture_running": True,
        }
    )
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


def test_gateway_cannot_send_visibility_updates():
    assert "visibility_update" not in {action.value for action in AgentAction}
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


def test_rtc_config_payload_validates_ice_servers_and_hides_credentials():
    assert AgentAction.RTC_CONFIG.value == "rtc_config"
    payload = RtcConfigPayload.model_validate(
        {
            "generation": 2,
            "ice_servers": [
                {
                    "urls": ["turn:10.0.0.5:3478?transport=udp"],
                    "username": "1700000000:stream-profile_a",
                    "credential": "c2VjcmV0",
                }
            ],
        }
    )
    assert payload.ice_servers[0].credential.get_secret_value() == "c2VjcmV0"
    assert "c2VjcmV0" not in repr(payload)
    wire = payload.wire_ice_servers()
    assert wire == [
        {
            "urls": ["turn:10.0.0.5:3478?transport=udp"],
            "username": "1700000000:stream-profile_a",
            "credential": "c2VjcmV0",
        }
    ]
    for broken in (
        {"generation": 1, "ice_servers": []},
        {"generation": 1, "ice_servers": [{"urls": ["http://evil"]}]},
        {"generation": 0, "ice_servers": [{"urls": ["stun:10.0.0.5:3478"]}]},
    ):
        with pytest.raises(ValidationError):
            RtcConfigPayload.model_validate(broken)


def test_rtc_config_payload_relay_only_strict_boolean():
    base = {
        "generation": 1,
        "ice_servers": [{"urls": ["turn:10.0.0.5:3478?transport=udp"]}],
    }
    # Defaults to False
    p_default = RtcConfigPayload.model_validate(base)
    assert p_default.relay_only is False

    # Accepts True
    p_relay = RtcConfigPayload.model_validate({**base, "relay_only": True})
    assert p_relay.relay_only is True

    # Strict boolean: non-bool types are rejected
    for invalid in ("true", "false", 1, 0, None, []):
        with pytest.raises(ValidationError):
            RtcConfigPayload.model_validate({**base, "relay_only": invalid})
