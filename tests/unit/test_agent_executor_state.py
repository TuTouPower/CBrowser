"""Unit tests for t030 cross-invocation session state (refs + ledger)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from cbrowser.agent_executor.refs import RefEntry
from cbrowser.agent_executor.state import (
    bound_state,
    decode_ledger,
    decode_snapshots,
    default_state_path,
    load_state,
    save_state,
)


def _entry() -> RefEntry:
    return RefEntry(
        ref="f0e0",
        target_id="t-1",
        frame_id="f1",
        loader_id="l1",
        backend_node_id=10,
        signature="abcd1234",
        role="button",
        name="Go",
        tag="BUTTON",
        attrs={"id": "go"},
    )


def test_ref_entry_round_trips_through_dict() -> None:
    assert RefEntry.from_dict(_entry().to_dict()) == _entry()


def test_default_state_path_uses_cache_home_and_sanitizes(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    path = default_state_path("p 1", "i/1")
    assert path.parent == tmp_path / "cbrowser" / "agent-executor"
    assert path.name == "p_1_i_1.json"


def test_save_load_round_trip(tmp_path) -> None:
    path = tmp_path / "state.json"
    snapshots = {"t-1": {"f0e0": _entry().to_dict()}}
    ledger = {
        "t-1": {
            "origin": "agent",
            "manageable": True,
            "cleanable": True,
            "opener_id": None,
        }
    }
    save_state(
        path, snapshots, ledger, profile_id="p1", runtime_instance_id="i1"
    )
    assert path.exists()
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    loaded = load_state(path)
    assert loaded["snapshots"] == snapshots
    assert loaded["ledger"] == ledger
    assert loaded["profile"] == "p1"
    assert loaded["runtime_instance_id"] == "i1"


def test_bound_state_matches_only_exact_profile_and_runtime(tmp_path) -> None:
    path = tmp_path / "state.json"
    snapshots = {"t-1": {"f0e0": _entry().to_dict()}}
    ledger = {"t-1": {"origin": "agent", "manageable": True, "cleanable": True}}
    save_state(
        path, snapshots, ledger, profile_id="p1", runtime_instance_id="i1"
    )
    state = load_state(path)
    assert bound_state(state, profile_id="p1", runtime_instance_id="i1") == (
        snapshots,
        ledger,
    )
    # Another runtime, another profile, or an old unbound file: empty.
    assert bound_state(state, profile_id="p1", runtime_instance_id="i2") == (
        {},
        {},
    )
    assert bound_state(state, profile_id="p2", runtime_instance_id="i1") == (
        {},
        {},
    )
    assert bound_state(
        {"snapshots": snapshots, "ledger": ledger},
        profile_id="p1",
        runtime_instance_id="i1",
    ) == ({}, {})


def test_load_missing_corrupt_or_wrong_version_is_empty(tmp_path) -> None:
    assert load_state(tmp_path / "nope.json") == {"snapshots": {}, "ledger": {}}
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    assert load_state(corrupt) == {"snapshots": {}, "ledger": {}}
    wrong = tmp_path / "wrong.json"
    wrong.write_text(
        json.dumps({"version": 99, "snapshots": {}, "ledger": {}}),
        encoding="utf-8",
    )
    assert load_state(wrong) == {"snapshots": {}, "ledger": {}}


def test_decode_skips_malformed_entries_but_keeps_good_ones() -> None:
    snapshots = decode_snapshots(
        {
            "t-1": {"f0e0": _entry().to_dict(), "bad": {"ref": 1}},
            "t-2": "not-a-dict",
        }
    )
    assert list(snapshots) == ["t-1"]
    assert snapshots["t-1"]["f0e0"] == _entry()
    ledger = decode_ledger(
        {
            "t-1": {
                "origin": "agent",
                "manageable": True,
                "cleanable": True,
                "opener_id": None,
            },
            "t-2": {"origin": "bogus"},
            "t-3": "not-a-dict",
        }
    )
    assert list(ledger) == ["t-1"]
    assert ledger["t-1"].origin == "agent"
    assert ledger["t-1"].cleanable is True
