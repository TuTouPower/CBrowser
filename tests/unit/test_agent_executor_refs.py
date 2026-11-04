"""Unit tests for the t030 ref registry (build + per-item validation)."""

from __future__ import annotations

import pytest

from cbrowser.agent_executor.refs import (
    RefStaleError,
    build_snapshot,
    describe_signature,
    map_iframe_frames,
    validate_ref,
)

FRAMES = [("frame-1", "loader-1"), ("frame-2", "loader-2")]
# backend -> (nodeName, attributes, frame index into FRAMES or None when the
# node's document could not be mapped to a frame; None means "exclude",
# never "guess the main frame", so refs can never bind across frames).
DOM_NODES = {
    10: ("BUTTON", {"id": "go", "class": "btn"}, 0),
    11: ("INPUT", {"id": "q", "type": "text"}, 0),
    12: ("BUTTON", {"id": "inner", "class": "btn"}, 1),
    13: ("INPUT", {"id": "frame-input"}, 1),
    14: ("DIV", {"id": "pad"}, 1),
    15: ("SCRIPT", {}, 1),
    16: ("BUTTON", {"id": "lost"}, None),
    17: ("BUTTON", {"id": "main-only"}, 0),
}
# Real Chrome AX trees carry frameId only on the frame root node; every
# other node has frameId "" (verified against a live Chromium, t030).  The
# frame therefore comes from the DOM mapping, never from the AX node.
AX_NODES = [
    {
        "backendDOMNodeId": 10,
        "frameId": "",
        "role": {"value": "button"},
        "name": {"value": "Go"},
    },
    {
        "backendDOMNodeId": 11,
        "frameId": "",
        "role": {"value": "textbox"},
        "name": {"value": "Search"},
    },
    {
        # Deliberately wrong AX frameId: DOM mapping (frame-2) wins.
        "backendDOMNodeId": 12,
        "frameId": "frame-1",
        "role": {"value": "button"},
        "name": {"value": "Inner"},
    },
    {
        "backendDOMNodeId": 99,
        "frameId": "frame-1",
        "role": {"value": "generic"},
        "name": {"value": "Orphan"},
    },
]


def _entries():
    return build_snapshot(
        target_id="t-1",
        frames=FRAMES,
        dom_nodes=DOM_NODES,
        ax_nodes=AX_NODES,
        runtime_instance_id="i1",
    )


def test_snapshot_skips_ax_nodes_without_dom_counterpart() -> None:
    entries = _entries()
    assert [e.ref for e in entries] == ["f0e0", "f0e1", "f1e0", "f1e1", "f1e2"]
    assert entries[0].role == "button"
    assert entries[0].name == "Go"
    assert entries[0].frame_id == "frame-1"
    assert entries[0].loader_id == "loader-1"
    assert entries[0].tag == "BUTTON"
    # The iframe node is namespaced to its own frame even though its AX
    # frameId is wrong: the DOM mapping is authoritative, so no ref can
    # bind across frames.
    assert entries[2].ref == "f1e0"
    assert entries[2].frame_id == "frame-2"
    assert entries[2].name == "Inner"


def test_snapshot_frame_comes_from_dom_not_ax_frame_id() -> None:
    # AX children carry no frameId at all in real Chrome output; the
    # entries above still land in the right frames via the DOM mapping.
    entries = _entries()
    assert entries[0].frame_id == "frame-1"
    assert entries[1].frame_id == "frame-1"
    assert entries[2].frame_id == "frame-2"


def test_snapshot_adds_dom_only_child_frame_elements() -> None:
    # Child-frame DOM nodes without an AX counterpart are still addressable
    # (role/name honestly empty, tag + id/class for identification); the
    # structural SCRIPT, the unmapped-frame node and the main-frame
    # DOM-only node are excluded.
    entries = _entries()
    frame_input = entries[3]
    assert frame_input.ref == "f1e1"
    assert frame_input.role == ""
    assert frame_input.name == ""
    assert frame_input.tag == "INPUT"
    assert frame_input.attrs == {"id": "frame-input"}
    assert frame_input.frame_id == "frame-2"
    assert entries[4].tag == "DIV"
    assert entries[4].attrs == {"id": "pad"}


def test_map_iframe_frames_prefers_url_match() -> None:
    assert map_iframe_frames(["u1", "u2"], ["u2", "u1"]) == [1, 0]


def test_map_iframe_frames_falls_back_to_order_zip() -> None:
    assert map_iframe_frames(["a", "b"], ["x", "y"]) == [0, 1]


def test_map_iframe_frames_leaves_unmapped_as_none() -> None:
    assert map_iframe_frames(["a"], ["x", "y"]) == [None, None]
    # Mixed: first doc matches by URL, the rest zip only on equal counts.
    assert map_iframe_frames(["a", "b"], ["b", "x"]) == [1, 0]


def _validate(entry, **over):
    kwargs = {
        "live_runtime_instance_id": "i1",
        "live_target_ids": ["t-1"],
        "live_frame": {"id": "frame-1", "loaderId": "loader-1"},
        "resolved_signature": entry.signature,
    }
    kwargs.update(over)
    return validate_ref(entry, **kwargs)


def test_valid_ref_passes() -> None:
    _validate(_entries()[0])


def test_runtime_change_is_stale() -> None:
    # The runtime compared is the one recorded ON the entry, not a
    # caller-supplied pair: a state file copied to another runtime fails
    # even when target, frame and signature all still match.
    with pytest.raises(RefStaleError, match="runtime"):
        _validate(_entries()[0], live_runtime_instance_id="i2")


def test_entry_without_runtime_never_validates() -> None:
    # Pre-binding state files carry no runtime on their entries; they
    # must be rejected, not trusted, against any live runtime.
    entry = _entries()[0]
    assert entry.runtime_instance_id == "i1"
    import dataclasses

    unbound = dataclasses.replace(entry, runtime_instance_id="")
    with pytest.raises(RefStaleError, match="runtime"):
        _validate(unbound)


def test_closed_target_is_stale() -> None:
    with pytest.raises(RefStaleError, match="target"):
        _validate(_entries()[0], live_target_ids=["t-other"])


def test_gone_frame_is_stale() -> None:
    with pytest.raises(RefStaleError, match="frame is gone"):
        _validate(_entries()[0], live_frame=None)


def test_navigation_loader_change_is_stale() -> None:
    with pytest.raises(RefStaleError, match="loaderId"):
        _validate(
            _entries()[0],
            live_frame={"id": "frame-1", "loaderId": "loader-2"},
        )


def test_unresolvable_node_is_stale() -> None:
    with pytest.raises(RefStaleError, match="no longer resolves"):
        _validate(_entries()[0], resolved_signature=None)


def test_replaced_node_signature_mismatch_is_stale() -> None:
    with pytest.raises(RefStaleError, match="replaced"):
        _validate(
            _entries()[0],
            resolved_signature=describe_signature("BUTTON", {"id": "other"}),
        )
