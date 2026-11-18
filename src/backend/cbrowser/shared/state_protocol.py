"""Minimal batch state protocol between the API and the Supervisor (t083).

The Supervisor's coordination (initial recovery, periodic reconcile,
control operations, exit retries) consumes ONLY this protocol — never
the UI runtime aggregate.  A state entry carries exactly what
coordination needs: desired intent, the bound instance/config fence,
the terminal-event and retry/block fields.  It never carries font
coverage, transport, search-defaults, control or UI data.

Consistency fences:

- ``api_epoch`` identifies one API process lifetime.  A snapshot or
  notice from another epoch invalidates everything cached from the
  previous one.
- ``state_revision`` is a per-Profile monotonic revision (DB column,
  incremented on every runtime row update).  A notice whose revision
  is not newer than the cached entry is stale and dropped; a snapshot
  is authoritative only once every batch of one epoch has been read.

Snapshots are keyset-paginated by ``profile_id`` with a declared batch
limit: the number of requests and SELECTs per alignment round grows
by batches, never by Profiles.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

# Declared batch limit for snapshot pagination (AC-002): one request
# and one SELECT per batch, independent of the Profile count.
MAX_STATE_BATCH = 200

# The API process epoch: generated once per process lifetime.  Every
# snapshot and change notice carries it; consumers discard state from
# any other epoch.
API_EPOCH = uuid.uuid4().hex


class SupervisorProfileState(BaseModel):
    """One Profile's minimal coordination state."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    display_number: int = Field(ge=0)
    desired_state: str
    observed_state: str
    runtime_instance_id: str | None = None
    config_version: int = Field(ge=1)
    failure_count: int = Field(ge=0)
    restart_blocked: bool = False
    last_exit_event_id: str | None = None
    backoff_started_at: str | None = None
    next_retry_at: str | None = None
    updated_at: str
    state_revision: int = Field(ge=0)


class StateSnapshot(BaseModel):
    """One batch of a full state alignment snapshot."""

    model_config = ConfigDict(extra="forbid")

    api_epoch: str
    profiles: list[SupervisorProfileState]
    # Keyset cursor for the next batch; None marks the final batch.
    next_cursor: str | None = None


class StateChangeNotice(BaseModel):
    """Pushed change notification over the Supervisor control channel.

    Carries the full minimal state of each changed Profile (fenced by
    ``state_revision``) plus the ids of Profiles removed since the
    previous notice.  Delivery is best-effort: the 30-second snapshot
    fallback realigns anything a lost notice missed.
    """

    model_config = ConfigDict(extra="forbid")

    api_epoch: str
    states: list[SupervisorProfileState] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)

