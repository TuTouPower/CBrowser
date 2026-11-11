"""Structured runtime-event logging for the backend.

This module carries the runtime event log emitter that used to live in
the legacy top-level ``diagnostics`` module (deleted with A42): the
sanitizers and the allowlist emitter are part of the installed
``cbrowser`` package so profile services no longer depend on an external
top-level legacy module.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sys

from cbrowser.domain.runtime_policy import ExitReason

_EVENT_LOGGER = logging.getLogger("cbrowser.events")
_EVENT_LOGGER.setLevel(logging.INFO)
if not _EVENT_LOGGER.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("%(message)s"))
    _EVENT_LOGGER.addHandler(_h)


_CANONICAL_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_CANONICAL_SYS_RE = re.compile(r"^(?:inst|evt|prof|op)_[0-9a-zA-Z]{4,32}$")
_SAFE_EXIT_REASONS = {reason.value for reason in ExitReason}


def _sanitize_id(val: str) -> str:
    s = str(val).strip()
    if _CANONICAL_UUID_RE.match(s) or _CANONICAL_SYS_RE.match(s):
        return s
    digest = hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]
    return f"id_hash_{digest}"


def _sanitize_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    r = str(reason).strip().lower()
    return r if r in _SAFE_EXIT_REASONS else "custom_reason"


def emit_runtime_event_log(
    *,
    event_id: str,
    profile_id: str,
    runtime_instance_id: str,
    event_type: str,
    exit_code: int | None,
    exit_reason: str | None,
    config_version: int,
    outcome: str,
) -> None:
    """Emit a structured JSON log for runtime events using an explicit allowlist of safe fields.

    Never logs passwords, tokens, cookies, clipboard content, or private strings.
    """
    import datetime
    import json

    safe_record = {
        "event_id": _sanitize_id(event_id),
        "profile_id": _sanitize_id(profile_id),
        "runtime_instance_id": _sanitize_id(runtime_instance_id),
        "event_type": str(event_type).strip().lower() if event_type in ("exit", "heartbeat", "lifecycle") else "unknown",
        "exit_code": int(exit_code) if exit_code is not None else None,
        "exit_reason": _sanitize_reason(exit_reason),
        "config_version": int(config_version),
        "outcome": str(outcome),
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    record_json = json.dumps(safe_record, separators=(",", ":"))
    _EVENT_LOGGER.info("RUNTIME_EVENT_JSON: %s", record_json)
