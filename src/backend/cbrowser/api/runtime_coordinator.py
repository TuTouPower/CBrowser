"""Runtime Coordinator and SSE Broadcaster for CBrowser Control API."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
import uuid
from collections import deque
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from urllib.parse import quote
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

from cbrowser.domain.models import (
    PreviewPolicySyncRequest,
    ProfilePreviewEvent,
    ProfileRuntimeEvent,
    ProfileRuntimeEventData,
    SearchDefaultsStatusData,
    TransportObservationData,
)
from cbrowser.services.profile_service import ProfileNotFoundError, ProfileService
from pydantic import SecretStr

logger = logging.getLogger("cbrowser.api.runtime_coordinator")

_PLATFORM_DETECTION_LABELS: dict[str, tuple[str, ...]] = {
    "windows": ("windows", "office"),
    "macos": ("macos",),
}


class ReconcileOutcome(Enum):
    CONVERGED = "converged"
    RETRYABLE = "retryable"
    TERMINATED = "terminated"


class SearchDefaultsConflictError(RuntimeError):
    """The search-defaults retry names a stale instance (HTTP 409)."""


class SearchDefaultsUnavailableError(RuntimeError):
    """The search-defaults operation cannot reach the runtime (HTTP 503)."""


@dataclass
class _LastError:
    """A recorded coordinator error plus the config version it targets.

    t056 A26: an error is recorded against the version the failed
    operation targeted.  Clearing is bound to that version: only an
    instance of the same (or a newer, superseding) version reaching
    running clears it, so a new version's failure is never hidden by
    an old version still running.
    """

    message: str
    config_version: int | None = None


def _downstream_error_text(resp: Any) -> str:
    """Extract the downstream failure reason from a Supervisor response.

    t056 A15: the Supervisor answers in the unified ErrorResponse shape,
    so ``error`` and ``message`` are preserved together (``error:
    message``) and stored as the coordinator's last error for the
    profile — surfaced on the runtime view as ``last_coordinator_error``,
    the Profile's error_reason.  A legacy ``detail`` body and raw text
    remain as fallbacks for non-conforming bodies.
    """
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001 - non-JSON body falls back to raw text
        return resp.text
    if isinstance(body, dict):
        error = body.get("error")
        message = body.get("message")
        if isinstance(error, str) and error and isinstance(message, str) and message:
            return f"{error}: {message}"
        if isinstance(error, str) and error:
            return error
        if isinstance(message, str) and message:
            return message
        detail = body.get("detail")
        if isinstance(detail, str) and detail:
            return detail
    return resp.text


class RuntimeEventBroadcaster:
    """In-memory event hub for Server-Sent Events (SSE) with history ring buffer."""

    def __init__(self, maxlen: int = 1000):
        self._epoch = secrets.token_hex(16)
        self._next_event_id: int = 1
        self._history: deque[ProfileRuntimeEvent] = deque(maxlen=maxlen)
        self._subscribers: set[asyncio.Queue[ProfileRuntimeEvent | str]] = set()
        self._lock = asyncio.Lock()

    def _format_event_id(self, sequence: int) -> str:
        return f"{self._epoch}:{sequence}"

    @staticmethod
    def _parse_event_id(event_id: str) -> tuple[str, int] | None:
        try:
            epoch, sequence = event_id.rsplit(":", 1)
            return epoch, int(sequence)
        except (AttributeError, ValueError):
            return None

    async def publish(self, data: ProfileRuntimeEventData) -> ProfileRuntimeEvent:
        async with self._lock:
            event_id = self._format_event_id(self._next_event_id)
            self._next_event_id += 1
            event = ProfileRuntimeEvent(id=event_id, event="runtime_state", data=data)
            self._history.append(event)
            for q in list(self._subscribers):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    # Drop oldest from full subscriber queue to keep real-time
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        q.put_nowait(event)
                    except asyncio.QueueFull:
                        pass
            return event

    async def publish_transient(self, event_name: str, data: Any) -> None:
        payload = (
            data.model_dump_json()
            if hasattr(data, "model_dump_json")
            else json.dumps(data, separators=(",", ":"))
        )
        frame = f"event: {event_name}\ndata: {payload}\n\n"
        async with self._lock:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(frame)
                except asyncio.QueueFull:
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        q.put_nowait(frame)
                    except asyncio.QueueFull:
                        pass

    async def subscribe(
        self,
        last_event_id: str | None = None,
        initial_snapshot_provider: Callable[[], list[ProfileRuntimeEventData]]
        | None = None,
    ) -> AsyncGenerator[str, None]:
        q: asyncio.Queue[ProfileRuntimeEvent | str] = asyncio.Queue(maxsize=100)
        initial_events: list[ProfileRuntimeEvent] = []
        resync_required = False
        async with self._lock:
            replayed = False
            if last_event_id:
                parsed = self._parse_event_id(last_event_id)
                if parsed is not None:
                    target_epoch, target_id = parsed
                    history_sequences = [
                        int(event.id.rsplit(":", 1)[1]) for event in self._history
                    ]
                    last_published = self._next_event_id - 1
                    if target_epoch == self._epoch and target_id <= last_published:
                        if not history_sequences or (
                            min(history_sequences) - 1
                            <= target_id
                            <= max(history_sequences)
                        ):
                            # The shared history still covers the gap (or the
                            # subscriber is already up to date): replay only
                            # what is missing, nothing is rebuilt.
                            initial_events = [
                                event
                                for event in self._history
                                if int(event.id.rsplit(":", 1)[1]) > target_id
                            ]
                            replayed = True
                        # else: the id fell out of the retained window; fall
                        # through to an explicit snapshot rebuild below.

            if not replayed and initial_snapshot_provider is not None:
                # One consistent read under the same lock publish() uses, so
                # the snapshot, its live base point and the subscriber
                # registration share a single ordering: no live event can be
                # missed or delivered before older snapshot state. Snapshot
                # frames are private to this subscriber — they never enter
                # the shared history — and all carry the base point id (the
                # last live sequence at snapshot time), so a later reconnect
                # resumes replay exactly after the base point.
                raw_res = initial_snapshot_provider()
                if asyncio.iscoroutine(raw_res):
                    snapshot_data_list = await raw_res
                else:
                    snapshot_data_list = raw_res
                base_id = self._format_event_id(self._next_event_id - 1)
                for data in snapshot_data_list:
                    initial_events.append(
                        ProfileRuntimeEvent(
                            id=base_id, event="runtime_state", data=data
                        )
                    )
            elif not replayed and last_event_id:
                # The caller asked to resume from an id we cannot serve and
                # no snapshot provider exists: say so explicitly instead of
                # silently truncating the stream.
                resync_required = True

            # Register only after the snapshot/catch-up is built while holding
            # the same lock as publish(), so no live event can fall into the
            # gap between the snapshot base point and live delivery.
            self._subscribers.add(q)

        try:
            if resync_required:
                yield ": resync-required\n\n"
            for event in initial_events:
                payload = event.data.model_dump_json()
                yield f"id: {event.id}\nevent: {event.event}\ndata: {payload}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    if isinstance(event, str):
                        yield event
                        continue
                    payload = event.data.model_dump_json()
                    yield f"id: {event.id}\nevent: {event.event}\ndata: {payload}\n\n"
                except TimeoutError:
                    yield ": ping\n\n"
        finally:
            self._subscribers.discard(q)


class RuntimeCoordinator:
    """Coordinates Profile runtime desires with external Supervisor via RPC."""

    def __init__(
        self,
        supervisor_url: str | None,
        supervisor_token: SecretStr | str | None,
        profile_service: ProfileService,
        require_supervisor: bool = False,
        max_retries: int | None = None,
        stop_max_retries: int = 5,
        initial_backoff: float = 0.5,
        max_backoff: float = 10.0,
        backoff_factor: float = 2.0,
        transport: httpx.AsyncBaseTransport | None = None,
        event_broadcaster: RuntimeEventBroadcaster | None = None,
    ):
        clean_url = supervisor_url.strip().rstrip("/") if supervisor_url else None
        token_val = None
        if supervisor_token is not None:
            token_val = (
                supervisor_token.get_secret_value()
                if isinstance(supervisor_token, SecretStr)
                else str(supervisor_token).strip()
            )

        if require_supervisor and (not clean_url or not token_val):
            raise RuntimeError("Supervisor URL and token must be configured")

        self.supervisor_url = clean_url
        self._token_str = token_val
        self.profile_service = profile_service
        self.require_supervisor = require_supervisor
        self.max_retries = max_retries
        self.stop_max_retries = stop_max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_factor = backoff_factor
        self.transport = transport
        self.broadcaster = event_broadcaster or RuntimeEventBroadcaster()

        self._last_errors: dict[str, _LastError] = {}
        self._search_defaults: dict[str, SearchDefaultsStatusData | None] = {}
        self._transport: dict[str, TransportObservationData | None] = {}
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._publish_tasks: set[asyncio.Task[None]] = set()
        self._client: httpx.AsyncClient | None = None
        self._pending_preview_policy: dict[str, tuple[bool, int, str | None]] = {}
        self._running: bool = False
        # t031: set by app lifespan after the control service is built.
        # None in tests that construct the coordinator standalone.
        self.control_service = None

    def is_enabled(self) -> bool:
        return bool(self.supervisor_url and self._token_str)

    @staticmethod
    def _is_running_converged(runtime: Any) -> bool:
        return (
            getattr(runtime, "desired_state", None) == "running"
            and getattr(runtime, "observed_state", None) == "running"
            and getattr(runtime, "runtime_instance_id", None) is not None
        )

    @staticmethod
    def _is_error_converged(runtime: Any, error: _LastError) -> bool:
        """Whether *runtime* shows the error's target version running.

        t056 A26: an error is settled only when an instance of its
        target version (or a newer, superseding one) is running.  A
        version-less error (no known target) settles on any running
        instance.  A runtime without a config_version cannot prove the
        target version runs, so it never settles a versioned error.
        """
        if not RuntimeCoordinator._is_running_converged(runtime):
            return False
        if error.config_version is None:
            return True
        runtime_version = getattr(runtime, "config_version", None)
        return (
            isinstance(runtime_version, int)
            and runtime_version >= error.config_version
        )

    def get_last_error(
        self, profile_id: str, runtime: Any = None
    ) -> str | None:
        """Read the last coordinator error.  A pure read: it never
        clears (t056 A26).  When a runtime record is supplied and it
        shows the error's target version running, there is nothing to
        report; the stored entry itself is cleared only by a write
        path (see clear_last_error_if_converged)."""
        entry = self._last_errors.get(profile_id)
        if entry is None:
            return None
        if runtime is not None and self._is_error_converged(runtime, entry):
            return None
        return entry.message

    def set_last_error(
        self,
        profile_id: str,
        error: str | None,
        *,
        config_version: int | None = None,
    ) -> None:
        """Record (or clear, when *error* is None) the last error.

        When *config_version* is omitted, a previously recorded target
        version is kept: a follow-up message about the same failure
        (e.g. the retry-limit suffix) must not drop the version the
        original error targeted.
        """
        if error is None:
            self._last_errors.pop(profile_id, None)
            return
        previous = self._last_errors.get(profile_id)
        target = (
            config_version
            if config_version is not None
            else (previous.config_version if previous is not None else None)
        )
        self._last_errors[profile_id] = _LastError(error, target)

    def clear_last_error(
        self, profile_id: str, *, config_version: int | None = None
    ) -> None:
        """Clear the recorded error.

        Without *config_version* the clear is unconditional (profile
        gone, stopped intent converged).  With one, only an error whose
        target is that version or older is cleared: a newer version's
        failure is not erased by an older version's success.
        """
        if config_version is None:
            self._last_errors.pop(profile_id, None)
            return
        entry = self._last_errors.get(profile_id)
        if entry is None or entry.config_version is None:
            self._last_errors.pop(profile_id, None)
        elif config_version >= entry.config_version:
            self._last_errors.pop(profile_id, None)

    def clear_last_error_if_converged(
        self, profile_id: str, runtime: Any
    ) -> None:
        """Write-path clear (t056 A26): drop the error only when the
        supplied runtime record shows its target version running."""
        entry = self._last_errors.get(profile_id)
        if entry is not None and self._is_error_converged(runtime, entry):
            self._last_errors.pop(profile_id, None)

    def egress_probe_runner(self):
        """Production egress-probe runner (t052): probes run in the
        Supervisor's helper container, which shares the Browser network
        perspective.  Returns ``None`` when no Supervisor is configured —
        the service then records a failed observation instead of probing
        from the API process (whose egress would be the wrong one)."""
        from cbrowser.services.egress_probe import SupervisorEgressProbeRunner

        if not self.is_enabled():
            return None
        return SupervisorEgressProbeRunner(
            supervisor_url=self.supervisor_url,
            supervisor_token=self._token_str,
            transport=self.transport,
        )

    async def get_font_runtime(
        self, profile_id: str
    ) -> tuple[str | None, list[str]]:
        """Resolve the bound font set and its missing detection fonts (AC-007).

        Derived from the Profile's own config with the same ``check_font_set``
        detection data the Agent reports in /health, so the REST response and
        SSE agree with the in-container check. The read is live on every
        call (t053 A19): there is deliberately no cache, so a set that is
        deleted or damaged is reported missing immediately, with no restart.
        A missing set reports every detection font as uncovered; the
        Supervisor's launch gate still fails closed on it separately.
        Any read failure degrades to the set id with an empty missing list
        and never breaks a runtime response.
        """
        from cbrowser import font_sets
        from cbrowser.font_sets import DETECTION_FONTS
        from cbrowser.runtime_agent.fontconfig import PLATFORM_FONTS_UNCONFIGURED

        try:
            profile = await self.profile_service.get_profile(profile_id)
        except Exception:  # noqa: BLE001
            return None, []
        config = profile.config
        font_set_id = config.font_set_id
        if not font_set_id:
            return None, [PLATFORM_FONTS_UNCONFIGURED]
        platform = config.fingerprint_platform
        if platform not in _PLATFORM_DETECTION_LABELS:
            return str(font_set_id), []
        labels = _PLATFORM_DETECTION_LABELS[platform]
        found = font_sets.get_font_set(platform, font_set_id)
        if found is None:
            return str(font_set_id), sorted(
                {
                    name
                    for label in labels
                    for name in DETECTION_FONTS.get(label, ())
                }
            )
        directory, _manifest = found
        detection = font_sets.check_font_set(directory).get("detection", {})
        missing = sorted(
            {
                name
                for label in labels
                for name in detection.get(label, {}).get("missing", [])
            }
        )
        return str(font_set_id), missing

    def get_search_defaults(
        self, profile_id: str
    ) -> SearchDefaultsStatusData | None:
        return self._search_defaults.get(profile_id)

    def fenced_search_defaults(
        self, profile_id: str, runtime_instance_id: str | None
    ) -> SearchDefaultsStatusData | None:
        """Cached status only when it belongs to the given live instance.

        Every surface that pairs a status with an instance id (REST view,
        SSE snapshot, live publish) must apply this fence, or an instance
        switch can briefly broadcast the old instance's status under the
        new instance's id (review t022_code_f010).
        """
        status = self._search_defaults.get(profile_id)
        if status is None:
            return None
        if status.runtime_instance_id != runtime_instance_id:
            return None
        return status

    async def refresh_search_defaults(
        self, profile_id: str
    ) -> SearchDefaultsStatusData | None:
        """Best-effort refresh of the cached search-defaults status.

        Reads the supervisor's fenced observation of the live agent. Any
        failure keeps the previously cached value; this status never
        affects runtime readiness.
        """
        if not self.is_enabled():
            return self.get_search_defaults(profile_id)
        import httpx

        if not self._client:
            self._client = httpx.AsyncClient(
                transport=self.transport, timeout=10.0, trust_env=False
            )
        url = (
            f"{self.supervisor_url}/supervisor/v1/profiles/"
            f"{quote(profile_id, safe='')}/search-defaults"
        )
        headers = {"Authorization": f"Bearer {self._token_str}"}
        try:
            resp = await self._client.get(url, headers=headers)
        except Exception:  # noqa: BLE001 - status refresh is best-effort only
            return self.get_search_defaults(profile_id)
        if resp.status_code != 200:
            return self.get_search_defaults(profile_id)
        try:
            payload = resp.json()
            raw_status = payload.get("search_defaults")
            status = (
                SearchDefaultsStatusData.model_validate(raw_status)
                if raw_status is not None
                else None
            )
            # Only surface a status that belongs to the instance the
            # supervisor currently fenced for this profile.
            if status is not None and (
                payload.get("runtime_instance_id") is None
                or status.runtime_instance_id != payload.get("runtime_instance_id")
            ):
                status = None
        except Exception:  # noqa: BLE001 - malformed supervisor payload keeps the cache
            return self.get_search_defaults(profile_id)
        self._search_defaults[profile_id] = status
        return status

    async def close_supervisor_tunnels(
        self, profile_id: str, generation: int
    ) -> bool:
        """Ask the Supervisor to close its tunnels for the profile (t031).

        Returns True only when the Supervisor confirms the close AND
        the attendant release (t031_code_f001: a failed attendant
        release keeps the control record's pending flag set, so the
        next reconcile round retries the whole cascade). A False result
        leaves the pending flag set (see reconcile_profile_now).
        """
        if not self.is_enabled():
            return False
        import httpx

        if not self._client:
            self._client = httpx.AsyncClient(
                transport=self.transport, timeout=10.0, trust_env=False
            )
        url = (
            f"{self.supervisor_url}/supervisor/v1/profiles/"
            f"{quote(profile_id, safe='')}/control/close-tunnels"
        )
        headers = {"Authorization": f"Bearer {self._token_str}"}
        try:
            resp = await self._client.post(
                url, json={"generation": generation}, headers=headers
            )
        except Exception:  # noqa: BLE001 - close failure degrades to pending
            return False
        if resp.status_code != 200:
            return False
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001 - undecodable close is unconfirmed
            return False
        return body.get("attendant_released") is True

    async def list_attendant_dialogs(
        self, profile_id: str
    ) -> list[dict] | None:
        """Peek held dialogs via the Supervisor (t031 answer path).

        Returns None when the Supervisor is disabled or unreachable;
        an empty list means the attendant is reachable and holds
        nothing for this profile.
        """
        if not self.is_enabled():
            return None
        import httpx

        if not self._client:
            self._client = httpx.AsyncClient(
                transport=self.transport, timeout=10.0, trust_env=False
            )
        url = (
            f"{self.supervisor_url}/supervisor/v1/profiles/"
            f"{quote(profile_id, safe='')}/control/dialogs"
        )
        headers = {"Authorization": f"Bearer {self._token_str}"}
        try:
            resp = await self._client.get(url, headers=headers)
        except Exception:  # noqa: BLE001 - unreachable Supervisor degrades
            return None
        if resp.status_code != 200:
            return None
        try:
            body = resp.json()
        except ValueError:
            return None
        dialogs = body.get("dialogs")
        return dialogs if isinstance(dialogs, list) else None

    async def answer_attendant_dialog(
        self,
        profile_id: str,
        target_id: str,
        accept: bool,
        prompt_text: str | None = None,
    ) -> dict | None:
        """Answer a held dialog via the Supervisor (t031 answer path)."""
        if not self.is_enabled():
            return None
        import httpx

        if not self._client:
            self._client = httpx.AsyncClient(
                transport=self.transport, timeout=10.0, trust_env=False
            )
        url = (
            f"{self.supervisor_url}/supervisor/v1/profiles/"
            f"{quote(profile_id, safe='')}/control/answer-dialog"
        )
        headers = {"Authorization": f"Bearer {self._token_str}"}
        payload: dict[str, Any] = {"target_id": target_id, "accept": accept}
        if prompt_text is not None:
            payload["prompt_text"] = prompt_text
        try:
            resp = await self._client.post(
                url, json=payload, headers=headers
            )
        except Exception:  # noqa: BLE001 - unreachable Supervisor degrades
            return None
        if resp.status_code != 200:
            return None
        try:
            body = resp.json()
        except ValueError:
            return None
        dialog = body.get("dialog")
        return dialog if isinstance(dialog, dict) else None

    def get_transport(
        self, profile_id: str
    ) -> TransportObservationData | None:
        return self._transport.get(profile_id)

    def fenced_transport(
        self, profile_id: str, runtime_instance_id: str | None
    ) -> TransportObservationData | None:
        """Cached observation only when it belongs to the live instance.

        Same fence rationale as search-defaults: an instance switch must
        never broadcast the old generation's transport state under the
        new instance's id.
        """
        observation = self._transport.get(profile_id)
        if observation is None:
            return None
        if observation.runtime_instance_id != runtime_instance_id:
            return None
        return observation

    async def refresh_transport(
        self, profile_id: str
    ) -> TransportObservationData | None:
        """Best-effort refresh of the cached transport observation.

        Any failure keeps the previously cached value; before the first
        successful report the value stays absent (rendered as unknown).
        """
        if not self.is_enabled():
            return self.get_transport(profile_id)
        import httpx

        if not self._client:
            self._client = httpx.AsyncClient(
                transport=self.transport, timeout=10.0, trust_env=False
            )
        url = (
            f"{self.supervisor_url}/supervisor/v1/profiles/"
            f"{quote(profile_id, safe='')}/transport"
        )
        headers = {"Authorization": f"Bearer {self._token_str}"}
        try:
            resp = await self._client.get(url, headers=headers)
        except Exception:  # noqa: BLE001 - observation refresh is best-effort only
            return self.get_transport(profile_id)
        if resp.status_code != 200:
            return self.get_transport(profile_id)
        try:
            payload = resp.json()
            raw = payload.get("transport")
            observation = (
                TransportObservationData.model_validate(raw)
                if raw is not None
                else None
            )
            if observation is not None and (
                payload.get("runtime_instance_id") is None
                or observation.runtime_instance_id
                != payload.get("runtime_instance_id")
            ):
                observation = None
        except Exception:  # noqa: BLE001 - malformed supervisor payload keeps the cache
            return self.get_transport(profile_id)
        self._transport[profile_id] = observation
        return observation

    async def retry_search_defaults(
        self, profile_id: str, request_id: str | None = None
    ) -> SearchDefaultsStatusData | None:
        """Ask the supervisor to retry search-defaults on the live instance.

        Fenced to the instance recorded in the runtime state. The
        request_id is the end-to-end idempotency key: callers repeating a
        submission pass the same key (the router maps the Idempotency-Key
        header), and the supervisor/agent deduplicate on it, so a retried
        HTTP call cannot execute the initialization twice. Without a
        caller key a fresh one is generated for this single call.
        """
        runtime = await self.profile_service.get_runtime(profile_id)
        if not self.is_enabled():
            raise SearchDefaultsUnavailableError("Supervisor is not configured")
        if not runtime.runtime_instance_id:
            raise SearchDefaultsUnavailableError("Profile runtime is not running")
        import httpx

        if not self._client:
            self._client = httpx.AsyncClient(
                transport=self.transport, timeout=10.0, trust_env=False
            )
        url = f"{self.supervisor_url}/supervisor/v1/profiles/search-defaults/retry"
        headers = {"Authorization": f"Bearer {self._token_str}"}
        body = {
            "profile_id": profile_id,
            "runtime_instance_id": runtime.runtime_instance_id,
            "request_id": request_id or f"sd-retry-{uuid.uuid4().hex}",
        }
        try:
            resp = await self._client.post(url, json=body, headers=headers)
        except httpx.TransportError as e:
            raise SearchDefaultsUnavailableError(
                f"Supervisor unreachable: {type(e).__name__}"
            ) from None
        if resp.status_code == 409:
            raise SearchDefaultsConflictError(
                "Search defaults retry conflicts with the live instance"
            )
        if resp.status_code != 200:
            raise SearchDefaultsUnavailableError(
                f"Supervisor search-defaults retry failed ({resp.status_code})"
            )
        # The retry is consumed asynchronously by the runner (request
        # file + status file). Poll the status briefly until the runner
        # reports an outcome stamped with THIS request_id, so the
        # response and the SSE publish reflect this retry's terminal
        # state instead of the stale pre-retry failure (review
        # t022_code_f011). The wait is bounded; on timeout the latest
        # known status is returned and later refreshes converge.
        effective_request_id = body["request_id"]
        status = await self.refresh_search_defaults(profile_id)
        deadline = time.monotonic() + 5.0
        while (
            status is None or status.request_id != effective_request_id
        ) and time.monotonic() < deadline:
            await asyncio.sleep(0.25)
            status = await self.refresh_search_defaults(profile_id)
        await self.publish_profile_change(profile_id)
        return status

    async def start(self) -> None:
        import httpx

        self._running = True
        self._client = httpx.AsyncClient(
            transport=self.transport,
            timeout=10.0,
            trust_env=False,
        )
        if not self.is_enabled():
            logger.warning("Runtime Coordinator is disabled: supervisor not configured")
            return

        # Startup reconciliation: converge any running desired state
        # without an active instance
        try:
            profiles = await self.profile_service.list_profiles()
            for p in profiles:
                try:
                    rt = await self.profile_service.get_runtime(p.id)
                    if rt.desired_state == "running" and (
                        rt.observed_state != "running" or rt.runtime_instance_id is None
                    ):
                        logger.info(
                            "Scheduling startup convergence for running profile %s",
                            p.id,
                        )
                        self.trigger_reconcile(p.id)
                    elif rt.desired_state == "stopped" and (
                        rt.observed_state != "stopped"
                        or rt.runtime_instance_id is not None
                    ):
                        logger.info(
                            "Scheduling startup convergence for stopped profile %s",
                            p.id,
                        )
                        self.trigger_reconcile(p.id)
                except Exception as e:  # noqa: BLE001 - startup scan must isolate per-profile inspection failure
                    logger.warning(
                        "Error checking runtime on startup for %s: %s", p.id, e
                    )
        except Exception as e:  # noqa: BLE001 - top-level startup task boundary prevents worker crash
            logger.error("Failed to run startup reconciliation scan: %s", e)

    def has_active_task(self, profile_id: str) -> bool:
        """Whether a runtime task is active for the profile."""
        return profile_id in self._active_tasks

    @property
    def publish_task_count(self) -> int:
        """Number of in-flight publish tasks."""
        return len(self._publish_tasks)

    async def stop(self) -> None:
        self._running = False
        tasks = list(self._active_tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._active_tasks.clear()

        publish_tasks = list(self._publish_tasks)
        for task in publish_tasks:
            if not task.done():
                task.cancel()
        if publish_tasks:
            await asyncio.gather(*publish_tasks, return_exceptions=True)
        self._publish_tasks.clear()

        if self._client:
            await self._client.aclose()
            self._client = None

    def _on_publish_task_done(self, task: asyncio.Task[None]) -> None:
        self._publish_tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.warning("Background runtime publish failed: %s", error)

    def publish_profile_change_later(self, profile_id: str) -> None:
        """Schedule an SSE publish owned by the coordinator's task set."""
        task = asyncio.create_task(self.publish_profile_change(profile_id))
        self._publish_tasks.add(task)
        task.add_done_callback(self._on_publish_task_done)

    def publish_reference_change_later(
        self, event_name: str, entity_id: str | None = None
    ) -> None:
        """Schedule a transient reference-data change event (t056 A31):
        ``groups_changed`` / ``proxies_changed``.  The payload carries
        only the changed entity id (or null for a reorder); receivers
        invalidate their group/proxy/profile lists and refetch."""
        task = asyncio.create_task(
            self.broadcaster.publish_transient(
                event_name, {"entity_id": entity_id}
            )
        )
        self._publish_tasks.add(task)
        task.add_done_callback(self._on_publish_task_done)

    async def publish_profile_change(self, profile_id: str) -> None:
        try:
            rt = await self.profile_service.get_runtime(profile_id)
            err = self.get_last_error(profile_id, runtime=rt)
            control = None
            if self.control_service is not None:
                try:
                    control = await self.control_service.get_state(profile_id)
                except Exception:  # noqa: BLE001 - control is advisory here
                    control = None
            font_set_id, missing_fonts = await self.get_font_runtime(profile_id)
            data = ProfileRuntimeEventData(
                profile_id=rt.profile_id,
                desired_state=rt.desired_state,
                observed_state=rt.observed_state,
                runtime_instance_id=rt.runtime_instance_id,
                failure_count=rt.failure_count,
                restart_blocked=rt.restart_blocked,
                last_started_at=rt.last_started_at,
                last_stopped_at=rt.last_stopped_at,
                browser_product=rt.browser_product,
                browser_user_agent=rt.browser_user_agent,
                font_set_id=font_set_id,
                missing_fonts=missing_fonts,
                last_coordinator_error=err,
                search_defaults=self.fenced_search_defaults(
                    profile_id, rt.runtime_instance_id
                ),
                transport=self.fenced_transport(
                    profile_id, rt.runtime_instance_id
                ),
                control=control,
                updated_at=rt.updated_at,
            )
            await self.broadcaster.publish(data)
        except ProfileNotFoundError:
            pass
        except Exception as e:  # noqa: BLE001 - event broadcaster boundary protects coordinator loop
            logger.warning("Error publishing profile runtime change: %s", e)

    async def _post_preview_policy(
        self,
        profile_id: str,
        enabled: bool,
        epoch: int,
        instance: str | None,
    ) -> None:
        import httpx

        if not self._client:
            self._client = httpx.AsyncClient(
                transport=self.transport, timeout=10.0, trust_env=False
            )
        url = (
            f"{self.supervisor_url}/supervisor/v1/profiles/"
            f"{quote(profile_id, safe='')}/preview-policy"
        )
        headers = {"Authorization": f"Bearer {self._token_str}"}
        body = PreviewPolicySyncRequest(
            enabled=enabled,
            epoch=epoch,
            runtime_instance_id=instance,
            request_id=uuid.uuid4().hex,
        ).model_dump()
        resp = await self._client.post(url, json=body, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Preview policy sync failed ({resp.status_code})")

    async def request_preview_policy(
        self,
        profile_id: str,
        enabled: bool,
        epoch: int,
        instance: str | None,
    ) -> None:
        if not self.is_enabled():
            self._pending_preview_policy[profile_id] = (enabled, epoch, instance)
            return
        try:
            await self._post_preview_policy(profile_id, enabled, epoch, instance)
        except Exception as exc:  # noqa: BLE001 - keep a pending dispatch
            self._pending_preview_policy[profile_id] = (enabled, epoch, instance)
            logger.warning(
                "Preview policy dispatch pending: profile=%s error_type=%s",
                profile_id,
                type(exc).__name__,
            )
        else:
            self._pending_preview_policy.pop(profile_id, None)

    async def flush_pending_preview_policy(self, profile_id: str) -> None:
        pending = self._pending_preview_policy.get(profile_id)
        if pending is None or not self.is_enabled():
            return
        enabled, epoch, instance = pending
        try:
            await self._post_preview_policy(profile_id, enabled, epoch, instance)
        except Exception as exc:  # noqa: BLE001 - retry on the next reconcile
            logger.warning(
                "Preview policy reconcile retry failed: profile=%s error_type=%s",
                profile_id,
                type(exc).__name__,
            )
            return
        self._pending_preview_policy.pop(profile_id, None)

    def has_pending_preview_policy(self, profile_id: str) -> bool:
        return profile_id in self._pending_preview_policy

    async def publish_profile_preview(
        self, profile_id: str, captured_at: str
    ) -> None:
        data = ProfilePreviewEvent(
            profile_id=profile_id, captured_at=captured_at
        )
        await self.broadcaster.publish_transient("profile_preview", data)

    def trigger_reconcile(self, profile_id: str) -> None:
        if not self.is_enabled():
            self.set_last_error(profile_id, "Supervisor is not configured")
            self.publish_profile_change_later(profile_id)
            return

        existing = self._active_tasks.get(profile_id)
        if existing and not existing.done():
            existing.cancel()

        task = asyncio.create_task(self._reconcile_profile_loop(profile_id))
        self._active_tasks[profile_id] = task

    async def reconcile_profile_now(
        self, profile_id: str, *, operation_id: str | None = None
    ) -> ReconcileOutcome:
        if not self.is_enabled():
            self.set_last_error(profile_id, "Supervisor is not configured")
            await self.publish_profile_change(profile_id)
            return ReconcileOutcome.RETRYABLE

        # t031: a takeover whose Supervisor close failed stays pending;
        # retry it on every reconcile round until the Supervisor
        # confirms (the API-side state already committed at takeover).
        if self.control_service is not None:
            try:
                await self.control_service.retry_pending_supervisor_close(
                    profile_id
                )
            except Exception:  # noqa: BLE001 - retry never blocks reconcile
                logger.warning(
                    "Pending supervisor close retry failed: profile=%s",
                    profile_id,
                )

        await self.flush_pending_preview_policy(profile_id)

        import httpx

        if not self._client:
            self._client = httpx.AsyncClient(
                transport=self.transport,
                timeout=10.0,
                trust_env=False,
            )

        try:
            runtime = await self.profile_service.get_runtime(profile_id)
        except ProfileNotFoundError:
            self.clear_last_error(profile_id)
            return ReconcileOutcome.CONVERGED

        if runtime.desired_state == "running":
            return await self._reconcile_running(
                profile_id, runtime, operation_id=operation_id
            )
        if runtime.desired_state == "stopped":
            return await self._reconcile_stopped(
                profile_id, runtime, operation_id=operation_id
            )
        return ReconcileOutcome.CONVERGED

    async def _reconcile_running(
        self, profile_id: str, runtime, *, operation_id: str | None = None
    ) -> ReconcileOutcome:
        import httpx

        # t056 A26: the target version is the latest config version.
        # Every error recorded and every clear in this method is bound
        # to it, and convergence itself requires the running instance
        # to be that version — an old version still running is not a
        # converged new version.
        try:
            versions = await self.profile_service.list_config_versions(profile_id)
            latest_v = max(
                (v.version for v in versions), default=runtime.config_version
            )
        except Exception:  # noqa: BLE001 - config version query failure safely falls back to current runtime version
            latest_v = runtime.config_version

        if runtime.restart_blocked:
            self.set_last_error(
                profile_id,
                "Restart blocked; manual retry required",
                config_version=latest_v,
            )
            await self.publish_profile_change(profile_id)
            return ReconcileOutcome.TERMINATED

        if (
            runtime.observed_state == "running"
            and runtime.runtime_instance_id is not None
            and runtime.config_version >= latest_v
        ):
            self.clear_last_error_if_converged(profile_id, runtime)
            return ReconcileOutcome.CONVERGED

        profile = await self.profile_service.get_profile(profile_id)
        req_body = {
            "profile_id": profile_id,
            "profile_number": profile.display_number,
            "config_version": latest_v,
            "force": False,
            "operation_id": operation_id
            or f"coord_start_{profile_id}_{uuid.uuid4().hex[:8]}",
        }
        url = f"{self.supervisor_url}/supervisor/v1/profiles/start"
        headers = {"Authorization": f"Bearer {self._token_str}"}

        try:
            resp = await self._client.post(url, json=req_body, headers=headers)
        except httpx.TransportError as e:
            err_msg = f"Supervisor unreachable: {type(e).__name__}"
            self.set_last_error(profile_id, err_msg, config_version=latest_v)
            await self.publish_profile_change(profile_id)
            return ReconcileOutcome.RETRYABLE

        if resp.status_code == 200:
            # The start for latest_v was accepted: an error recorded
            # against that version (or an older one it supersedes) is
            # settled.  An error targeting a newer version can never
            # exist here — latest_v is the maximum — so this clear is
            # version-bound by construction.
            self.clear_last_error(profile_id, config_version=latest_v)
            await self.publish_profile_change(profile_id)
            return ReconcileOutcome.CONVERGED

        err_msg = (
            f"Supervisor start failed ({resp.status_code}): "
            f"{_downstream_error_text(resp)}"
        )
        self.set_last_error(profile_id, err_msg, config_version=latest_v)
        await self.publish_profile_change(profile_id)
        return ReconcileOutcome.RETRYABLE

    async def _reconcile_stopped(
        self, profile_id: str, runtime, *, operation_id: str | None = None
    ) -> ReconcileOutcome:
        import httpx

        if runtime.observed_state == "stopped" and runtime.runtime_instance_id is None:
            self.clear_last_error(profile_id)
            return ReconcileOutcome.CONVERGED

        target_instance = runtime.runtime_instance_id
        if not target_instance:
            # Ask the Supervisor whether it still owns an instance. A
            # transport failure is retried; an authoritative "no instance"
            # response means the stopped intent already holds.
            status_url = (
                f"{self.supervisor_url}/supervisor/v1/profiles/{quote(profile_id, safe='')}/status"
            )
            headers = {"Authorization": f"Bearer {self._token_str}"}
            try:
                st_resp = await self._client.get(status_url, headers=headers)
            except httpx.TransportError as e:
                err_msg = f"Supervisor unreachable: {type(e).__name__}"
                self.set_last_error(profile_id, err_msg)
                await self.publish_profile_change(profile_id)
                return ReconcileOutcome.RETRYABLE

            if st_resp.status_code == 200:
                target_instance = st_resp.json().get("runtime_instance_id")
            elif st_resp.status_code != 404:
                err_msg = (
                    f"Supervisor status failed ({st_resp.status_code}): "
                    f"{_downstream_error_text(st_resp)}"
                )
                self.set_last_error(profile_id, err_msg)
                await self.publish_profile_change(profile_id)
                return ReconcileOutcome.RETRYABLE

            if not target_instance:
                self.clear_last_error(profile_id)
                await self.publish_profile_change(profile_id)
                return ReconcileOutcome.CONVERGED

        req_body = {
            "profile_id": profile_id,
            "runtime_instance_id": target_instance,
            "operation_id": operation_id
            or f"coord_stop_{profile_id}_{uuid.uuid4().hex[:8]}",
        }
        url = f"{self.supervisor_url}/supervisor/v1/profiles/stop"
        headers = {"Authorization": f"Bearer {self._token_str}"}

        try:
            resp = await self._client.post(url, json=req_body, headers=headers)
        except httpx.TransportError as e:
            err_msg = f"Supervisor unreachable: {type(e).__name__}"
            self.set_last_error(profile_id, err_msg)
            await self.publish_profile_change(profile_id)
            return ReconcileOutcome.RETRYABLE

        if resp.status_code == 200:
            # The stop response is a command result, not an observation of
            # stopped state. Consume it explicitly and converge only when
            # the authoritative runtime record (fed by Supervisor reports)
            # actually shows the stopped state.
            try:
                result_status = resp.json().get("status")
            except Exception:  # noqa: BLE001 - non-JSON body has no command result
                result_status = None
            if result_status not in {
                "stopped",
                "already_absent",
                "superseded_noop",
            }:
                self.set_last_error(
                    profile_id,
                    "Supervisor stop response omitted a valid command result",
                )
                await self.publish_profile_change(profile_id)
                return ReconcileOutcome.RETRYABLE
            try:
                refreshed = await self.profile_service.get_runtime(profile_id)
            except ProfileNotFoundError:
                self.clear_last_error(profile_id)
                return ReconcileOutcome.CONVERGED
            if (
                refreshed.observed_state == "stopped"
                and refreshed.runtime_instance_id is None
            ):
                self.clear_last_error(profile_id)
                await self.publish_profile_change(profile_id)
                return ReconcileOutcome.CONVERGED
            await self.publish_profile_change(profile_id)
            return ReconcileOutcome.RETRYABLE

        err_msg = (
            f"Supervisor stop failed ({resp.status_code}): "
            f"{_downstream_error_text(resp)}"
        )
        self.set_last_error(profile_id, err_msg)
        await self.publish_profile_change(profile_id)
        return ReconcileOutcome.RETRYABLE

    async def _reconcile_profile_loop(self, profile_id: str) -> None:
        backoff = self.initial_backoff
        retries = 0
        round_operation_id = f"coord_round_{uuid.uuid4().hex}"
        try:
            while self._running:
                try:
                    success = await self.reconcile_profile_now(
                        profile_id, operation_id=round_operation_id
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.exception(
                        "Unexpected error reconciling profile %s: %s",
                        profile_id,
                        e,  # noqa: TRY401
                    )
                    self.set_last_error(
                        profile_id, f"Coordinator error: {type(e).__name__}"
                    )
                    await self.publish_profile_change(profile_id)
                    success = False
                if isinstance(success, ReconcileOutcome):
                    outcome = success
                else:
                    outcome = (
                        ReconcileOutcome.CONVERGED
                        if success
                        else ReconcileOutcome.RETRYABLE
                    )
                if outcome is ReconcileOutcome.CONVERGED:
                    break
                if outcome is ReconcileOutcome.TERMINATED:
                    # Blocked intent keeps its last error; a manual reset creates
                    # a fresh reconcile round with cleared errors.
                    break
                retries += 1
                limit = self.max_retries
                if limit is None and self.stop_max_retries is not None:
                    try:
                        rt = await self.profile_service.get_runtime(profile_id)
                        if rt.desired_state == "stopped":
                            limit = self.stop_max_retries
                    except Exception as exc:  # noqa: BLE001 - non-critical query failure falls back to default limit
                        logger.debug(
                            "Failed querying runtime for stop retries: %s",
                            type(exc).__name__,
                        )
                if limit is not None and retries >= limit:
                    logger.warning(
                        "Reconciliation retry limit reached: profile=%s limit=%s",
                        profile_id,
                        limit,
                    )
                    previous = self.get_last_error(profile_id)
                    self.set_last_error(
                        profile_id,
                        (previous + "; " if previous else "")
                        + "Reconciliation retry limit reached; manual retry required",
                    )
                    await self.publish_profile_change(profile_id)
                    break
                await asyncio.sleep(min(backoff, self.max_backoff))
                backoff *= self.backoff_factor
        except asyncio.CancelledError:
            # Task superseded or coordinator stopped
            pass
        finally:
            if self._active_tasks.get(profile_id) is asyncio.current_task():
                self._active_tasks.pop(profile_id, None)
