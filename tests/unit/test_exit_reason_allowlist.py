"""Shared exit-reason vocabulary is fully covered by the diagnostics allowlist."""

from cbrowser.domain.runtime_policy import ExitReason
from diagnostics import _sanitize_reason


def test_all_known_exit_reasons_are_logged_verbatim() -> None:
    for reason in ExitReason:
        assert _sanitize_reason(reason.value) == reason.value


def test_unknown_exit_reason_is_redacted() -> None:
    assert _sanitize_reason("private-user-value") == "custom_reason"
    assert _sanitize_reason(None) is None
