"""t031 tunnel_filter: setAutoAttach sessions must not bypass backstops."""

from __future__ import annotations

from cbrowser.runtime_agent.tunnel_filter import TunnelFilter


def _get_targets_response(filter_: TunnelFilter, pages: list[str]):
    filter_.filter_outgoing({"id": 1, "method": "Target.getTargets"})
    filter_.observe_incoming(
        {
            "id": 1,
            "result": {
                "targetInfos": [
                    {"targetId": pid, "type": "page"} for pid in pages
                ]
            },
        }
    )


def test_auto_attached_session_page_close_backstop():
    """Page.close through an auto-attached session hits the backstop."""
    filter_ = TunnelFilter()
    _get_targets_response(filter_, ["only-page"])
    # No setDiscoverTargets: no targetCreated events. The page becomes
    # known only through the auto-attach event.
    filter_.observe_incoming(
        {
            "method": "Target.attachedToTarget",
            "params": {
                "sessionId": "auto-session-1",
                "targetInfo": {"targetId": "only-page", "type": "page"},
            },
        }
    )
    decision, _ = filter_.filter_outgoing(
        {
            "id": 2,
            "method": "Page.close",
            "sessionId": "auto-session-1",
        }
    )
    assert decision == "reject"


def test_auto_attached_session_close_target_backstop():
    """closeTarget on an auto-attach-discovered page hits the backstop."""
    filter_ = TunnelFilter()
    # The page set is empty until auto-attach teaches it.
    filter_.observe_incoming(
        {
            "method": "Target.attachedToTarget",
            "params": {
                "sessionId": "auto-session-2",
                "targetInfo": {"targetId": "solo", "type": "page"},
            },
        }
    )
    decision, _ = filter_.filter_outgoing(
        {"id": 3, "method": "Target.closeTarget", "params": {"targetId": "solo"}}
    )
    assert decision == "reject"


def test_set_auto_attach_itself_is_forwarded():
    """setAutoAttach is not rejected: it is the executor's transport."""
    filter_ = TunnelFilter()
    decision, _ = filter_.filter_outgoing(
        {
            "id": 4,
            "method": "Target.setAutoAttach",
            "params": {"autoAttach": True, "waitForDebuggerOnStart": False},
        }
    )
    assert decision == "forward"


def test_detach_clears_session_mapping():
    filter_ = TunnelFilter()
    _get_targets_response(filter_, ["only-page"])
    filter_.observe_incoming(
        {
            "method": "Target.attachedToTarget",
            "params": {
                "sessionId": "auto-session-3",
                "targetInfo": {"targetId": "only-page", "type": "page"},
            },
        }
    )
    filter_.observe_incoming(
        {
            "method": "Target.detachedFromTarget",
            "params": {"sessionId": "auto-session-3"},
        }
    )
    # Detached session no longer resolves: forward (Chrome rejects the
    # dead session itself); the backstop no longer misfires on it.
    decision, _ = filter_.filter_outgoing(
        {
            "id": 5,
            "method": "Page.close",
            "sessionId": "auto-session-3",
        }
    )
    assert decision == "forward"
