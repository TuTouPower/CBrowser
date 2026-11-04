"""t031 takeover chain assembly: real Stream hook + constructor wiring.

Review t031_test_f001: the classifier table and the flush envelope tests
were each true, but no test ever drove the production assembly between
them -- the Stream input hook's classify -> foreground -> report chain,
nor the StreamAgent constructor wiring that connects the policy callback
to the flush queue. This file drives both through production code.
"""

from __future__ import annotations

from cbrowser.stream_agent.agent import StreamAgent
from cbrowser.stream_agent.config import StreamAgentConfig
from cbrowser.stream_agent.policy import (
    LiveCapturePolicyAgent,
    create_policy_controlled_service_class,
)


class _BaseService:
    """Minimal WebRTC service stand-in: records forwarded input."""

    def __init__(self, supervisor):
        self.supervisor = supervisor
        self.forwarded: list[tuple[object, str | None]] = []

    def _on_peer_data_message(
        self, msg, display_id: str = "primary", conn_id: str | None = None
    ):
        self.forwarded.append((msg, conn_id))
        return "forwarded"


def _make_service():
    service_cls = create_policy_controlled_service_class(_BaseService)
    service = service_cls(supervisor=None)
    service.policy_agent = LiveCapturePolicyAgent()
    seen: list[tuple[str | None, str]] = []
    service.policy_agent.on_human_takeover = lambda conn, kind: seen.append(
        (conn, kind)
    )
    return service, seen


def test_hook_reports_foreground_and_forwards_everything():
    service, seen = _make_service()
    policy = service.policy_agent
    policy.set_peer_active("conn-fg", True)
    policy.set_peer_active("conn-bg", False)

    # Foreground key press: classified, reported, and forwarded.
    service._on_peer_data_message("kd,65", conn_id="conn-fg")
    assert seen == [("conn-fg", "key")]
    # Background wheel: classified but suppressed, still forwarded.
    service._on_peer_data_message("sf,3", conn_id="conn-bg")
    assert seen == [("conn-fg", "key")]
    # Foreground pure mouse move: not a takeover, still forwarded.
    service._on_peer_data_message("m,100,200", conn_id="conn-fg")
    assert seen == [("conn-fg", "key")]
    # Foreground bare key release: not a takeover, still forwarded.
    service._on_peer_data_message("ku,65", conn_id="conn-fg")
    assert seen == [("conn-fg", "key")]
    # Unmapped connection: fail-closed to foreground, reported.
    service._on_peer_data_message("m2,1,100,200", conn_id="conn-unknown")
    assert seen == [("conn-fg", "key"), ("conn-unknown", "mouse_button")]
    # Input delivery is unconditional: every message reached the base.
    assert [m for m, _ in service.forwarded] == [
        "kd,65",
        "sf,3",
        "m,100,200",
        "ku,65",
        "m2,1,100,200",
    ]


def test_stream_agent_constructor_wires_policy_callback():
    config = StreamAgentConfig(
        profile_id="p1",
        runtime_instance_id="inst-1",
        gateway_url="ws://127.0.0.1:18080",
        agent_token="x" * 40,
    )
    agent = StreamAgent(config)
    # The constructor itself (not a hand-built object) connects the
    # policy callback to this agent's report method.
    callback = agent.policy.on_human_takeover
    assert callback is not None
    assert callback.__self__ is agent
    assert callback.__func__ is StreamAgent.report_human_takeover
    # Driving the wired callback queues a pending report for flush.
    agent.policy.on_human_takeover("conn-1", "key")
    assert agent._pending_takeovers == [
        {"conn_id": "conn-1", "input_kind": "key"}
    ]
