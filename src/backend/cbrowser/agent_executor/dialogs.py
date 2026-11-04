"""Dialog routing for the t030 agent executor (p032).

Conservative defaults when no handler is registered: an alert only ever
closes; confirm / prompt / beforeunload are never default-accepted, because
accepting can change business state or discard unsaved content.  A
registered handler's explicit answer wins.  Native permission / device
prompts are not observable over CDP and are never silently granted: they
surface as ``needs_human`` for t031 handOff instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DialogRecord:
    target_id: str
    dialog_type: str  # alert | confirm | prompt | beforeunload
    message: str
    url: str = ""
    has_browser_handler: bool = False
    answered: bool = False
    answer: str | None = None  # "accept" | "dismiss"
    prompt_text: str | None = None


def default_action(dialog_type: str) -> str:
    """Conservative no-handler action for one dialog type."""
    if dialog_type == "alert":
        return "accept"  # an alert has only one button: closing it
    return "dismiss"


class DialogTracker:
    """Per-target open-dialog state for one executor session."""

    def __init__(self) -> None:
        self._open: dict[str, DialogRecord] = {}

    def record_opening(self, record: DialogRecord) -> None:
        self._open[record.target_id] = record

    def record_closed(self, target_id: str) -> None:
        self._open.pop(target_id, None)

    def open_for(self, target_id: str) -> DialogRecord | None:
        return self._open.get(target_id)

    def decide(
        self,
        target_id: str,
        answer: str | None = None,
        prompt_text: str | None = None,
    ) -> tuple[str, str | None]:
        """Resolve the answer for the open dialog on a target.

        ``answer=None`` means "no handler": apply the conservative default.
        Returns ``(action, prompt_text)`` and marks the record answered.
        Raises ``KeyError`` when no dialog is open on the target, and
        ``ValueError`` when ``answer`` is present but not a valid action:
        silently folding a typo (``"accep"``) into the opposite default
        would answer against the caller's intent without any signal.
        """
        record = self._open.get(target_id)
        if record is None:
            raise KeyError(f"no dialog open on target {target_id}")
        if answer is not None and answer not in ("accept", "dismiss"):
            raise ValueError(f"invalid dialog answer: {answer!r}")
        action = answer if answer is not None else default_action(
            record.dialog_type
        )
        record.answered = True
        record.answer = action
        record.prompt_text = prompt_text
        return action, prompt_text


def permission_needs_human_payload(
    *,
    profile_id: str,
    runtime_instance_id: str,
    target_id: str,
    kind: str,
    session_id: str,
) -> dict:
    """handOff payload shape for t031: a permission prompt needing a human.

    This is never an authorization: the executor cannot observe native
    permission/device prompts over CDP, so it reports them instead of
    granting them.
    """
    return {
        "handoff_kind": "permission_prompt",
        "profile_id": profile_id,
        "runtime_instance_id": runtime_instance_id,
        "target_id": target_id,
        "permission_kind": kind,
        "executor_session": session_id,
        "decision": "needs_human",
    }
