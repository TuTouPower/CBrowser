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
        ws=None,  # type: ignore[arg-type]
        last_heartbeat=t0 + 55.0,
    )
    old = registry.register(agent3)
    assert old is agent2
    assert registry.get("p1") is agent3


def test_old_session_heartbeat_cannot_extend_new_session_liveness() -> None:
    from cbrowser.gateway.registry import AgentRegistry, RegisteredAgent

    registry = AgentRegistry()
    agent = RegisteredAgent(
        profile_id="p1",
        instance_id="i1",
        agent_session_id="new-session",
        selkies_version="2.1.0",
        runtime_state="ready",
        udp_port=30001,
        config_version=1,
        ws=object(),
        last_heartbeat=100.0,
    )
    registry.register(agent)

    assert registry.update_heartbeat("p1", "i1", "old-session", now=200.0) is False
    assert registry.get("p1").last_heartbeat == 100.0
    assert registry.update_heartbeat("p1", "i1", "new-session", now=200.0) is True
    assert registry.get("p1").last_heartbeat == 200.0


def test_registration_throttle_is_bounded_per_source() -> None:
    # t022/A39 contract replacement: the old single "attempts" budget (where
    # successes consumed the same quota as failures) is superseded by two
    # budgets — bounded in-flight reservations released on every exit path,
    # and a windowed failure record that successes never consume or clear.
    from cbrowser.gateway.registry import RegistrationThrottle

    throttle = RegistrationThrottle(
        max_inflight=1, max_failures=2, window_seconds=60.0
    )
    # In-flight bound: a second concurrent reservation is refused until the
    # first is released.
    assert throttle.reserve("10.0.0.1", now=0.0)
    assert not throttle.reserve("10.0.0.1", now=0.5)
    throttle.release("10.0.0.1", success=True, now=1.0)
    # Successes never consume the failure budget, however often they repeat.
    for index in range(5):
        assert throttle.reserve("10.0.0.1", now=2.0 + index)
        throttle.release("10.0.0.1", success=True, now=2.0 + index)
    # Failures accumulate across successes: a success does not clear them.
    assert throttle.reserve("10.0.0.1", now=10.0)
    throttle.release("10.0.0.1", success=False, now=10.0)
    assert throttle.reserve("10.0.0.1", now=11.0)
    throttle.release("10.0.0.1", success=True, now=11.0)
    assert throttle.reserve("10.0.0.1", now=12.0)
    throttle.release("10.0.0.1", success=False, now=12.0)
    assert not throttle.reserve("10.0.0.1", now=13.0)
    # Other sources are unaffected, and the window eventually forgets.
    assert throttle.reserve("10.0.0.2", now=13.0)
    throttle.release("10.0.0.2", success=True, now=13.0)
    assert throttle.reserve("10.0.0.1", now=90.0)
    throttle.release("10.0.0.1", success=True, now=90.0)


def test_heartbeat_syncs_runtime_state() -> None:
    """A16: a heartbeat updates the registry's runtime_state for the
    registered session only."""
    from cbrowser.gateway.registry import AgentRegistry, RegisteredAgent

    registry = AgentRegistry(clock=lambda: 100.0)
    registry.register(
        RegisteredAgent(
            profile_id="p1",
            instance_id="i1",
            agent_session_id="s1",
            selkies_version="2.1.0",
            runtime_state="starting",
            udp_port=30001,
            config_version=1,
            ws=object(),
            last_heartbeat=100.0,
        )
    )
    assert (
        registry.update_heartbeat("p1", "i1", "s1", runtime_state="ready")
        is True
    )
    assert registry.get("p1").runtime_state == "ready"
    # A stale session cannot rewrite the live record.
    assert (
        registry.update_heartbeat("p1", "i1", "other", runtime_state="starting")
        is False
    )
    assert registry.get("p1").runtime_state == "ready"


def test_liveness_uses_injected_monotonic_clock() -> None:
    from cbrowser.gateway.registry import AgentRegistry, RegisteredAgent

    clock = [1000.0]

    def now() -> float:
        return clock[0]

    registry = AgentRegistry(clock=now)
    agent = RegisteredAgent(
        profile_id="p1",
        instance_id="i1",
        agent_session_id="s1",
        selkies_version="2.1.0",
        runtime_state="ready",
        udp_port=30001,
        config_version=1,
        ws=object(),
        last_heartbeat=registry.now(),
    )
    registry.register(agent)

    # Wall-clock jumps do not affect liveness, only the injected clock does.
    clock[0] = 1029.0
    assert registry.check_heartbeat_timeouts(timeout_sec=30.0) == []
    clock[0] = 1031.0
    assert len(registry.check_heartbeat_timeouts(timeout_sec=30.0)) == 1


def test_throttle_buckets_by_source_not_claimed_identity() -> None:
    """A39/F001: rotating claimed profile/instance strings cannot mint new
    buckets — the budget key is the transport source alone, and the number
    of tracked sources is bounded with eviction."""
    from cbrowser.gateway.registry import RegistrationThrottle

    throttle = RegistrationThrottle(
        max_inflight=2, max_failures=2, window_seconds=60.0, max_sources=3
    )
    # Two failures from one source exhaust it regardless of which identity
    # the handshake claimed (the throttle API never sees identity at all).
    for index in range(2):
        assert throttle.reserve("10.0.0.9", now=float(index))
        throttle.release("10.0.0.9", success=False, now=float(index))
    assert not throttle.reserve("10.0.0.9", now=3.0)
    # Distinct failing sources beyond the cap evict older entries, so the
    # tracked-source state stays bounded no matter how many sources appear.
    for octet in range(5):
        peer = f"10.0.1.{octet}"
        assert throttle.reserve(peer, now=10.0 + octet)
        throttle.release(peer, success=False, now=10.0 + octet)
    assert len(throttle._failures) <= 3


def test_throttle_eviction_never_drops_live_reservations_or_history() -> None:
    """A39/f002: under a >max_sources flood, eviction must not drop a
    source's in-flight count (max_inflight keeps holding), and a source
    that keeps failing during the flood keeps its failure history —
    eviction takes history-free and least-recently-active sources first."""
    from cbrowser.gateway.registry import RegistrationThrottle

    throttle = RegistrationThrottle(
        max_inflight=2, max_failures=3, window_seconds=60.0, max_sources=4
    )

    def fail(peer: str, at: float) -> None:
        assert throttle.reserve(peer, now=at)
        throttle.release(peer, success=False, now=at)

    # A live source holds both in-flight slots for the whole flood.
    assert throttle.reserve("holder", now=5.0)
    assert throttle.reserve("holder", now=5.0)
    # Flood sources fail first; the victim keeps failing afterwards and
    # stays the most recently active history-bearing source throughout.
    for octet in range(1, 5):
        fail(f"10.9.0.{octet}", 9.0 + octet)
    fail("victim", 14.0)
    fail("victim", 16.0)
    fail("victim", 18.0)
    fail("10.9.0.5", 19.0)
    fail("10.9.0.6", 20.0)
    # The holder's in-flight count survived every eviction pass.
    assert throttle._inflight.get("holder") == 2
    assert not throttle.reserve("holder", now=30.0)
    # The victim's three in-window failures survived the flood.
    assert not throttle.reserve("victim", now=31.0)
