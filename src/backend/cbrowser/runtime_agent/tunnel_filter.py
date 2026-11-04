"""Mediation filter for external-client CDP traffic at the Agent UDS tunnel.

t030 replaces the tunnel's previous transparent forwarding for the t029
``MUST_MEDIATE_METHODS`` list.  The filter is pure logic (no I/O) so it can
be unit-tested without a browser:

* ``Browser.close`` is always rejected: no external client may stop the
  Profile through the tunnel.  Lifecycle close stays available on the
  Agent's own ``/control`` path, which external clients cannot reach.
* ``Target.closeTarget`` / ``Page.close`` are NOT ownership-filtered at
  the tunnel: measured 2026-11-04, Playwright's ``popup.close()`` for a
  click-opened popup sends ``Target.closeTarget`` for a target the
  connection did not create, and rejecting it hangs the client waiting
  for a close that never comes.  Tab-close authorization is enforced by
  the executor's ledger (only cleanable targets), not the tunnel.  The
  tunnel keeps one backstop: when its observed page set has exactly one
  entry, closing it is rejected as ``last_tab_protected`` (closing the
  last tab can stop the browser).  When the tunnel cannot observe the
  page set it forwards, and the executor ledger remains authoritative.
* Download-behavior and emulation overrides are rejected: during an
  automation session they would bypass Agent Artifact capture or fight the
  Profile configuration.
* ``Page.addScriptToEvaluateOnNewDocument`` is registered per session and
  removed on disconnect instead of flat-rejected: Playwright's
  connect_over_cdp utility injection uses it, so flat rejection would break
  the executor's own transport.  Registration plus disconnect cleanup
  achieves "no script survives the session" without breaking the transport.

A rejection is a stable CDP error carrying the request's ``id`` and
``sessionId`` (when present); an id-less destructive command cannot be
answered, so it is dropped instead of forwarded.
"""

from __future__ import annotations

from typing import Any

_REJECT_ALWAYS = {
    "Browser.close",
    "Browser.setDownloadBehavior",
    "Page.setDownloadBehavior",
    "Emulation.setUserAgentOverride",
    "Emulation.setDeviceMetricsOverride",
    "Emulation.setGeolocationOverride",
    "Emulation.setTouchEmulationEnabled",
    "Emulation.setFocusEmulationEnabled",
    "Emulation.setEmulatedMedia",
    "Network.emulateNetworkConditions",
}

_REJECT_REASONS = {
    "Browser.close": "Browser.close is rejected: external clients cannot stop the Profile",
    "Browser.setDownloadBehavior": (
        "Browser.setDownloadBehavior is rejected: download capture stays "
        "Agent-managed during automation sessions"
    ),
    "Page.setDownloadBehavior": (
        "Page.setDownloadBehavior is rejected: download capture stays "
        "Agent-managed during automation sessions"
    ),
}

_EMULATION_REASON = (
    "emulation override is rejected: it conflicts with the Profile configuration"
)


def _error_response(msg: dict[str, Any], reason: str) -> dict[str, Any] | None:
    """Build the stable rejection, or None when there is no id to answer."""
    if "id" not in msg:
        return None
    resp: dict[str, Any] = {
        "id": msg["id"],
        "error": {"code": -32000, "message": f"CBrowser tunnel: {reason}"},
    }
    if "sessionId" in msg:
        resp["sessionId"] = msg["sessionId"]
    return resp


class TunnelFilter:
    """Per-connection mediation state for one external tunnel client."""

    def __init__(self) -> None:
        self._known_pages: set[str] = set()
        self._pending_get_targets: set[int] = set()
        self._pending_attach: dict[int, str] = {}
        self._session_targets: dict[str, str] = {}
        self._pending_script: dict[int, str | None] = {}
        self._scripts: list[tuple[str | None, str]] = []
        self._next_cleanup_id = 900000

    # -- client -> browser -------------------------------------------------

    def filter_outgoing(
        self, msg: dict[str, Any]
    ) -> tuple[str, dict[str, Any] | None]:
        """Classify one client message.

        Returns ``("forward", None)``, ``("reject", error_or_None)`` or
        ``("forward", None)`` with registration side effects for script
        injection.  Rejected messages must not be forwarded.
        """
        method = msg.get("method")
        if not isinstance(method, str):
            return "forward", None
        if method in _REJECT_ALWAYS:
            reason = _REJECT_REASONS.get(method, _EMULATION_REASON)
            return "reject", _error_response(msg, reason)
        if method == "Target.closeTarget":
            target_id = (msg.get("params") or {}).get("targetId")
            if (
                isinstance(target_id, str)
                and target_id in self._known_pages
                and len(self._known_pages) == 1
            ):
                return "reject", _error_response(
                    msg,
                    "Target.closeTarget is rejected: refusing to close the "
                    "last remaining page (last_tab_protected)",
                )
            return "forward", None
        if method == "Page.close":
            session_id = msg.get("sessionId")
            target_id = (
                self._session_targets.get(session_id)
                if isinstance(session_id, str)
                else None
            )
            if (
                target_id is not None
                and target_id in self._known_pages
                and len(self._known_pages) == 1
            ):
                return "reject", _error_response(
                    msg,
                    "Page.close is rejected: refusing to close the last "
                    "remaining page (last_tab_protected)",
                )
            return "forward", None
        if method == "Target.getTargets":
            if isinstance(msg.get("id"), int):
                self._pending_get_targets.add(msg["id"])
            return "forward", None
        if method == "Target.attachToTarget":
            target_id = (msg.get("params") or {}).get("targetId")
            if isinstance(msg.get("id"), int) and isinstance(target_id, str):
                self._pending_attach[msg["id"]] = target_id
            return "forward", None
        if method == "Page.addScriptToEvaluateOnNewDocument":
            if isinstance(msg.get("id"), int):
                session_id = msg.get("sessionId")
                self._pending_script[msg["id"]] = (
                    session_id if isinstance(session_id, str) else None
                )
            return "forward", None
        return "forward", None

    # -- browser -> client -------------------------------------------------

    def observe_incoming(self, msg: dict[str, Any]) -> None:
        """Learn ownership facts from responses and events."""
        msg_id = msg.get("id")
        if isinstance(msg_id, int):
            if msg_id in self._pending_get_targets:
                self._pending_get_targets.discard(msg_id)
                # Only a successful response rebuilds the observed page
                # set: an error response carries no targetInfos, and
                # letting it clear the set would silently disable the
                # last-page backstop for the next close.
                result = msg.get("result")
                if "error" not in msg and isinstance(result, dict):
                    infos = result.get("targetInfos", [])
                    self._known_pages = {
                        str(t.get("targetId", ""))
                        for t in infos
                        if t.get("type") == "page"
                    }
            if msg_id in self._pending_attach:
                target_id = self._pending_attach.pop(msg_id)
                session_id = (msg.get("result") or {}).get("sessionId")
                if isinstance(session_id, str):
                    self._session_targets[session_id] = target_id
            if msg_id in self._pending_script:
                session_id = self._pending_script.pop(msg_id)
                identifier = (msg.get("result") or {}).get("identifier")
                if isinstance(identifier, str):
                    self._scripts.append((session_id, identifier))
            return
        if msg.get("method") == "Target.targetCreated":
            info = (msg.get("params") or {}).get("targetInfo") or {}
            target_id = info.get("targetId")
            if isinstance(target_id, str) and info.get("type") == "page":
                self._known_pages.add(target_id)
        elif msg.get("method") == "Target.targetDestroyed":
            target_id = (msg.get("params") or {}).get("targetId")
            if isinstance(target_id, str):
                self._known_pages.discard(target_id)

    # -- disconnect ----------------------------------------------------------

    def disconnect_cleanup_commands(self) -> list[dict[str, Any]]:
        """Removal commands for scripts registered by this connection."""
        commands = []
        for session_id, identifier in self._scripts:
            self._next_cleanup_id += 1
            cmd: dict[str, Any] = {
                "id": self._next_cleanup_id,
                "method": "Page.removeScriptToEvaluateOnNewDocument",
                "params": {"identifier": identifier},
            }
            if session_id is not None:
                cmd["sessionId"] = session_id
            commands.append(cmd)
        return commands
