"""Executor session: one CLI run over one authenticated CDP tunnel.

Transport is raw CDP over the automation websocket (no Playwright in the
production path: Playwright does not expose targetId, which is the
identity primitive for adopt, ledger and ref validation).  Trusted input
goes through the CDP Input domain only (t029 adopted input path); no
synthetic-event fallback, no global probe variables.

Dialog listeners are attached at attach time, before any action on the
page, and dialog answers travel on their own command ids, so a pending
trigger command can never block its own dialog answer (p032).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urlsplit

import httpx
from cbrowser.shared.error_response import parse_error_response

from .dialogs import DialogRecord, DialogTracker, permission_needs_human_payload
from .ledger import PageLedger, PageRecord
from .refs import (
    RefEntry,
    RefStaleError,
    build_snapshot,
    map_iframe_frames,
    validate_ref,
)
from .transport import CdpClient, CdpError, CdpTimeoutError


class SessionError(CdpError):
    """Executor session failure with a stable CLI error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = code


def _walk_dom_tree(
    node: dict,
    out: dict[int, tuple[str, dict[str, str], int]],
    slot: int,
    iframe_docs: list[tuple[int, str | None]],
) -> None:
    """Walk a pierced DOM tree, tagging every node with its document slot.

    Slot 0 is the main document; each iframe ``contentDocument`` gets a
    fresh slot in walk order, recorded in ``iframe_docs`` as
    ``(slot, documentURL)`` so the caller can map slots to frames.
    """
    backend_id = node.get("backendNodeId")
    if isinstance(backend_id, int):
        attrs_list = node.get("attributes", [])
        attrs = {
            attrs_list[i]: attrs_list[i + 1]
            for i in range(0, len(attrs_list) - 1, 2)
        }
        out[backend_id] = (str(node.get("nodeName", "")), attrs, slot)
    for child in node.get("children", []) or []:
        _walk_dom_tree(child, out, slot, iframe_docs)
    content = node.get("contentDocument")
    if isinstance(content, dict):
        doc_slot = len(iframe_docs) + 1
        iframe_docs.append((doc_slot, content.get("documentURL")))
        _walk_dom_tree(content, out, doc_slot, iframe_docs)


def _walk_frame_tree(node: dict, out: list[tuple[str, str]]) -> None:
    frame = node.get("frame", {})
    out.append((str(frame.get("id", "")), str(frame.get("loaderId", ""))))
    for child in node.get("childFrames", []) or []:
        _walk_frame_tree(child, out)


def _walk_frame_urls(node: dict, out: list[str]) -> None:
    frame = node.get("frame", {})
    out.append(str(frame.get("url", "")))
    for child in node.get("childFrames", []) or []:
        _walk_frame_urls(child, out)


def _find_frame(node: dict, frame_id: str) -> dict | None:
    frame = node.get("frame", {})
    if str(frame.get("id", "")) == frame_id:
        return {"id": frame_id, "loaderId": str(frame.get("loaderId", ""))}
    for child in node.get("childFrames", []) or []:
        found = _find_frame(child, frame_id)
        if found is not None:
            return found
    return None


class ExecutorSession:
    def __init__(
        self,
        endpoint: str,
        token: str,
        profile_id: str,
        runtime_instance_id: str,
        step_timeout: float = 30.0,
        initial_snapshots: dict[str, dict[str, RefEntry]] | None = None,
        initial_ledger: dict[str, PageRecord] | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.token = token
        self.profile_id = profile_id
        self.runtime_instance_id = runtime_instance_id
        self.step_timeout = step_timeout
        self.session_id = f"exec-{int(time.time() * 1000)}"
        self._control_generation: int | None = None
        self.ledger = PageLedger(profile_id, runtime_instance_id)
        self.dialogs = DialogTracker()
        self._client = CdpClient(
            endpoint, headers={"Authorization": f"Bearer {token}"}
        )
        self._target_sessions: dict[str, str] = {}  # target_id -> sessionId
        self._session_targets: dict[str, str] = {}  # sessionId -> target_id
        self._snapshots: dict[str, dict[str, RefEntry]] = {}
        self._attach_tasks: set[asyncio.Task] = set()
        # State restored from a previous invocation of the same session
        # (same profile + runtime-instance); applied at start() once the
        # live target set is known, so only live targets are restored.
        self._initial_snapshots = initial_snapshots or {}
        self._initial_ledger = initial_ledger or {}

    def export_state(self) -> tuple[dict[str, dict[str, dict]], dict[str, dict]]:
        """Serialize snapshots + ledger for the state file (no secrets)."""
        snapshots = {
            target_id: {ref: entry.to_dict() for ref, entry in refs.items()}
            for target_id, refs in self._snapshots.items()
        }
        ledger = {
            record.target_id: {
                "origin": record.origin,
                "manageable": record.manageable,
                "cleanable": record.cleanable,
                "opener_id": record.opener_id,
            }
            for record in self.ledger.all()
        }
        return snapshots, ledger

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        try:
            await self._client.connect()
        except Exception as exc:  # noqa: BLE001 - connect failure is a stable CLI error
            close_code = getattr(getattr(exc, "rcvd", None), "code", None)
            if close_code == 4403:
                raise SessionError(
                    "control_revoked",
                    "control was taken over; an explicit human restore "
                    "is required before this agent may connect again",
                ) from None
            raise SessionError(
                "connection_failed", f"cannot connect to automation endpoint: {exc}"
            ) from None
        self._client.on_event(self._handle_event)
        try:
            # Baseline FIRST: enabling discovery replays targetCreated
            # for pre-existing targets, and those must stay "user", not
            # fall through to the mid-session "unknown" path.
            targets = await self._client.send("Target.getTargets")
        except CdpError as exc:
            raise SessionError("connection_failed", str(exc)) from None
        page_ids = [
            str(t.get("targetId", ""))
            for t in targets.get("targetInfos", [])
            if t.get("type") == "page"
        ]
        self.ledger.baseline(page_ids)
        # Resume the previous invocation's session: persisted ledger
        # records win over the baseline for live targets (otherwise an
        # agent page created by an earlier call would look like a user
        # page), and persisted snapshots are kept for live targets only.
        # Restored pages sort by saved order (monotonic offsets), so the
        # last-tab guard keeps a stable newest page.
        live = set(page_ids)
        restore_base = time.monotonic()
        for index, (target_id, record) in enumerate(
            self._initial_ledger.items()
        ):
            if target_id in live:
                record.created_at = restore_base + index * 0.001
                self.ledger.restore(record)
        for target_id, refs in self._initial_snapshots.items():
            if target_id in live:
                self._snapshots[target_id] = dict(refs)
        try:
            await self._client.send("Target.setDiscoverTargets", {"discover": True})
        except CdpError as exc:
            raise SessionError("connection_failed", str(exc)) from None

    async def close(self) -> None:
        """Safe disconnect: detach sessions, never close pages or browser."""
        for target_id, session_id in list(self._target_sessions.items()):
            try:
                await self._client.send(
                    "Target.detachFromTarget", {"sessionId": session_id}
                )
            except Exception:  # noqa: BLE001 - best-effort detach
                pass
        self._target_sessions.clear()
        self._session_targets.clear()
        await self._client.close()

    # -- events ---------------------------------------------------------------

    def _handle_event(self, msg: dict) -> None:
        method = msg.get("method", "")
        params = msg.get("params", {}) or {}
        if method == "Target.targetCreated":
            info = params.get("targetInfo", {}) or {}
            target_id = str(info.get("targetId", ""))
            if info.get("type") != "page" or not target_id:
                return
            record = self.ledger.record_observed(
                target_id, opener_id=info.get("openerId")
            )
            if record.origin == "agent":
                task = asyncio.create_task(self._attach_safe(target_id))
                self._attach_tasks.add(task)
                task.add_done_callback(self._attach_tasks.discard)
        elif method == "Target.targetDestroyed":
            target_id = str(params.get("targetId", ""))
            self.ledger.record_closed(target_id)
            session_id = self._target_sessions.pop(target_id, None)
            if session_id is not None:
                self._session_targets.pop(session_id, None)
            self._snapshots.pop(target_id, None)
        elif method == "Page.javascriptDialogOpening":
            session_id = msg.get("sessionId")
            target_id = self._session_targets.get(session_id) if session_id else None
            if target_id is None:
                return
            self.dialogs.record_opening(
                DialogRecord(
                    target_id=target_id,
                    dialog_type=str(params.get("type", "")),
                    message=str(params.get("message", "")),
                    url=str(params.get("url", "")),
                    has_browser_handler=bool(params.get("hasBrowserHandler", False)),
                )
            )
        elif method == "Page.javascriptDialogClosed":
            session_id = msg.get("sessionId")
            target_id = self._session_targets.get(session_id) if session_id else None
            if target_id is not None:
                self.dialogs.record_closed(target_id)

    async def _attach_safe(self, target_id: str) -> None:
        try:
            await self.attach(target_id)
        except Exception:  # noqa: BLE001 - auto-attach is best-effort; explicit steps re-attach
            pass

    # -- target sessions --------------------------------------------------------

    async def attach(self, target_id: str) -> str:
        if target_id in self._target_sessions:
            return self._target_sessions[target_id]
        result = await self._client.send(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
            timeout=self.step_timeout,
        )
        session_id = str(result.get("sessionId", ""))
        if not session_id:
            raise SessionError("target_not_found", f"cannot attach to {target_id}")
        self._target_sessions[target_id] = session_id
        self._session_targets[session_id] = target_id
        for method in ("Page.enable", "Runtime.enable", "DOM.enable"):
            await self._client.send(
                method, session_id=session_id, timeout=self.step_timeout
            )
        return session_id

    async def _live_page_ids(self) -> list[str]:
        targets = await self._client.send(
            "Target.getTargets", timeout=self.step_timeout
        )
        return [
            str(t.get("targetId", ""))
            for t in targets.get("targetInfos", [])
            if t.get("type") == "page"
        ]

    # -- steps ------------------------------------------------------------------

    async def list_targets(self) -> list[dict]:
        return [
            {
                "target_id": r.target_id,
                "origin": r.origin,
                "manageable": r.manageable,
                "cleanable": r.cleanable,
            }
            for r in self.ledger.all()
        ]

    async def new_page(self, url: str | None = None) -> dict:
        params: dict[str, Any] = {}
        if url:
            params["url"] = url
        result = await self._client.send(
            "Target.createTarget", params, timeout=self.step_timeout
        )
        target_id = str(result.get("targetId", ""))
        if not target_id:
            raise SessionError("target_not_found", "Target.createTarget gave no id")
        self.ledger.record_created(target_id)
        await self.attach(target_id)
        return {"target_id": target_id}

    async def adopt(self, target_id: str) -> dict:
        live = await self._live_page_ids()
        if target_id not in live:
            raise SessionError("target_not_found", f"target {target_id} not live")
        record = self.ledger.adopt(target_id)
        if target_id not in self._target_sessions:
            # t031: when the attendant holds a dialog on this page,
            # attaching would hang Page.enable behind the modal dialog
            # (chain evidence). Skip the attach: the page is still
            # adopted for dialog operations, which resolve through the
            # attendant peek path instead of this session.
            dialogs = await self._attendant_dialogs()
            if dialogs and any(
                d.get("target_id") == target_id for d in dialogs
            ):
                return {
                    "target_id": target_id,
                    "origin": record.origin,
                    "manageable": record.manageable,
                    "cleanable": record.cleanable,
                }
        await self.attach(target_id)
        return {
            "target_id": target_id,
            "origin": record.origin,
            "manageable": record.manageable,
            "cleanable": record.cleanable,
        }

    async def snapshot(self, target_id: str) -> dict:
        session_id = await self.attach(target_id)
        frame_tree = await self._client.send(
            "Page.getFrameTree", session_id=session_id, timeout=self.step_timeout
        )
        frames: list[tuple[str, str]] = []
        _walk_frame_tree(frame_tree.get("frameTree", {}), frames)
        frame_urls: list[str] = []
        _walk_frame_urls(frame_tree.get("frameTree", {}), frame_urls)
        dom = await self._client.send(
            "DOM.getDocument",
            {"depth": -1, "pierce": True},
            session_id=session_id,
            timeout=self.step_timeout,
        )
        dom_slots: dict[int, tuple[str, dict[str, str], int]] = {}
        iframe_docs: list[tuple[int, str | None]] = []
        _walk_dom_tree(dom.get("root", {}), dom_slots, 0, iframe_docs)
        # Map iframe document slots to child frames (URL match, else order
        # zip); unmapped slots stay None and their nodes are excluded from
        # the snapshot rather than guessed into a frame.
        mapping = map_iframe_frames(
            frame_urls[1:], [url for _, url in iframe_docs]
        )
        slot_to_frame: dict[int, int | None] = {0: 0}
        for (slot, _), mapped in zip(iframe_docs, mapping):
            slot_to_frame[slot] = mapped + 1 if mapped is not None else None
        dom_nodes: dict[int, tuple[str, dict[str, str], int | None]] = {
            backend: (name, attrs, slot_to_frame[slot])
            for backend, (name, attrs, slot) in dom_slots.items()
        }
        ax = await self._client.send(
            "Accessibility.getFullAXTree",
            session_id=session_id,
            timeout=self.step_timeout,
        )
        entries = build_snapshot(
            target_id=target_id,
            frames=frames,
            dom_nodes=dom_nodes,
            ax_nodes=ax.get("nodes", []),
            runtime_instance_id=self.runtime_instance_id,
        )
        self._snapshots[target_id] = {e.ref: e for e in entries}
        return {
            "target_id": target_id,
            "nodes": [
                {
                    "ref": e.ref,
                    "role": e.role,
                    "name": e.name,
                    "frame_id": e.frame_id,
                    "tag": e.tag,
                    "attrs": e.attrs,
                }
                for e in entries
            ],
        }

    async def _validated_entry(self, target_id: str, ref: str) -> RefEntry:
        snapshot = self._snapshots.get(target_id, {})
        entry = snapshot.get(ref)
        if entry is None:
            raise SessionError(
                "ref_stale", f"ref {ref} not in latest snapshot for {target_id}"
            )
        session_id = await self.attach(target_id)
        try:
            live_ids = await self._live_page_ids()
            frame_tree = await self._client.send(
                "Page.getFrameTree",
                session_id=session_id,
                timeout=self.step_timeout,
            )
            live_frame = _find_frame(
                frame_tree.get("frameTree", {}), entry.frame_id
            )
            resolved = await self._client.send(
                "DOM.resolveNode",
                {"backendNodeId": entry.backend_node_id},
                session_id=session_id,
                timeout=self.step_timeout,
            )
            object_id = ((resolved.get("object") or {}).get("objectId"))
            signature = None
            if object_id:
                # A replaced node still resolves and (when cloned) keeps an
                # identical tag+attributes signature, so resolve+describe
                # alone cannot tell it apart.  isConnected is the decisive
                # liveness signal: a detached node is a stale ref even
                # when its signature matches.
                connected = await self._client.send(
                    "Runtime.callFunctionOn",
                    {
                        "objectId": object_id,
                        "functionDeclaration": (
                            "function() { return this.isConnected; }"
                        ),
                        "returnByValue": True,
                    },
                    session_id=session_id,
                    timeout=self.step_timeout,
                )
                if connected.get("result", {}).get("value") is False:
                    raise SessionError(
                        "ref_stale",
                        "node is detached from document; snapshot again",
                    )
            if object_id:
                described = await self._client.send(
                    "DOM.describeNode",
                    {"objectId": object_id},
                    session_id=session_id,
                    timeout=self.step_timeout,
                )
                node = described.get("node", {}) or {}
                attrs_list = node.get("attributes", [])
                attrs = {
                    attrs_list[i]: attrs_list[i + 1]
                    for i in range(0, len(attrs_list) - 1, 2)
                }
                from .refs import describe_signature

                signature = describe_signature(str(node.get("nodeName", "")), attrs)
        except CdpError as exc:
            raise SessionError("ref_stale", f"ref validation failed: {exc}") from None
        try:
            validate_ref(
                entry,
                live_runtime_instance_id=self.runtime_instance_id,
                live_target_ids=live_ids,
                live_frame=live_frame,
                resolved_signature=signature,
            )
        except RefStaleError as exc:
            raise SessionError("ref_stale", str(exc)) from None
        return entry

    async def click(self, target_id: str, ref: str) -> dict:
        entry = await self._validated_entry(target_id, ref)
        session_id = await self.attach(target_id)
        resolved = await self._client.send(
            "DOM.resolveNode",
            {"backendNodeId": entry.backend_node_id},
            session_id=session_id,
            timeout=self.step_timeout,
        )
        object_id = (resolved.get("object") or {}).get("objectId")
        if not object_id:
            raise SessionError("ref_stale", "node no longer resolves")
        try:
            await self._client.send(
                "DOM.scrollIntoViewIfNeeded",
                {"objectId": object_id},
                session_id=session_id,
                timeout=self.step_timeout,
            )
        except CdpError as exc:
            # A node detached between validation and action is stale,
            # not a protocol failure.
            if "detached" in str(exc):
                raise SessionError(
                    "ref_stale",
                    "node is detached from document; snapshot again",
                ) from None
            raise
        quads = await self._client.send(
            "DOM.getContentQuads",
            {"objectId": object_id},
            session_id=session_id,
            timeout=self.step_timeout,
        )
        quad = (quads.get("quads") or [None])[0]
        if not quad or len(quad) < 8:
            raise SessionError("ref_stale", "node has no content quad")
        x = sum(quad[0::2]) / 4
        y = sum(quad[1::2]) / 4
        # Open the popup attribution window before the input lands, so a
        # popup opened by this click is attributable to this session.
        self.ledger.expect_popup([target_id])
        for kind in ("mousePressed", "mouseReleased"):
            dialog = await self._dispatch_mouse_event(
                session_id, kind, x, y, target_id
            )
            if dialog is not None:
                # The press/release opened a modal dialog: the renderer
                # is blocked until it is answered, so the click returns
                # now with the dialog surfaced; the caller answers it
                # with dialog_answer (which unblocks the pending dispatch,
                # whose late response is dropped).  The click never
                # answers anything itself.
                #
                # When the dialog opened on mousePressed, mouseReleased
                # was never sent: the press is uncompleted and the click
                # did not happen.  Report that explicitly instead of
                # letting the caller assume a complete click.
                result: dict[str, Any] = {"x": x, "y": y, "dialog": dialog}
                if kind == "mousePressed":
                    result["release_skipped"] = True
                return result
        return {"x": x, "y": y}

    async def _dispatch_mouse_event(
        self,
        session_id: str,
        kind: str,
        x: float,
        y: float,
        target_id: str,
    ) -> dict | None:
        """Dispatch one mouse event, returning early if it opens a dialog.

        A modal dialog blocks the renderer, so the dispatch response
        never arrives until the dialog is answered.  Awaiting the full
        step timeout would deadlock the program: the answer step runs
        after click, but click would never return.  Poll the dialog
        tracker while waiting instead; on a dialog, drop the pending
        command and return the dialog at once.  Returns None when the
        dispatch completed normally.
        """
        key, fut = await self._client.send_request(
            "Input.dispatchMouseEvent",
            {
                "type": kind,
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1,
            },
            session_id,
        )
        deadline = time.monotonic() + self.step_timeout
        while True:
            record = self.dialogs.open_for(target_id)
            if record is not None:
                self._client.drop_pending(key)
                return {"type": record.dialog_type, "message": record.message}
            if fut.done():
                error = self._client.response_error(fut.result())
                if error is not None:
                    raise error
                return None
            if time.monotonic() >= deadline:
                self._client.drop_pending(key)
                raise CdpTimeoutError(
                    f"CDP command Input.dispatchMouseEvent timed out "
                    f"after {self.step_timeout}s"
                )
            await asyncio.sleep(0.05)

    async def input_text(self, target_id: str, ref: str, text: str) -> dict:
        entry = await self._validated_entry(target_id, ref)
        session_id = await self.attach(target_id)
        await self._client.send(
            "DOM.focus",
            {"backendNodeId": entry.backend_node_id},
            session_id=session_id,
            timeout=self.step_timeout,
        )
        await self._client.send(
            "Input.insertText",
            {"text": text},
            session_id=session_id,
            timeout=self.step_timeout,
        )
        return {}

    async def navigate(self, target_id: str, url: str) -> dict:
        session_id = await self.attach(target_id)
        await self._client.send(
            "Page.navigate",
            {"url": url},
            session_id=session_id,
            timeout=self.step_timeout,
        )
        return {}

    async def wait_for(
        self, target_id: str, expression: str, timeout_ms: int
    ) -> dict:
        session_id = await self.attach(target_id)
        deadline = time.monotonic() + timeout_ms / 1000.0
        while True:
            result = await self._client.send(
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "returnByValue": True,
                    "awaitPromise": True,
                },
                session_id=session_id,
                timeout=self.step_timeout,
            )
            value = (result.get("result") or {}).get("value")
            if value:
                return {"value": value}
            if time.monotonic() >= deadline:
                raise SessionError(
                    "step_timeout",
                    f"wait_for expression not truthy within {timeout_ms}ms",
                )
            await asyncio.sleep(0.2)

    async def extract(self, target_id: str, expression: str) -> dict:
        session_id = await self.attach(target_id)
        result = await self._client.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
            session_id=session_id,
            timeout=self.step_timeout,
        )
        if "exceptionDetails" in result:
            detail = result["exceptionDetails"] or {}
            text = ((detail.get("exception") or {}).get("description")) or "evaluate failed"
            raise SessionError("cdp_error", f"evaluate failed: {text}")
        return {"value": (result.get("result") or {}).get("value")}

    async def dialog_answer(
        self,
        target_id: str,
        answer: str | None = None,
        prompt_text: str | None = None,
    ) -> dict:
        if target_id not in self._target_sessions:
            # t031: a session attached AFTER a dialog opened cannot
            # answer it (Chrome: "No dialog is showing"; Page.enable
            # hangs behind the modal dialog). A dialog held by the
            # resident attendant is answered on the attendant's own
            # session instead; anything else falls through to the
            # normal attach path below.
            dialogs = await self._attendant_dialogs()
            if dialogs:
                for held in dialogs:
                    if held.get("target_id") != target_id:
                        continue
                    if answer is not None and answer not in (
                        "accept",
                        "dismiss",
                    ):
                        raise SessionError(
                            "invalid_program",
                            f"invalid dialog answer: {answer!r}",
                        )
                    if answer is not None:
                        accept = answer == "accept"
                    else:
                        # Conservative default, mirroring
                        # dialogs.default_action.
                        accept = held.get("type") == "alert"
                    answered = await self._answer_attendant_dialog(
                        target_id, accept, prompt_text
                    )
                    if answered is not None:
                        return {
                            "action": answered.get(
                                "action",
                                "accept" if accept else "dismiss",
                            )
                        }
                    break
        session_id = await self.attach(target_id)
        try:
            action, text = self.dialogs.decide(target_id, answer, prompt_text)
        except KeyError:
            raise SessionError(
                "dialog_not_open", f"no dialog open on target {target_id}"
            ) from None
        except ValueError as exc:
            raise SessionError("invalid_program", str(exc)) from None
        params: dict[str, Any] = {"accept": action == "accept"}
        if text is not None:
            params["promptText"] = text
        await self._client.send(
            "Page.handleJavaScriptDialog",
            params,
            session_id=session_id,
            timeout=self.step_timeout,
        )
        self.dialogs.record_closed(target_id)
        return {"action": action}

    async def dialog_wait(self, target_id: str, timeout_ms: int) -> dict:
        if target_id not in self._target_sessions:
            # t031: attaching first would hang Page.enable behind an
            # already-open modal dialog, so a held dialog is observed
            # through the attendant peek instead of the session path.
            dialogs = await self._attendant_dialogs()
            if dialogs:
                for held in dialogs:
                    if held.get("target_id") == target_id:
                        return {
                            "type": held.get("type", ""),
                            "message": held.get("message", ""),
                        }
        # Attach first, like dialog_answer: without Page enabled on the
        # target, opening events never reach the tracker and the wait
        # would always time out even while a dialog is open.
        await self.attach(target_id)
        deadline = time.monotonic() + timeout_ms / 1000.0
        while True:
            record = self.dialogs.open_for(target_id)
            if record is not None:
                return {
                    "type": record.dialog_type,
                    "message": record.message,
                }
            if time.monotonic() >= deadline:
                raise SessionError(
                    "dialog_timeout",
                    f"no dialog opened on {target_id} within {timeout_ms}ms",
                )
            await asyncio.sleep(0.05)

    async def set_input_files(
        self, target_id: str, ref: str, files: list[str]
    ) -> dict:
        entry = await self._validated_entry(target_id, ref)
        session_id = await self.attach(target_id)
        # pushNodesByBackendIdsToFrontend requires the document to have
        # been requested on THIS session first; a snapshot taken in an
        # earlier invocation used a different session, so request it
        # here (depth 0: only the document node itself is needed).
        await self._client.send(
            "DOM.getDocument",
            {"depth": 0},
            session_id=session_id,
            timeout=self.step_timeout,
        )
        pushed = await self._client.send(
            "DOM.pushNodesByBackendIdsToFrontend",
            {"backendNodeIds": [entry.backend_node_id]},
            session_id=session_id,
            timeout=self.step_timeout,
        )
        node_ids = pushed.get("nodeIds", [])
        if not node_ids:
            raise SessionError("ref_stale", "node has no frontend id")
        await self._client.send(
            "DOM.setFileInputFiles",
            {"nodeId": node_ids[0], "files": files},
            session_id=session_id,
            timeout=self.step_timeout,
        )
        return {}

    async def permission(self, target_id: str, kind: str) -> dict:
        return permission_needs_human_payload(
            profile_id=self.profile_id,
            runtime_instance_id=self.runtime_instance_id,
            target_id=target_id,
            kind=kind,
            session_id=self.session_id,
        )

    # ---- t031 human-priority control (ADR 019) ----

    @property
    def control_api_base(self) -> str:
        """API origin derived from the automation WS endpoint.

        The CLI takes no separate API URL: the tunnel endpoint is
        same-origin with the API, so ws(s)://host/path maps to
        http(s)://host. The token is never logged (callers redact).
        """
        parts = urlsplit(self.endpoint)
        scheme = "https" if parts.scheme == "wss" else "http"
        return f"{scheme}://{parts.netloc}"

    async def _control_post(self, action: str, payload: dict) -> dict:
        url = (
            f"{self.control_api_base}/api/v1/profiles/{self.profile_id}"
            f"/control/{action}"
        )
        try:
            async with httpx.AsyncClient(
                timeout=self.step_timeout, trust_env=False
            ) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.token}"},
                )
        except Exception as exc:  # noqa: BLE001 - transport failure is a CLI error
            raise SessionError(
                "control_request_failed",
                f"control {action} request failed: {type(exc).__name__}",
            ) from None
        if resp.status_code == 409:
            # Unified ErrorResponse (t056 A15, strict since t069): the
            # refusal code is the top-level `error`. Any other shape —
            # a legacy `detail` body, missing fields, a non-JSON body —
            # is a protocol error, never a parsed refusal and never a
            # silently assumed `control_conflict`.
            try:
                body = resp.json()
            except Exception:  # noqa: BLE001 - non-JSON body is non-conforming
                body = None
            parsed = parse_error_response(body)
            if parsed is None:
                raise SessionError(
                    "control_protocol_error",
                    f"control {action} refused with a non-conforming "
                    "error response (HTTP 409)",
                )
            raise SessionError(
                "control_conflict",
                f"control {action} refused: {parsed.error}",
            )
        if resp.status_code != 200:
            raise SessionError(
                "control_request_failed",
                f"control {action} failed: HTTP {resp.status_code}",
            )
        data = resp.json()
        generation = data.get("generation")
        if isinstance(generation, int):
            # Stale-response fence (AC-005): never let an older control
            # state overwrite a newer one this session already knows.
            if (
                self._control_generation is not None
                and generation < self._control_generation
            ):
                raise SessionError(
                    "control_stale_generation",
                    f"control {action} response is stale "
                    f"(generation {generation} < {self._control_generation})",
                )
            self._control_generation = generation
        return data

    async def control_claim(self) -> dict:
        """Explicitly claim control for this session's identity."""
        return await self._control_post(
            "claim", {"agent_session_id": self.session_id}
        )

    async def _attendant_dialogs(self) -> list[dict] | None:
        """Peek dialogs held by the resident attendant (t031).

        Returns None when the endpoint is unreachable or malformed;
        callers fall back to the normal session path in that case.
        """
        url = (
            f"{self.control_api_base}/api/v1/profiles/{self.profile_id}"
            "/control/dialogs"
        )
        try:
            async with httpx.AsyncClient(
                timeout=self.step_timeout, trust_env=False
            ) as client:
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {self.token}"},
                )
        except Exception:  # noqa: BLE001 - peek failure degrades to normal path
            return None
        if resp.status_code != 200:
            return None
        try:
            dialogs = resp.json().get("dialogs")
        except ValueError:
            return None
        return dialogs if isinstance(dialogs, list) else None

    async def _answer_attendant_dialog(
        self,
        target_id: str,
        accept: bool,
        prompt_text: str | None = None,
    ) -> dict | None:
        """Answer a held dialog on the attendant's session (t031)."""
        url = (
            f"{self.control_api_base}/api/v1/profiles/{self.profile_id}"
            "/control/dialog-answer"
        )
        payload: dict[str, Any] = {"target_id": target_id, "accept": accept}
        if prompt_text is not None:
            payload["prompt_text"] = prompt_text
        try:
            async with httpx.AsyncClient(
                timeout=self.step_timeout, trust_env=False
            ) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.token}"},
                )
        except Exception:  # noqa: BLE001 - answer failure degrades to normal path
            return None
        if resp.status_code != 200:
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    async def control_handoff(
        self, reason: str, detail: str | None = None
    ) -> dict:
        """Hand control back to the user (permission/captcha/2FA/handoff).

        The harness pattern is: permission returns needs-human, then
        the harness issues control_handoff. The session itself never
        auto-hands-off on a permission probe: the harness decides.
        """
        if reason not in (
            "cli_handoff",
            "permission",
            "captcha",
            "two_fa",
            "agent_finish",
        ):
            raise SessionError(
                "invalid_program", f"unknown control handoff reason: {reason!r}"
            )
        payload: dict[str, Any] = {
            "reason": reason,
            "agent_session_id": self.session_id,
        }
        if detail:
            payload["detail"] = detail
        return await self._control_post("handoff", payload)

    async def control_release(self) -> dict:
        """Best-effort end-of-session release (reason agent_finish).

        Never raises: cleanup paths must not fail on control release.
        Control release is explicit: process exit alone does not
        release control (the session persists via the state file), and
        a human takeover always preempts regardless of release.
        """
        try:
            return await self.control_handoff("agent_finish")
        except Exception:  # noqa: BLE001 - best-effort release
            return {"released": False}

    async def wait_for_target_count(self, count: int, timeout_ms: int) -> dict:
        """Wait until at least ``count`` live page targets exist."""
        deadline = time.monotonic() + timeout_ms / 1000.0
        while True:
            live = await self._live_page_ids()
            if len(live) >= count:
                return {"count": len(live), "targets": live}
            if time.monotonic() >= deadline:
                raise SessionError(
                    "step_timeout",
                    f"only {len(live)} page targets after {timeout_ms}ms",
                )
            await asyncio.sleep(0.2)

    async def cleanup(self) -> dict:
        live = await self._live_page_ids()
        closable, refused = self.ledger.cleanup_plan(live)
        closed: list[str] = []
        for target_id in closable:
            await self._client.send(
                "Target.closeTarget",
                {"targetId": target_id},
                timeout=self.step_timeout,
            )
            self.ledger.record_closed(target_id)
            closed.append(target_id)
        return {"closed": closed, "refused": refused}
