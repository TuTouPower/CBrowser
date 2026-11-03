"""Shared exit-reason vocabulary is fully covered by the event-log allowlist."""

from cbrowser.domain.runtime_policy import ExitReason
from cbrowser.runtime_event_log import _sanitize_reason


def test_all_known_exit_reasons_are_logged_verbatim() -> None:
    for reason in ExitReason:
        assert _sanitize_reason(reason.value) == reason.value


def test_unknown_exit_reason_is_redacted() -> None:
    assert _sanitize_reason("private-user-value") == "custom_reason"
    assert _sanitize_reason(None) is None


def test_emit_runtime_event_log_writes_sanitized_json(caplog) -> None:
    """AC-010: the packaged emitter writes one sanitized JSON record —
    non-canonical ids are hashed, unknown reasons collapse, and the raw
    values never appear in the log line."""
    import json
    import logging

    from cbrowser.runtime_event_log import emit_runtime_event_log

    with caplog.at_level(logging.INFO, logger="cbrowser.events"):
        emit_runtime_event_log(
            event_id="raw-private-event",
            profile_id="prof_1234abcd",
            runtime_instance_id="instance secret value",
            event_type="exit",
            exit_code=3,
            exit_reason="private-user-value",
            config_version=2,
            outcome="recorded",
        )
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "cbrowser.events"
    ]
    assert len(messages) == 1
    assert messages[0].startswith("RUNTIME_EVENT_JSON: ")
    payload = json.loads(messages[0].split(": ", 1)[1])
    assert payload["event_id"].startswith("id_hash_")
    assert payload["runtime_instance_id"].startswith("id_hash_")
    assert payload["profile_id"] == "prof_1234abcd"
    assert payload["exit_reason"] == "custom_reason"
    assert payload["exit_code"] == 3
    assert "raw-private-event" not in messages[0]
    assert "instance secret value" not in messages[0]
