"""Unit tests for the runtime-agent CDP tunnel filter (t030).

The filter mediates external-client CDP traffic at the Agent UDS ``/cdp``
tunnel: Browser.close and other t029 MUST_MEDIATE commands must not reach
the browser unchecked, while the executor's own pages stay closable and
Playwright's per-session utility injection is registered and cleaned up on
disconnect instead of flat-rejected (flat rejection breaks connect_over_cdp).
"""

from __future__ import annotations

from cbrowser.runtime_agent.tunnel_filter import TunnelFilter


def _msg(method: str, msg_id: int = 1, **kw):
    msg: dict = {"id": msg_id, "method": method, "params": kw.pop("params", {})}
    msg.update(kw)
    return msg


def test_browser_close_always_rejected_with_stable_error() -> None:
    f = TunnelFilter()
    decision, response = f.filter_outgoing(_msg("Browser.close"))
    assert decision == "reject"
    assert response is not None
    assert response["id"] == 1
    assert response["error"]["code"] == -32000
    assert "Browser.close" in response["error"]["message"]


def test_browser_close_rejection_preserves_session_id() -> None:
    f = TunnelFilter()
    decision, response = f.filter_outgoing(_msg("Browser.close", sessionId="sess-1"))
    assert decision == "reject"
    assert response is not None
    assert response["sessionId"] == "sess-1"


def test_idless_destructive_command_is_dropped_without_forward() -> None:
    f = TunnelFilter()
    decision, response = f.filter_outgoing({"method": "Browser.close"})
    assert decision == "reject"
    assert response is None  # nothing to correlate; dropping is the safe reply


def test_download_behavior_rejected() -> None:
    f = TunnelFilter()
    for method in ("Browser.setDownloadBehavior", "Page.setDownloadBehavior"):
        decision, _ = f.filter_outgoing(_msg(method))
        assert decision == "reject", method


def test_emulation_and_network_overrides_rejected() -> None:
    f = TunnelFilter()
    for method in (
        "Emulation.setUserAgentOverride",
        "Emulation.setDeviceMetricsOverride",
        "Emulation.setGeolocationOverride",
        "Emulation.setTouchEmulationEnabled",
        "Emulation.setFocusEmulationEnabled",
        "Emulation.setEmulatedMedia",
        "Network.emulateNetworkConditions",
    ):
        decision, _ = f.filter_outgoing(_msg(method))
        assert decision == "reject", method


def test_unrelated_methods_forward() -> None:
    f = TunnelFilter()
    for method in (
        "Page.navigate",
        "Runtime.evaluate",
        "Target.getTargets",
        "DOM.getDocument",
        "Input.dispatchMouseEvent",
        "Page.handleJavaScriptDialog",
    ):
        decision, response = f.filter_outgoing(_msg(method))
        assert decision == "forward", method
        assert response is None


def test_unparseable_or_methodless_messages_forward() -> None:
    f = TunnelFilter()
    decision, _ = f.filter_outgoing({"id": 9})
    assert decision == "forward"
    decision, _ = f.filter_outgoing({"id": 9, "method": 123})
    assert decision == "forward"


def test_close_target_forwarded_when_tunnel_cannot_prove_last_tab() -> None:
    # The tunnel does not ownership-filter closes: Playwright popup flows
    # (click-opened popups from any page) require closeTarget to pass.
    # Tab-close authorization lives in the executor ledger.
    f = TunnelFilter()
    decision, _ = f.filter_outgoing(
        _msg("Target.closeTarget", params={"targetId": "t-user"})
    )
    assert decision == "forward"


def test_close_target_rejected_only_for_observed_last_page() -> None:
    f = TunnelFilter()
    f.filter_outgoing(_msg("Target.getTargets", msg_id=2))
    f.observe_incoming(
        {
            "id": 2,
            "result": {
                "targetInfos": [
                    {"targetId": "t-only", "type": "page"},
                    {"targetId": "t-other", "type": "page"},
                ]
            },
        }
    )
    decision, _ = f.filter_outgoing(
        _msg("Target.closeTarget", msg_id=3, params={"targetId": "t-only"})
    )
    assert decision == "forward"
    f.observe_incoming(
        {
            "method": "Target.targetDestroyed",
            "params": {"targetId": "t-other"},
        }
    )
    decision, response = f.filter_outgoing(
        _msg("Target.closeTarget", msg_id=4, params={"targetId": "t-only"})
    )
    assert decision == "reject"
    assert response is not None
    assert "last_tab_protected" in response["error"]["message"]


def test_page_close_last_tab_backstop_via_session_mapping() -> None:
    f = TunnelFilter()
    f.filter_outgoing(_msg("Target.getTargets", msg_id=2))
    f.observe_incoming(
        {
            "id": 2,
            "result": {"targetInfos": [{"targetId": "t-only", "type": "page"}]},
        }
    )
    f.filter_outgoing(
        _msg("Target.attachToTarget", msg_id=3, params={"targetId": "t-only"})
    )
    f.observe_incoming({"id": 3, "result": {"sessionId": "s-only"}})
    decision, _ = f.filter_outgoing(_msg("Page.close", msg_id=4, sessionId="s-only"))
    assert decision == "reject"
    decision, _ = f.filter_outgoing(_msg("Page.close", msg_id=5, sessionId="s-other"))
    assert decision == "forward"


def test_target_created_and_destroyed_track_known_pages() -> None:
    f = TunnelFilter()
    f.observe_incoming(
        {
            "method": "Target.targetCreated",
            "params": {
                "targetInfo": {"targetId": "t-a", "type": "page"},
            },
        }
    )
    f.observe_incoming(
        {
            "method": "Target.targetCreated",
            "params": {
                "targetInfo": {"targetId": "t-b", "type": "page"},
            },
        }
    )
    decision, _ = f.filter_outgoing(
        _msg("Target.closeTarget", msg_id=3, params={"targetId": "t-a"})
    )
    assert decision == "forward"
    f.observe_incoming(
        {"method": "Target.targetDestroyed", "params": {"targetId": "t-b"}}
    )
    decision, _ = f.filter_outgoing(
        _msg("Target.closeTarget", msg_id=4, params={"targetId": "t-a"})
    )
    assert decision == "reject"


def test_add_script_registered_and_removal_built_on_disconnect() -> None:
    f = TunnelFilter()
    decision, _ = f.filter_outgoing(
        _msg(
            "Page.addScriptToEvaluateOnNewDocument",
            msg_id=7,
            sessionId="s-1",
            params={"source": "1"},
        )
    )
    assert decision == "forward"
    f.observe_incoming({"id": 7, "result": {"identifier": "script-9"}})
    cleanup = f.disconnect_cleanup_commands()
    assert len(cleanup) == 1
    cmd = cleanup[0]
    assert cmd["method"] == "Page.removeScriptToEvaluateOnNewDocument"
    assert cmd["params"] == {"identifier": "script-9"}
    assert cmd["sessionId"] == "s-1"
    assert isinstance(cmd["id"], int)


def test_add_script_without_response_identifier_is_not_cleaned() -> None:
    f = TunnelFilter()
    f.filter_outgoing(
        _msg(
            "Page.addScriptToEvaluateOnNewDocument",
            msg_id=7,
            sessionId="s-1",
            params={"source": "1"},
        )
    )
    f.observe_incoming({"id": 7, "error": {"code": -32000, "message": "nope"}})
    assert f.disconnect_cleanup_commands() == []


def test_get_targets_response_without_pages_keeps_close_forwarded() -> None:
    f = TunnelFilter()
    f.filter_outgoing(_msg("Target.getTargets", msg_id=2))
    f.observe_incoming({"id": 2, "result": {}})
    decision, _ = f.filter_outgoing(
        _msg("Target.closeTarget", msg_id=3, params={"targetId": "t-x"})
    )
    assert decision == "forward"


def test_error_get_targets_response_does_not_clear_known_pages() -> None:
    # The last-page backstop is built from observed pages; a failed
    # getTargets response carries no targetInfos and must not wipe it,
    # or the next close of the only page would slip through.
    f = TunnelFilter()
    f.filter_outgoing(_msg("Target.getTargets", msg_id=2))
    f.observe_incoming(
        {
            "id": 2,
            "result": {"targetInfos": [{"targetId": "t-only", "type": "page"}]},
        }
    )
    decision, _ = f.filter_outgoing(
        _msg("Target.closeTarget", msg_id=3, params={"targetId": "t-only"})
    )
    assert decision == "reject"
    f.filter_outgoing(_msg("Target.getTargets", msg_id=4))
    f.observe_incoming(
        {"id": 4, "error": {"code": -32000, "message": "boom"}}
    )
    decision, _ = f.filter_outgoing(
        _msg("Target.closeTarget", msg_id=5, params={"targetId": "t-only"})
    )
    assert decision == "reject"
