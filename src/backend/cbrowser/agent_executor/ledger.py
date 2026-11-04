"""Page ledger for the t030 agent executor.

Three concepts stay separate (p033):

* origin: who created the page (``agent`` / ``user`` / ``unknown``).  Adopt
  never rewrites origin.
* manageable: this session may locate and act on the page.
* cleanable: this session may close the page at cleanup.  Only pages
  provably created by this session are cleanable; adopt alone never grants
  cleanup, and ``managed=True`` never implies it.

Baseline pages (present when the session starts) are recorded as ``user``;
pages that appear mid-session without proof of agent creation are
``unknown``.  Both are preserved by every cleanup path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class PageRecord:
    target_id: str
    origin: str  # "agent" | "user" | "unknown"
    manageable: bool = False
    cleanable: bool = False
    opener_id: str | None = None
    created_at: float = field(default_factory=time.monotonic)


class PageLedger:
    """Tracks page ownership for one executor session."""

    def __init__(
        self,
        profile_id: str,
        runtime_instance_id: str,
        popup_window_s: float = 5.0,
    ) -> None:
        self.profile_id = profile_id
        self.runtime_instance_id = runtime_instance_id
        self.popup_window_s = popup_window_s
        self._pages: dict[str, PageRecord] = {}
        self._expect_popup_until: float = 0.0
        self._expect_popup_from: set[str] = set()

    # -- intake ------------------------------------------------------------

    def baseline(self, target_ids: list[str]) -> None:
        """Record pages that predate the session as user pages.

        Pages already observed (e.g. a popup that arrived between
        discovery enable and this baseline read) keep their record.
        """
        for target_id in target_ids:
            if target_id not in self._pages:
                self._pages[target_id] = PageRecord(
                    target_id=target_id, origin="user"
                )

    def record_created(self, target_id: str) -> PageRecord:
        """A target this session created via Target.createTarget."""
        record = PageRecord(
            target_id=target_id, origin="agent", manageable=True, cleanable=True
        )
        self._pages[target_id] = record
        return record

    def expect_popup(self, from_target_ids: list[str]) -> None:
        """Open an attribution window for popups from an agent action."""
        self._expect_popup_until = time.monotonic() + self.popup_window_s
        self._expect_popup_from = set(from_target_ids)

    def record_observed(
        self, target_id: str, opener_id: str | None = None
    ) -> PageRecord:
        """Record a targetCreated event seen mid-session.

        Attribution to the agent requires all three: an opener that is an
        agent page, an open attribution window from an agent action, and
        the opener inside that window's source set.  Anything short of that
        is ``unknown`` and therefore never cleanable.
        """
        if target_id in self._pages:
            return self._pages[target_id]
        now = time.monotonic()
        attributable = (
            opener_id is not None
            and now <= self._expect_popup_until
            and opener_id in self._expect_popup_from
            and self._pages.get(opener_id) is not None
            and self._pages[opener_id].origin == "agent"
        )
        if attributable:
            record = PageRecord(
                target_id=target_id,
                origin="agent",
                manageable=True,
                cleanable=True,
                opener_id=opener_id,
            )
        else:
            record = PageRecord(
                target_id=target_id, origin="unknown", opener_id=opener_id
            )
        self._pages[target_id] = record
        return record

    def record_closed(self, target_id: str) -> None:
        self._pages.pop(target_id, None)

    def restore(self, record: PageRecord) -> None:
        """Unconditionally install a persisted record (session resume).

        Used at session start to overlay the previous invocation's ledger
        onto the live baseline, so agent-owned pages are not mistaken for
        user pages just because they predate this process.
        """
        self._pages[record.target_id] = record

    # -- adopt ---------------------------------------------------------------

    def adopt(self, target_id: str) -> PageRecord:
        """Take management of an existing page without changing its origin.

        Cleanup permission is never derived from adopt: an adopted user or
        unknown page stays non-cleanable; an already agent-owned page keeps
        whatever cleanup permission it had.
        """
        record = self._pages.get(target_id)
        if record is None:
            record = PageRecord(target_id=target_id, origin="unknown")
            self._pages[target_id] = record
        record.manageable = True
        return record

    # -- queries ---------------------------------------------------------------

    def get(self, target_id: str) -> PageRecord | None:
        return self._pages.get(target_id)

    def all(self) -> list[PageRecord]:
        return list(self._pages.values())

    def cleanup_plan(
        self, live_target_ids: list[str]
    ) -> tuple[list[str], list[dict[str, str]]]:
        """Compute the safe cleanup set.

        Returns ``(closable, refused)``.  The browser's last remaining page
        is never closed: if every live target is agent-cleanable, the
        newest one is kept and reported as ``last_tab_protected``.
        """
        live = [t for t in live_target_ids if t in self._pages]
        closable = [
            t
            for t in live
            if self._pages[t].cleanable
        ]
        if closable and len(closable) == len(live):
            keep = max(closable, key=lambda t: self._pages[t].created_at)
            closable.remove(keep)
            refused = [
                {"target_id": keep, "reason": "last_tab_protected"},
            ]
        else:
            refused = []
        return closable, refused
