"""Event delivery must preserve filesystem and runtime-instance boundaries."""

import json
import secrets
from types import SimpleNamespace

import httpx
import pytest
from aiohttp import web
from cbrowser.supervisor.core import ActiveSession, SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator


@pytest.mark.asyncio
async def test_actual_http_delivery_resumes_after_listener_restart(tmp_path):
    token = secrets.token_urlsafe(32)
    token_file = tmp_path / "service_key"
    token_file.write_text(token)
    token_file.chmod(0o600)
    received = []

    async def receive(request):
        assert request.headers["Authorization"] == f"Bearer {token}"
        received.append(await request.json())
        return web.json_response({"status": "ok", "outcome": "applied"})

    app = web.Application()
    app.router.add_post("/api/v1/internal/supervisor/runtimes/events", receive)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    await site.stop()
    forwarder = EventForwarder(
        f"http://127.0.0.1:{port}", tmp_path / "spool", token_file=token_file
    )
    try:
        assert not await forwarder.emit_event(
            "event", "profile", "runtime", "exit", 137
        )
        assert len(list((tmp_path / "spool").glob("*.json"))) == 1
        await web.TCPSite(runner, "127.0.0.1", port).start()
        assert await forwarder.replay_spooled_events() == 1
        assert received[0]["event_id"] == "event"
        assert not list((tmp_path / "spool").glob("*.json"))
        await forwarder.close()
        restarted = EventForwarder(
            f"http://127.0.0.1:{port}", tmp_path / "spool", token_file=token_file
        )
        # Files are not a durable dedupe ledger: a restarted Supervisor may
        # resend the same event_id, and API event_id uniqueness absorbs it.
        assert await restarted.emit_event("event", "profile", "runtime", "exit", 137)
        assert len(received) == 2
        await restarted.close()
    finally:
        await forwarder.close()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_event_identifier_cannot_escape_spool_directory(tmp_path):
    forwarder = EventForwarder("http://127.0.0.1:1", tmp_path / "spool")
    try:
        assert not await forwarder.emit_event(
            "../escaped",
            "profile",
            "runtime",
            "exit",
            0,
            "normal",
        )
        assert not (tmp_path / "escaped.json").exists()
        assert not (tmp_path / "escaped.tmp").exists()
        queued = list((tmp_path / "spool").glob("*.json"))
        assert len(queued) == 1
        assert json.loads(queued[0].read_text())["event_id"] == "../escaped"
    finally:
        await forwarder.close()


@pytest.mark.asyncio
async def test_spool_envelope_carries_version(tmp_path):
    forwarder = EventForwarder("http://127.0.0.1:1", tmp_path / "spool")
    try:
        assert not await forwarder.emit_event(
            "event", "profile", "runtime", "exit", 1
        )
        queued = json.loads(next((tmp_path / "spool").glob("*.json")).read_text())
        assert queued["version"] == 1
        assert queued["event_id"] == "event"
    finally:
        await forwarder.close()


@pytest.mark.asyncio
async def test_replay_accepts_legacy_unversioned_event(tmp_path):
    received = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(json.loads(request.content))
        return httpx.Response(200, json={"status": "ok", "outcome": "applied"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://api"
    ) as client:
        forwarder = EventForwarder("http://api", tmp_path / "spool", client=client)
        legacy = {
            "event_id": "legacy",
            "profile_id": "profile",
            "runtime_instance_id": "runtime",
            "event_type": "exit",
            "exit_code": 0,
            "exit_reason": "normal",
            "config_version": 1,
            "payload": {},
        }
        (tmp_path / "spool" / "legacy.json").write_text(
            json.dumps(legacy), encoding="utf-8"
        )
        assert await forwarder.replay_spooled_events() == 1
        assert received == [legacy]
        assert not (tmp_path / "spool" / "legacy.json").exists()


@pytest.mark.asyncio
async def test_replay_quarantines_unsupported_envelope_version(tmp_path):
    forwarder = EventForwarder("http://127.0.0.1:1", tmp_path / "spool")
    try:
        future = {
            "version": 99,
            "event_id": "future",
            "profile_id": "profile",
            "runtime_instance_id": "runtime",
            "event_type": "exit",
            "exit_code": 0,
            "exit_reason": "normal",
            "config_version": 1,
            "payload": {},
        }
        (tmp_path / "spool" / "future.json").write_text(
            json.dumps(future), encoding="utf-8"
        )
        assert await forwarder.replay_spooled_events() == 0
        assert not (tmp_path / "spool" / "future.json").exists()
        assert (tmp_path / "spool" / "quarantine" / "future.json").is_file()
    finally:
        await forwarder.close()


@pytest.mark.asyncio
async def test_old_normal_exit_cannot_remove_new_local_runtime(tmp_path):
    received = []

    async def receive(request):
        event = await request.json()
        received.append(event["event_id"])
        return web.json_response({"status": "ok", "outcome": "stale_instance"})

    app = web.Application()
    app.router.add_post("/api/v1/internal/supervisor/runtimes/events", receive)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    api = httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False)
    events = EventForwarder(str(api.base_url), tmp_path / "spool", client=api)
    core = SupervisorCore(
        SimpleNamespace(validator=PathValidator(tmp_path)), PortAllocator(), events, api
    )
    current = ActiveSession("profile", "new_runtime", 1, 30000, "browser", "stream")
    core._sessions["profile"] = current
    directory = (
        tmp_path / "runtime-events" / "profile" / "events" / "runtime" / "old_runtime"
    )
    directory.mkdir(parents=True)
    (directory / "exit.json").write_text(
        json.dumps(
            {
                "event_id": "old_exit",
                "profile_id": "profile",
                "runtime_instance_id": "old_runtime",
                "event_type": "exit",
                "exit_code": 0,
                "exit_reason": "normal",
                "config_version": 1,
            }
        )
    )
    try:
        await core.consume_disk_events()
        assert core.get_session("profile") is current
        # Durable acknowledgements avoid re-uploading an entire native journal.
        await core.consume_disk_events()
        assert received == ["old_exit"]
        await api.aclose()
        restarted = EventForwarder(f"http://127.0.0.1:{port}", tmp_path / "spool")
        core.events = restarted
        await core.consume_disk_events()
        assert received == ["old_exit"]
        await restarted.close()
    finally:
        await api.aclose()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_profile_event_directory_cannot_impersonate_another_profile(tmp_path):
    received = []

    async def receive(request):
        received.append(await request.json())
        return web.json_response({"status": "ok", "outcome": "applied"})

    app = web.Application()
    app.router.add_post("/api/v1/internal/supervisor/runtimes/events", receive)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    api = httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False)
    events = EventForwarder(str(api.base_url), tmp_path / "spool", client=api)
    core = SupervisorCore(
        SimpleNamespace(validator=PathValidator(tmp_path)), PortAllocator(), events, api
    )
    directory = (
        tmp_path / "runtime-events" / "profile_a" / "events" / "runtime" / "runtime_a"
    )
    directory.mkdir(parents=True)
    (directory / "forged.json").write_text(
        json.dumps(
            {
                "event_id": "forged",
                "profile_id": "profile_b",
                "runtime_instance_id": "runtime_b",
                "event_type": "exit",
                "exit_code": 0,
                "exit_reason": "normal",
                "config_version": 1,
            }
        )
    )
    try:
        await core.consume_disk_events()
        assert received == []
    finally:
        await api.aclose()
        await runner.cleanup()


def _forwarder_with_status(tmp_path, status_code: int) -> EventForwarder:
    def handler(request: httpx.Request) -> httpx.Response:
        if status_code == 200:
            return httpx.Response(200, json={"status": "ok", "outcome": "applied"})
        return httpx.Response(status_code, json={"detail": "nope"})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://api",
        trust_env=False,
    )
    return EventForwarder("http://api", tmp_path / "spool", client=client)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403, 408, 429, 500, 503])
async def test_retryable_statuses_keep_event_queued(tmp_path, status_code) -> None:
    """A8: auth/throttling/gateway failures are unavailable, never dead-letter."""
    from cbrowser.supervisor.event_forwarder import UNAVAILABLE

    forwarder = _forwarder_with_status(tmp_path, status_code)
    try:
        outcome = await forwarder.emit_event_with_outcome(
            "evt", "profile", "runtime", "lifecycle"
        )
        assert outcome == UNAVAILABLE
        assert len(list((tmp_path / "spool").glob("*.json"))) == 1
        assert not (tmp_path / "spool" / "quarantine").exists()
    finally:
        await forwarder.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 422])
async def test_permanent_rejection_dead_letters_event(tmp_path, status_code) -> None:
    """A8: a definite semantic rejection dead-letters the spool copy once."""
    from cbrowser.supervisor.event_forwarder import REJECTED

    forwarder = _forwarder_with_status(tmp_path, status_code)
    try:
        outcome = await forwarder.emit_event_with_outcome(
            "evt", "profile", "runtime", "lifecycle"
        )
        assert outcome == REJECTED
        assert not list((tmp_path / "spool").glob("*.json"))
        assert len(list((tmp_path / "spool" / "quarantine").glob("*.json"))) == 1
    finally:
        await forwarder.close()


async def _rejected_event_setup(tmp_path, monkeypatch=None):
    """Core + forwarder wired to an API that permanently refuses events."""
    received = []

    async def receive(request):
        received.append(await request.json())
        return web.json_response({"status": "ok", "outcome": "bogus_outcome"})

    app = web.Application()
    app.router.add_post("/api/v1/internal/supervisor/runtimes/events", receive)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    api = httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False)
    events = EventForwarder(str(api.base_url), tmp_path / "spool", client=api)
    core = SupervisorCore(
        SimpleNamespace(validator=PathValidator(tmp_path)), PortAllocator(), events, api
    )
    directory = (
        tmp_path / "runtime-events" / "profile" / "events" / "runtime" / "inst"
    )
    directory.mkdir(parents=True)
    journal = directory / "exit.json"
    journal.write_text(
        json.dumps(
            {
                "event_id": "rejected_exit",
                "profile_id": "profile",
                "runtime_instance_id": "inst",
                "event_type": "exit",
                "exit_code": 0,
                "exit_reason": "normal",
                "config_version": 1,
            }
        )
    )
    return core, events, api, runner, received, journal


@pytest.mark.asyncio
async def test_rejected_disk_event_dead_letters_exactly_once(tmp_path):
    """A8/f013: one rejected event produces exactly one dead letter — the
    journal original in the data quarantine; the forwarder's spool copy
    is discarded, not quarantined a second time."""
    core, events, api, runner, received, journal = await _rejected_event_setup(
        tmp_path
    )
    try:
        await core.consume_disk_events()
        dead_letters = list((tmp_path / "quarantine").rglob("exit.json"))
        assert len(dead_letters) == 1
        assert not (tmp_path / "spool" / "quarantine").exists() or not list(
            (tmp_path / "spool" / "quarantine").glob("*.json")
        )
        assert not journal.exists()
        # The cursor moved past it: a second scan does not redeliver.
        await core.consume_disk_events()
        assert len(received) == 1
    finally:
        await api.aclose()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_failed_quarantine_keeps_event_pending(tmp_path, monkeypatch):
    """A8/f013: when the dead-letter move itself fails, the cursor must
    not advance — the event stays pending and is attempted again."""
    core, events, api, runner, received, journal = await _rejected_event_setup(
        tmp_path
    )
    try:
        monkeypatch.setattr(core, "_quarantine_event_file", lambda *a: False)
        await core.consume_disk_events()
        assert journal.exists()
        await core.consume_disk_events()
        assert len(received) == 2  # retried, not silently skipped
    finally:
        await api.aclose()
        await runner.cleanup()
