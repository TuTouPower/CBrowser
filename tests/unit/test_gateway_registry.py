"""Unit tests for Gateway AgentRegistry."""

from cbrowser.gateway.registry import AgentRegistry, RegisteredAgent


def test_agent_registry_lifecycle_and_heartbeats() -> None:
    registry = AgentRegistry()
    t0 = 1000.0

    # 1. Register agent
    agent = RegisteredAgent(
        profile_id="p1",
        instance_id="inst_1",
        agent_session_id="ses_1",
        selkies_version="2.1.0",
        runtime_state="ready",
        udp_port=30005,
        config_version=1,
        turn_host="10.0.0.1",
        turn_port=3478,
        ws=None,  # type: ignore[arg-type]
        last_heartbeat=t0,
    )
    old = registry.register(agent)
    assert old is None
    assert registry.get("p1") is agent

    # 2. Update heartbeat
    registry.update_heartbeat("p1", "inst_1", now=t0 + 10.0)
    assert registry.get("p1").last_heartbeat == t0 + 10.0

    # 3. Heartbeat check: 25s elapsed, not timed out (threshold=30s)
    timed_out = registry.check_heartbeat_timeouts(now=t0 + 35.0, timeout_sec=30.0)
    assert timed_out == []

    # 4. Heartbeat check: at t0 + 41s (31s since last heartbeat), timed out
    timed_out = registry.check_heartbeat_timeouts(now=t0 + 41.0, timeout_sec=30.0)
    assert len(timed_out) == 1
    assert timed_out[0].profile_id == "p1"
    assert registry.get("p1") is None  # Removed on timeout

    # 5. Replacement of agent
    agent2 = RegisteredAgent(
        profile_id="p1",
        instance_id="inst_2",
        agent_session_id="ses_2",
        selkies_version="2.1.0",
        runtime_state="ready",
        udp_port=30005,
        config_version=2,
        turn_host="10.0.0.1",
        turn_port=3478,
        ws=None,  # type: ignore[arg-type]
        last_heartbeat=t0 + 50.0,
    )
    old = registry.register(agent2)
    assert old is None
    assert registry.get("p1") is agent2

    # Re-registering replaces old
    agent3 = RegisteredAgent(
        profile_id="p1",
        instance_id="inst_2",
        agent_session_id="ses_3",
        selkies_version="2.1.0",
        runtime_state="ready",
        udp_port=30005,
        config_version=2,
        turn_host="10.0.0.1",
        turn_port=3478,
        ws=None,  # type: ignore[arg-type]
        last_heartbeat=t0 + 55.0,
    )
    old = registry.register(agent3)
    assert old is agent2
    assert registry.get("p1") is agent3
