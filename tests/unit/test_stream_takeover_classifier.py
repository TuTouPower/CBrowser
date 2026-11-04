"""t031 Stream takeover classifier + foreground resolution."""

from __future__ import annotations

from cbrowser.stream_agent.policy import (
    LiveCapturePolicyAgent,
    classify_human_takeover_input,
)


def test_classifier_table():
    assert classify_human_takeover_input("kd,65") == "key"
    assert classify_human_takeover_input("ku,65") is None
    assert classify_human_takeover_input("m,100,200") is None
    assert classify_human_takeover_input("m2,1,100,200") == "mouse_button"
    assert classify_human_takeover_input("sf,3") == "wheel"
    assert classify_human_takeover_input("sfe,-3") == "wheel"
    assert classify_human_takeover_input("co,end") == "ime_commit"
    assert classify_human_takeover_input("co,end,abc") == "ime_commit"
    assert classify_human_takeover_input("co,update,ab") is None
    assert classify_human_takeover_input("co,") is None
    assert classify_human_takeover_input("SETTINGS,foo") is None
    assert classify_human_takeover_input("") is None
    assert classify_human_takeover_input(None) is None
    assert classify_human_takeover_input(123) is None


def test_foreground_resolution():
    agent = LiveCapturePolicyAgent()
    # Unmapped connection: fail-closed to foreground.
    assert agent.is_foreground_input("conn-unknown") is True
    # Missing conn id: fail-closed to foreground.
    assert agent.is_foreground_input(None) is True
    # Mapped viewer, active: foreground.
    agent.set_peer_active("conn-a", True)
    assert agent.is_foreground_input("conn-a") is True
    # Mapped viewer, background: no takeover.
    agent.set_peer_active("conn-b", False)
    assert agent.is_foreground_input("conn-b") is False
    # SDK peer id resolves through the mapping to its conn id.
    agent.register_peer_mapping("sdk-1", "conn-a")
    assert agent.is_foreground_input("sdk-1") is True
    agent.set_peer_active("conn-a", False)
    assert agent.is_foreground_input("sdk-1") is False


def test_report_callback_invoked_only_for_foreground_takeover():
    agent = LiveCapturePolicyAgent()
    seen: list[tuple[str | None, str]] = []
    agent.on_human_takeover = lambda conn, kind: seen.append((conn, kind))
    agent.set_peer_active("conn-bg", False)
    # Background wheel: classified but not reported.
    kind = classify_human_takeover_input("sf,3")
    assert kind == "wheel"
    if kind and agent.is_foreground_input("conn-bg"):
        agent.report_human_takeover("conn-bg", kind)
    assert seen == []
    # Foreground key: reported.
    agent.set_peer_active("conn-fg", True)
    kind = classify_human_takeover_input("kd,65")
    if kind and agent.is_foreground_input("conn-fg"):
        agent.report_human_takeover("conn-fg", kind)
    assert seen == [("conn-fg", "key")]
    # A failing callback never breaks the caller.
    agent.on_human_takeover = lambda conn, kind: (_ for _ in ()).throw(
        RuntimeError("boom")
    )
    agent.report_human_takeover("conn-fg", "key")
