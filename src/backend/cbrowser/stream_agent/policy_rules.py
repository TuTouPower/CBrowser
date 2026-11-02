"""Pure client-policy rules and constants."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

FORBIDDEN_PEER_PREFIXES: tuple[str, ...] = (
    "_arg_fps,",
    "r,",
    "s,",
    "_rc,",
    "_crf,",
    "vb,",
    "ab,",
)

DISALLOWED_SETTINGS_KEYS: set[str] = {
    "framerate",
    "manual_width",
    "manual_height",
    "manual_resolution",
    "scaling_dpi",
    "video_streaming_mode",
    "force_aligned_resolution",
    "video_bitrate",
    "rate_control_mode",
    "video_crf",
}

MAX_HISTORY_SIZE: int = 500

_SAFE_CALLER_RE = re.compile(r"^[A-Za-z0-9_:\-]{1,64}$")


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


def sanitize_caller(caller: Any) -> str:
    if not isinstance(caller, str):
        return "unknown"
    s = caller.strip()
    if _SAFE_CALLER_RE.match(s):
        return s
    return "sanitized"


def sanitize_settings_message(msg: str) -> str | None:
    if not isinstance(msg, str) or not msg.startswith("SETTINGS,"):
        return msg
    try:
        payload = json.loads(msg.split(",", 1)[1])
        if not isinstance(payload, dict):
            return None
        for k in DISALLOWED_SETTINGS_KEYS:
            payload.pop(k, None)
        return "SETTINGS," + json.dumps(payload)
    except (ValueError, json.JSONDecodeError):
        return None


def should_block_client_verb(msg: str) -> bool:
    if isinstance(msg, str):
        return msg.startswith(FORBIDDEN_PEER_PREFIXES)
    return False
