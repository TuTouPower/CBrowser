"""Evidence collection utilities.

Saves JSON artifacts to test tmp_path or designated evidence dir.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

_run_evidence_dir: Path | None = None


def _default_evidence_dir() -> Path:
    """Per-run private evidence directory (t024 AC-011/A33): the former
    shared, predictable tmp path let runs and users collide and kept
    artifacts world-readable indefinitely."""
    global _run_evidence_dir
    if _run_evidence_dir is None:
        _run_evidence_dir = Path(tempfile.mkdtemp(prefix="cbrowser_e2e_evidence_"))
        _run_evidence_dir.chmod(0o700)
    return _run_evidence_dir


def resolve_evidence_dir(target_dir: Path | str | None = None) -> Path:
    env_dir = os.environ.get("CBROWSER_E2E_EVIDENCE_DIR")
    if env_dir:
        return Path(env_dir)
    if target_dir is not None:
        return Path(target_dir)
    return _default_evidence_dir()


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(
                marker in lowered
                for marker in (
                    "token",
                    "secret",
                    "password",
                    "cookie",
                    "resume_key",
                    "session",
                )
            ):
                redacted[key] = "<redacted>"
            elif lowered in {"data", "payload", "frame"} and isinstance(item, str):
                redacted[key] = f"<redacted:{len(item)} bytes>"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def save_evidence(
    name: str, payload: Any, target_dir: Path | str | None = None
) -> Path:
    """Writes JSON evidence artifact to target directory/<name>.json."""
    out_dir = resolve_evidence_dir(target_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}.json"
    content = json.dumps(_redact(payload), indent=2, ensure_ascii=False)
    target.write_text(content, encoding="utf-8")
    return target
