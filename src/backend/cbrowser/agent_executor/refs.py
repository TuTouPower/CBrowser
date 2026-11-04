"""Short-lived ref registry for the t030 agent executor.

A ref is only valid inside one runtime, one target, one frame document
(``frameId`` + ``loaderId``) and one node identity (``backendNodeId`` plus a
describe-signature).  Any mismatch is a stale ref: the caller must take a
new snapshot.  Refs are never re-resolved by URL, title, index or node id
reuse, and never cross frames (iframe/OOPIF nodes carry their own frameId).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


class RefStaleError(Exception):
    """A ref failed validation; the caller must snapshot again."""


@dataclass(frozen=True)
class RefEntry:
    ref: str
    target_id: str
    frame_id: str
    loader_id: str
    backend_node_id: int
    signature: str
    role: str
    name: str
    tag: str = ""
    attrs: dict[str, str] = field(default_factory=dict)
    # Runtime that created the ref.  Stored in the state file so a state
    # file copied or re-pointed at another runtime can never validate:
    # entries without a runtime (pre-binding state files) never match a
    # live runtime and are rejected, not trusted.
    runtime_instance_id: str = ""

    def to_dict(self) -> dict:
        """Serialize for the cross-invocation state file (no secrets)."""
        return {
            "ref": self.ref,
            "target_id": self.target_id,
            "frame_id": self.frame_id,
            "loader_id": self.loader_id,
            "backend_node_id": self.backend_node_id,
            "signature": self.signature,
            "role": self.role,
            "name": self.name,
            "tag": self.tag,
            "attrs": dict(self.attrs),
            "runtime_instance_id": self.runtime_instance_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RefEntry":
        """Inverse of :meth:`to_dict`; raises on malformed input."""
        if not isinstance(data, dict):
            raise ValueError("ref entry is not an object")
        return cls(
            ref=str(data["ref"]),
            target_id=str(data["target_id"]),
            frame_id=str(data["frame_id"]),
            loader_id=str(data["loader_id"]),
            backend_node_id=int(data["backend_node_id"]),
            signature=str(data["signature"]),
            role=str(data["role"]),
            name=str(data["name"]),
            tag=str(data.get("tag", "")),
            attrs=dict(data.get("attrs", {})),
            runtime_instance_id=str(data.get("runtime_instance_id", "")),
        )


def describe_signature(node_name: str, attributes: dict[str, str]) -> str:
    """Stable node signature: tag plus sorted attributes."""
    attrs = "|".join(f"{k}={attributes[k]}" for k in sorted(attributes))
    return hashlib.sha256(f"{node_name}|{attrs}".encode()).hexdigest()[:16]


def _display_attrs(attributes: dict[str, str]) -> dict[str, str]:
    """Compact identification attributes for snapshot output."""
    return {k: attributes[k] for k in ("id", "class") if k in attributes}


# DOM node names that are never snapshot entries on their own (document
# structure, not addressable content).
_STRUCTURAL_TAGS = {
    "HTML",
    "HEAD",
    "TITLE",
    "META",
    "LINK",
    "STYLE",
    "SCRIPT",
    "BASE",
}


def map_iframe_frames(
    child_urls: list[str], doc_urls: list[str | None]
) -> list[int | None]:
    """Map iframe documents (DOM walk order) to child frames.

    Returns one child-frame index per document, or None when the document
    cannot be mapped confidently.  URL match wins first; the leftovers zip
    in order only when their counts are equal; anything else stays
    unmapped (excluded from the snapshot) rather than guessed, so a ref
    can never bind to the wrong frame.
    """
    mapped: list[int | None] = [None] * len(doc_urls)
    used: set[int] = set()
    remaining_docs: list[int] = []
    for i, url in enumerate(doc_urls):
        if url is None:
            remaining_docs.append(i)
            continue
        matches = [
            j for j, cu in enumerate(child_urls) if j not in used and cu == url
        ]
        if len(matches) == 1:
            mapped[i] = matches[0]
            used.add(matches[0])
        else:
            remaining_docs.append(i)
    remaining_frames = [j for j in range(len(child_urls)) if j not in used]
    if len(remaining_frames) == len(remaining_docs):
        for i, j in zip(remaining_docs, remaining_frames):
            mapped[i] = j
    return mapped


def build_snapshot(
    *,
    target_id: str,
    frames: list[tuple[str, str]],
    dom_nodes: dict[int, tuple[str, dict[str, str], int | None]],
    ax_nodes: list[dict],
    runtime_instance_id: str = "",
) -> list[RefEntry]:
    """Build compact snapshot entries from frame list + DOM + AX tree.

    ``frames`` is the ``Page.getFrameTree`` traversal order as
    ``(frame_id, loader_id)`` pairs; refs are namespaced per frame
    (``f<frame_index>e<seq>``) so iframe/OOPIF nodes can never resolve
    into another frame.  ``dom_nodes`` maps backendNodeId ->
    (nodeName, attributes, frame index or None when unmapped).

    The frame of an entry comes from the DOM mapping, never from the AX
    node's ``frameId``: real Chrome AX trees carry ``frameId`` only on the
    frame root node, so trusting it drops every other node.  Child-frame
    DOM elements without an AX counterpart are still addressable (empty
    role/name, tag + id/class for identification); main-frame DOM-only
    nodes are not added (the AX tree covers the main frame) and
    structural nodes never are.
    """
    loader_by_frame = dict(frames)
    entries: list[RefEntry] = []
    seq: dict[int, int] = {}

    def _next(fi: int) -> str:
        n = seq.get(fi, 0)
        seq[fi] = n + 1
        return f"f{fi}e{n}"

    ax_backends: set[int] = set()
    for node in ax_nodes:
        backend_id = node.get("backendDOMNodeId")
        if not isinstance(backend_id, int):
            continue
        dom = dom_nodes.get(backend_id)
        if dom is None:
            continue
        node_name, attributes, fi = dom
        if fi is None:
            continue
        ax_backends.add(backend_id)
        frame_id, loader_id = frames[fi]
        entries.append(
            RefEntry(
                ref=_next(fi),
                target_id=target_id,
                frame_id=frame_id,
                loader_id=loader_id,
                backend_node_id=backend_id,
                signature=describe_signature(node_name, attributes),
                role=str(node.get("role", {}).get("value", "")),
                name=str(node.get("name", {}).get("value", "")),
                tag=node_name,
                attrs=_display_attrs(attributes),
                runtime_instance_id=runtime_instance_id,
            )
        )
    for backend_id, (node_name, attributes, fi) in dom_nodes.items():
        if fi is None or fi == 0 or backend_id in ax_backends:
            continue
        if node_name.startswith("#") or node_name in _STRUCTURAL_TAGS:
            continue
        frame_id, loader_id = frames[fi]
        entries.append(
            RefEntry(
                ref=_next(fi),
                target_id=target_id,
                frame_id=frame_id,
                loader_id=loader_id,
                backend_node_id=backend_id,
                signature=describe_signature(node_name, attributes),
                role="",
                name="",
                tag=node_name,
                attrs=_display_attrs(attributes),
                runtime_instance_id=runtime_instance_id,
            )
        )
    return entries


def validate_ref(
    entry: RefEntry,
    *,
    live_runtime_instance_id: str,
    live_target_ids: list[str],
    live_frame: dict | None,
    resolved_signature: str | None,
) -> None:
    """Validate a ref against freshly fetched live state.

    Raises :class:`RefStaleError` with a specific reason on any mismatch.
    ``live_frame`` is ``{"id": ..., "loaderId": ...}`` for the entry's
    frame, or None when the frame is gone.  ``resolved_signature`` is the
    describe-signature of the node the backendNodeId resolves to now, or
    None when it no longer resolves.

    The runtime check compares the runtime recorded on the entry itself
    against the live runtime supplied by the caller (the CLI's
    ``--runtime-instance`` for this invocation, never a value read back
    from the state file): a state file copied across runtimes fails
    here even when target, frame and signature all still match.
    """
    if entry.runtime_instance_id != live_runtime_instance_id:
        raise RefStaleError("runtime_instance_id changed; snapshot again")
    if entry.target_id not in live_target_ids:
        raise RefStaleError("target is closed or gone; snapshot again")
    if live_frame is None:
        raise RefStaleError("frame is gone; snapshot again")
    if str(live_frame.get("id", "")) != entry.frame_id:
        raise RefStaleError("frame id changed; snapshot again")
    if str(live_frame.get("loaderId", "")) != entry.loader_id:
        raise RefStaleError(
            "frame navigated (loaderId changed); snapshot again"
        )
    if resolved_signature is None:
        raise RefStaleError("node no longer resolves; snapshot again")
    if resolved_signature != entry.signature:
        raise RefStaleError(
            "node was replaced (signature changed); snapshot again"
        )
