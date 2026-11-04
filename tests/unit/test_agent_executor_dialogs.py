"""Unit tests for t030 dialog defaults and tracker."""

from __future__ import annotations

import pytest

from cbrowser.agent_executor.dialogs import (
    DialogRecord,
    DialogTracker,
    default_action,
    permission_needs_human_payload,
)


def test_alert_default_closes() -> None:
    assert default_action("alert") == "accept"


def test_confirm_prompt_beforeunload_never_default_accept() -> None:
    for kind in ("confirm", "prompt", "beforeunload"):
        assert default_action(kind) == "dismiss"


def test_tracker_answers_with_explicit_answer() -> None:
    tracker = DialogTracker()
    tracker.record_opening(
        DialogRecord(target_id="t-1", dialog_type="confirm", message="Sure?")
    )
    action, _ = tracker.decide("t-1", answer="accept")
    assert action == "accept"


def test_tracker_applies_conservative_default_without_handler() -> None:
    tracker = DialogTracker()
    tracker.record_opening(
        DialogRecord(target_id="t-1", dialog_type="prompt", message="Name?")
    )
    action, text = tracker.decide("t-1", prompt_text="ignored-by-default")
    assert action == "dismiss"
    assert text == "ignored-by-default"


def test_tracker_rejects_answer_when_no_dialog_open() -> None:
    tracker = DialogTracker()
    with pytest.raises(KeyError, match="no dialog open"):
        tracker.decide("t-1", answer="accept")


def test_closed_dialog_clears_state() -> None:
    tracker = DialogTracker()
    tracker.record_opening(
        DialogRecord(target_id="t-1", dialog_type="alert", message="Hi")
    )
    tracker.record_closed("t-1")
    assert tracker.open_for("t-1") is None


def test_permission_payload_never_grants() -> None:
    payload = permission_needs_human_payload(
        profile_id="p1",
        runtime_instance_id="i1",
        target_id="t-1",
        kind="camera",
        session_id="s-1",
    )
    assert payload["decision"] == "needs_human"
    assert payload["permission_kind"] == "camera"
    assert "grant" not in payload["decision"]


def test_tracker_rejects_invalid_answer_instead_of_folding_to_default() -> None:
    # A typo ("accep") must not silently become the opposite default:
    # the caller asked for accept and would get dismiss with no signal.
    tracker = DialogTracker()
    tracker.record_opening(
        DialogRecord(target_id="t-1", dialog_type="confirm", message="Sure?")
    )
    with pytest.raises(ValueError, match="invalid dialog answer"):
        tracker.decide("t-1", answer="accep")
    # The record is untouched: the caller can retry with a valid answer.
    action, _ = tracker.decide("t-1", answer="accept")
    assert action == "accept"
