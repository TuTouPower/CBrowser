"""Unit tests for the t030 page ledger (origin / management / cleanup split)."""

from __future__ import annotations

from cbrowser.agent_executor.ledger import PageLedger


def test_baseline_pages_are_user_and_never_cleanable() -> None:
    ledger = PageLedger("p1", "i1")
    ledger.baseline(["t-user-1", "t-user-2"])
    closable, refused = ledger.cleanup_plan(["t-user-1", "t-user-2"])
    assert closable == []
    assert refused == []


def test_created_pages_are_agent_owned_and_cleanable() -> None:
    ledger = PageLedger("p1", "i1")
    ledger.baseline(["t-user"])
    ledger.record_created("t-agent")
    closable, refused = ledger.cleanup_plan(["t-user", "t-agent"])
    assert closable == ["t-agent"]
    assert refused == []


def test_adopt_keeps_origin_and_grants_no_cleanup() -> None:
    ledger = PageLedger("p1", "i1")
    ledger.baseline(["t-user"])
    record = ledger.adopt("t-user")
    assert record.origin == "user"
    assert record.manageable is True
    assert record.cleanable is False
    closable, _ = ledger.cleanup_plan(["t-user"])
    assert closable == []


def test_adopt_of_unknown_target_stays_unknown() -> None:
    ledger = PageLedger("p1", "i1")
    record = ledger.adopt("t-stranger")
    assert record.origin == "unknown"
    assert record.cleanable is False


def test_popup_without_attribution_window_is_unknown() -> None:
    ledger = PageLedger("p1", "i1")
    ledger.record_created("t-agent")
    record = ledger.record_observed("t-popup", opener_id="t-agent")
    assert record.origin == "unknown"
    assert record.cleanable is False


def test_popup_inside_attribution_window_from_agent_page_is_agent() -> None:
    ledger = PageLedger("p1", "i1")
    ledger.record_created("t-agent")
    ledger.expect_popup(["t-agent"])
    record = ledger.record_observed("t-popup", opener_id="t-agent")
    assert record.origin == "agent"
    assert record.cleanable is True


def test_popup_window_from_user_page_is_not_attributed() -> None:
    ledger = PageLedger("p1", "i1")
    ledger.baseline(["t-user"])
    ledger.expect_popup(["t-user"])
    record = ledger.record_observed("t-popup", opener_id="t-user")
    assert record.origin == "unknown"


def test_concurrent_user_page_is_unknown_and_preserved() -> None:
    ledger = PageLedger("p1", "i1")
    ledger.baseline(["t-user"])
    ledger.record_created("t-agent")
    record = ledger.record_observed("t-concurrent")
    assert record.origin == "unknown"
    closable, _ = ledger.cleanup_plan(["t-user", "t-agent", "t-concurrent"])
    assert closable == ["t-agent"]


def test_last_remaining_page_is_never_closed() -> None:
    ledger = PageLedger("p1", "i1")
    ledger.record_created("t-only")
    closable, refused = ledger.cleanup_plan(["t-only"])
    assert closable == []
    assert refused == [{"target_id": "t-only", "reason": "last_tab_protected"}]


def test_last_tab_rule_keeps_newest_when_all_are_agent_pages() -> None:
    ledger = PageLedger("p1", "i1")
    ledger.record_created("t-old")
    ledger.record_created("t-new")
    closable, refused = ledger.cleanup_plan(["t-old", "t-new"])
    assert closable == ["t-old"]
    assert refused == [{"target_id": "t-new", "reason": "last_tab_protected"}]


def test_baseline_does_not_overwrite_observed_record() -> None:
    ledger = PageLedger("p1", "i1")
    ledger.record_created("t-agent")
    ledger.expect_popup(["t-agent"])
    ledger.record_observed("t-popup", opener_id="t-agent")
    ledger.baseline(["t-popup"])
    assert ledger.get("t-popup") is not None
    assert ledger.get("t-popup").origin == "agent"


def test_closed_pages_drop_from_ledger() -> None:
    ledger = PageLedger("p1", "i1")
    ledger.record_created("t-agent")
    ledger.record_closed("t-agent")
    assert ledger.get("t-agent") is None
