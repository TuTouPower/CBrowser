"""Runtime Coordinator and SSE Broadcaster for CBrowser v2 Control API."""

from __future__ import annotations

import asyncio
import logging
import secrets
import uuid
from collections import deque
from collections.abc import AsyncGenerator, Callable
from urllib.parse import quote
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

from cbrowser.domain.models import ProfileRuntimeEvent, ProfileRuntimeEventData
from cbrowser.services.profile_service import ProfileNotFoundError, ProfileService
from pydantic import SecretStr

logger = logging.getLogger("cbrowser.api.runtime_coordinator")


class ReconcileOutcome(Enum):
    CONVERGED = "converged"
    RETRYABLE = "retryable"
    TERMINATED = "terminated"


class RuntimeEventBroadcaster:
    """In-memory event hub for Server-Sent Events (SSE) with history ring buffer."""

    def __init__(self, maxlen: int = 1000):
        self._epoch = secrets.token_hex(16)
        self._next_event_id: int = 1
        self._history: deque[ProfileRuntimeEvent] = deque(maxlen=maxlen)
        self._subscribers: set[asyncio.Queue[ProfileRuntimeEvent]] = set()
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

    async def subscribe(
        self,
        last_event_id: str | None = None,
        initial_snapshot_provider: Callable[[], list[ProfileRuntimeEventData]]
        | None = None,
    ) -> AsyncGenerator[str, None]:
        q: asyncio.Queue[ProfileRuntimeEvent] = asyncio.Queue(maxsize=100)
        initial_events: list[ProfileRuntimeEvent] = []
        async with self._lock:
            replayed = False
            if last_event_id:
                parsed = self._parse_event_id(last_event_id)
                if parsed is not None:
                    target_epoch, target_id = parsed
                    history_sequences = [
                        int(event.id.rsplit(":", 1)[1]) for event in self._history
                    ]
                    if (
                        target_epoch == self._epoch
                        and history_sequences
                        and min(history_sequences)
                        <= target_id
                        <= max(history_sequences)
                    ):
                        initial_events = [
                            event
                            for event in self._history
                            if int(event.id.rsplit(":", 1)[1]) > target_id
                        ]
                        replayed = True

            if not replayed and initial_snapshot_provider is not None:
                raw_res = initial_snapshot_provider()
                if asyncio.iscoroutine(raw_res):
                    snapshot_data_list = await raw_res
                else:
                    snapshot_data_list = raw_res
                for data in snapshot_data_list:
                    event_id = self._format_event_id(self._next_event_id)
                    self._next_event_id += 1
                    event = ProfileRuntimeEvent(
                        id=event_id, event="runtime_state", data=data
                    )
                    self._history.append(event)
                    initial_events.append(event)

            # Register only after the snapshot/catch-up is built while holding the
            # same lock as publish(), so no live event can fall into the gap.
            self._subscribers.add(q)

        try:
            for event in initial_events:
                payload = event.data.model_dump_json()
                yield f"id: {event.id}\nevent: {event.event}\ndata: {payload}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
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

        self._last_errors: dict[str, str | None] = {}
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._publish_tasks: set[asyncio.Task[None]] = set()
        self._client: httpx.AsyncClient | None = None
        self._running: bool = False

    def is_enabled(self) -> bool:
        return bool(self.supervisor_url and self._token_str)

    def get_last_error(self, profile_id: str) -> str | None:
        return self._last_errors.get(profile_id)

    def set_last_error(self, profile_id: str, error: str | None) -> None:
        if error is None:
            self._last_errors.pop(profile_id, None)
        else:
            self._last_errors[profile_id] = error

    def clear_last_error(self, profile_id: str) -> None:
        self._last_errors.pop(profile_id, None)

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

    async def publish_profile_change(self, profile_id: str) -> None:
        try:
            rt = await self.profile_service.get_runtime(profile_id)
            err = self.get_last_error(profile_id)
            data = ProfileRuntimeEventData(
                profile_id=rt.profile_id,
                desired_state=rt.desired_state,
                observed_state=rt.observed_state,
                runtime_instance_id=rt.runtime_instance_id,
                failure_count=rt.failure_count,
                restart_blocked=rt.restart_blocked,
                last_coordinator_error=err,
                updated_at=rt.updated_at,
            )
            await self.broadcaster.publish(data)
        except ProfileNotFoundError:
            pass
        except Exception as e:  # noqa: BLE001 - event broadcaster boundary protects coordinator loop
            logger.warning("Error publishing profile runtime change: %s", e)

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

        if runtime.restart_blocked:
            self.set_last_error(profile_id, "Restart blocked; manual retry required")
            await self.publish_profile_change(profile_id)
            return ReconcileOutcome.TERMINATED

        if (
            runtime.observed_state == "running"
            and runtime.runtime_instance_id is not None
        ):
            self.clear_last_error(profile_id)
            return ReconcileOutcome.CONVERGED

        try:
            versions = await self.profile_service.list_config_versions(profile_id)
            latest_v = max(
                (v.version for v in versions), default=runtime.config_version
            )
        except Exception:  # noqa: BLE001 - config version query failure safely falls back to current runtime version
            latest_v = runtime.config_version

        req_body = {
            "profile_id": profile_id,
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
            self.set_last_error(profile_id, err_msg)
            await self.publish_profile_change(profile_id)
            return ReconcileOutcome.RETRYABLE

        if resp.status_code == 200:
            self.clear_last_error(profile_id)
            await self.publish_profile_change(profile_id)
            return ReconcileOutcome.CONVERGED

        detail = ""
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:  # noqa: BLE001 - non-dict or invalid JSON fallback to raw text
            detail = resp.text
        err_msg = f"Supervisor start failed ({resp.status_code}): {detail}"
        self.set_last_error(profile_id, err_msg)
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
                err_msg = f"Supervisor status failed ({st_resp.status_code})"
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
            self.clear_last_error(profile_id)
            await self.publish_profile_change(profile_id)
            return ReconcileOutcome.CONVERGED

        detail = ""
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:  # noqa: BLE001 - non-dict or invalid JSON fallback to raw text
            detail = resp.text
        err_msg = f"Supervisor stop failed ({resp.status_code}): {detail}"
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
