"""Evidence collection utilities.

Saves JSON artifacts to test tmp_path or designated evidence dir.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_EVIDENCE_DIR = Path(".scratch/t006_relay/evidence")


def resolve_evidence_dir(target_dir: Path | str | None = None) -> Path:
    env_dir = os.environ.get("CBROWSER_E2E_EVIDENCE_DIR")
    if env_dir:
        return Path(env_dir)
    if target_dir is not None:
        return Path(target_dir)
    return DEFAULT_EVIDENCE_DIR


def save_evidence(
    name: str, payload: Any, target_dir: Path | str | None = None
) -> Path:
    """Writes JSON evidence artifact to target directory/<name>.json."""
    out_dir = resolve_evidence_dir(target_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}.json"
    content = json.dumps(payload, indent=2, ensure_ascii=False)
    target.write_text(content, encoding="utf-8")
    return target
