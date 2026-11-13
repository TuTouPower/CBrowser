"""Persistent executor session state (t030).

One CLI invocation is one process, but one agent session spans many
invocations: an agent snapshots in one call and acts on a ref in the next.
Refs and page ownership therefore persist in a JSON state file keyed by
(profile, runtime-instance).  The file holds no tokens, cookies or
credentials -- only ref mappings and ledger metadata -- and is written
atomically with 0600 permissions.  Missing, corrupt or wrong-version state
resets to empty rather than failing the call; live validation (runtime,
target, frame, loader, signature) still rejects every stale ref.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from cbrowser.shared.atomic_write import atomic_write_text

from .ledger import PageRecord
from .refs import RefEntry

STATE_VERSION = 1


def _safe(value: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in value)


def default_state_path(profile_id: str, runtime_instance_id: str) -> Path:
    """Default state file under the user's cache directory."""
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return (
        cache
        / "cbrowser"
        / "agent-executor"
        / f"{_safe(profile_id)}_{_safe(runtime_instance_id)}.json"
    )


def load_state(path: Path) -> dict:
    """Load a state file; missing/corrupt/wrong-version state is empty.

    The payload carries the (profile, runtime) binding it was written
    for; callers must check that binding against the live invocation
    before trusting snapshots/ledger (see :func:`bound_state`).
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"snapshots": {}, "ledger": {}}
    if not isinstance(data, dict) or data.get("version") != STATE_VERSION:
        return {"snapshots": {}, "ledger": {}}
    snapshots = data.get("snapshots", {})
    ledger = data.get("ledger", {})
    if not isinstance(snapshots, dict) or not isinstance(ledger, dict):
        return {"snapshots": {}, "ledger": {}}
    return {
        "profile": data.get("profile"),
        "runtime_instance_id": data.get("runtime_instance_id"),
        "snapshots": snapshots,
        "ledger": ledger,
    }


def bound_state(
    state: dict, *, profile_id: str, runtime_instance_id: str
) -> tuple[dict, dict]:
    """Return (snapshots, ledger) only when the state binding matches.

    A state file written for another profile/runtime -- or an old file
    with no binding at all -- yields empty state.  Trusting it would let
    a copied state file smuggle another runtime's refs and cleanable
    page grants into this invocation.
    """
    if (
        state.get("profile") != profile_id
        or state.get("runtime_instance_id") != runtime_instance_id
    ):
        return {}, {}
    return state.get("snapshots", {}), state.get("ledger", {})


def save_state(
    path: Path,
    snapshots: dict[str, dict[str, dict]],
    ledger: dict[str, dict],
    *,
    profile_id: str,
    runtime_instance_id: str,
) -> None:
    """Atomically write state (tmp file + rename) with 0600 permissions."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": STATE_VERSION,
        "profile": profile_id,
        "runtime_instance_id": runtime_instance_id,
        "snapshots": snapshots,
        "ledger": ledger,
    }
    atomic_write_text(path, json.dumps(payload), mode=0o600)


def decode_snapshots(raw: dict) -> dict[str, dict[str, RefEntry]]:
    """Decode persisted snapshots, skipping malformed entries."""
    out: dict[str, dict[str, RefEntry]] = {}
    for target_id, refs in raw.items():
        if not isinstance(refs, dict):
            continue
        entries: dict[str, RefEntry] = {}
        for ref, data in refs.items():
            try:
                entry = RefEntry.from_dict(data)
            except (KeyError, TypeError, ValueError):
                continue
            entries[ref] = entry
        if entries:
            out[str(target_id)] = entries
    return out


def decode_ledger(raw: dict) -> dict[str, PageRecord]:
    """Decode persisted ledger records, skipping malformed entries."""
    out: dict[str, PageRecord] = {}
    for target_id, data in raw.items():
        if not isinstance(data, dict):
            continue
        try:
            origin = str(data["origin"])
            if origin not in ("agent", "user", "unknown"):
                continue
            out[str(target_id)] = PageRecord(
                target_id=str(target_id),
                origin=origin,
                manageable=bool(data["manageable"]),
                cleanable=bool(data["cleanable"]),
                opener_id=data.get("opener_id"),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out
