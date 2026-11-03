"""Corrupt initialization markers must not silently suppress real setup."""

import asyncio
import json
from pathlib import Path

import pytest
from cbrowser.runtime_agent.profile_defaults import (
    SEARCH_ENGINE_MARKER_FILE,
    ProfileDefaultsError,
    initialize_profile_defaults,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "marker",
    [
        {
            "version": True,
            "google_default_applied": True,
            "engine_keyword": "google.com",
        },
        {
            "version": 1,
            "google_default_applied": "false",
            "engine_keyword": "google.com",
        },
        {"version": 1, "google_default_applied": True, "engine_keyword": "other"},
    ],
)
async def test_corrupt_marker_rejected_before_using_browser(
    tmp_path: Path, marker: dict
) -> None:
    path = tmp_path / SEARCH_ENGINE_MARKER_FILE
    original = json.dumps(marker)
    path.write_text(original)
    with pytest.raises(ProfileDefaultsError):
        await initialize_profile_defaults(None, tmp_path, set_google_default=True)
    assert path.read_text() == original


class _FakePage:
    def __init__(self, active_keyword: str | None) -> None:
        self._active_keyword = active_keyword
        self.closed = False

    async def goto(self, _url: str) -> None:
        return None

    async def evaluate(self, script: str):
        if "getSearchEnginesList" in script:
            if self._active_keyword is None:
                return None
            return {"name": "Google", "keyword": self._active_keyword}
        return False

    async def close(self) -> None:
        self.closed = True


class _FakeContext:
    def __init__(self, active_keyword: str | None) -> None:
        self._active_keyword = active_keyword
        self.pages: list[_FakePage] = []

    async def new_page(self) -> _FakePage:
        page = _FakePage(self._active_keyword)
        self.pages.append(page)
        return page


class _ExplodingContext:
    async def new_page(self):
        raise RuntimeError("browser page unavailable")


class _HangingContext:
    async def new_page(self):
        await asyncio.sleep(60)


@pytest.mark.asyncio
async def test_search_defaults_failure_is_recorded_not_raised(
    tmp_path: Path,
) -> None:
    """A55: an initialization exception leaves the browser usable and is
    recorded as an independent failed status."""
    from cbrowser.runtime_agent.profile_defaults import (
        read_search_defaults_status,
        run_search_defaults_initialization,
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    state = await run_search_defaults_initialization(
        _ExplodingContext(),
        tmp_path / "profile",
        run_dir,
        set_google_default=True,
        runtime_instance_id="instance_a",
    )
    assert state == "failed"
    status = read_search_defaults_status(run_dir)
    assert status is not None
    assert status["state"] == "failed"
    assert status["error_kind"] == "ProfileDefaultsError"
    assert status["runtime_instance_id"] == "instance_a"
    assert not (tmp_path / "profile" / SEARCH_ENGINE_MARKER_FILE).exists()


@pytest.mark.asyncio
async def test_search_defaults_timeout_is_recorded_not_raised(
    tmp_path: Path,
) -> None:
    """A55: a hanging initialization times out bounded and records failure."""
    from cbrowser.runtime_agent.profile_defaults import (
        read_search_defaults_status,
        run_search_defaults_initialization,
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    state = await run_search_defaults_initialization(
        _HangingContext(),
        tmp_path / "profile",
        run_dir,
        set_google_default=True,
        runtime_instance_id="instance_a",
        timeout_s=0.2,
    )
    assert state == "failed"
    status = read_search_defaults_status(run_dir)
    assert status is not None
    assert status["error_kind"] == "timeout"


@pytest.mark.asyncio
async def test_search_defaults_disabled_does_not_touch_browser(
    tmp_path: Path,
) -> None:
    """A55: with the switch off, initialization is not executed at all."""
    from cbrowser.runtime_agent.profile_defaults import (
        read_search_defaults_status,
        run_search_defaults_initialization,
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    state = await run_search_defaults_initialization(
        _ExplodingContext(),
        tmp_path / "profile",
        run_dir,
        set_google_default=False,
        runtime_instance_id="instance_a",
    )
    assert state == "disabled"
    status = read_search_defaults_status(run_dir)
    assert status is not None and status["state"] == "disabled"


@pytest.mark.asyncio
async def test_search_defaults_verified_success_writes_marker_and_status(
    tmp_path: Path,
) -> None:
    """A55: only a verified Google default records success (marker + status)."""
    from cbrowser.runtime_agent.profile_defaults import (
        read_search_defaults_status,
        run_search_defaults_initialization,
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    state = await run_search_defaults_initialization(
        _FakeContext("google.com"),
        profile_dir,
        run_dir,
        set_google_default=True,
        runtime_instance_id="instance_a",
    )
    assert state == "applied"
    marker = json.loads((profile_dir / SEARCH_ENGINE_MARKER_FILE).read_text())
    assert marker["google_default_applied"] is True
    status = read_search_defaults_status(run_dir)
    assert status is not None and status["state"] == "applied"


def _make_defaults_runner(root: Path):
    from cbrowser.runtime_agent.runner import BrowserRunner

    snapshot = root / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "id": "snapshot_defaults",
                "profile_id": "profile_a",
                "version": 1,
                "config": {"name": "Defaults runner", "set_google_default": True},
                "created_at": "2026-11-04T00:00:00+08:00",
            }
        )
    )
    runner = BrowserRunner(
        "profile_a",
        "instance_a",
        snapshot,
        root / "run",
        root / "profile",
        events_dir=root / "events",
        engine_cache_dir=root / "engine_cache",
    )
    (root / "run").mkdir(parents=True, exist_ok=True)
    (root / "profile").mkdir(parents=True, exist_ok=True)
    return runner


@pytest.mark.asyncio
async def test_runner_consumes_fenced_search_defaults_retry(tmp_path: Path) -> None:
    """A55: the runner retries against the live context only for its own
    instance; a repeated request_id does not re-run initialization."""
    from cbrowser.runtime_agent.profile_defaults import (
        SEARCH_DEFAULTS_RETRY_FILE,
        read_search_defaults_status,
    )

    runner = _make_defaults_runner(tmp_path)
    context = _FakeContext("google.com")
    runner.browser_context = context
    run_dir = tmp_path / "run"
    (run_dir / SEARCH_DEFAULTS_RETRY_FILE).write_text(
        json.dumps(
            {
                "profile_id": "profile_a",
                "runtime_instance_id": "instance_a",
                "request_id": "req-1",
            }
        )
    )
    assert await runner._process_search_defaults_retry() is True
    status = read_search_defaults_status(run_dir)
    assert status is not None and status["state"] == "applied"
    assert status["request_id"] == "req-1"
    assert len(context.pages) == 1

    (run_dir / SEARCH_DEFAULTS_RETRY_FILE).write_text(
        json.dumps(
            {
                "profile_id": "profile_a",
                "runtime_instance_id": "instance_a",
                "request_id": "req-1",
            }
        )
    )
    assert await runner._process_search_defaults_retry() is True
    assert len(context.pages) == 1  # idempotent: no second initialization


@pytest.mark.asyncio
async def test_runner_rejects_stale_instance_search_defaults_retry(
    tmp_path: Path,
) -> None:
    """A55: a retry naming a superseded instance is consumed and rejected
    without touching the browser."""
    from cbrowser.runtime_agent.profile_defaults import SEARCH_DEFAULTS_RETRY_FILE

    runner = _make_defaults_runner(tmp_path)
    context = _FakeContext("google.com")
    runner.browser_context = context
    run_dir = tmp_path / "run"
    (run_dir / SEARCH_DEFAULTS_RETRY_FILE).write_text(
        json.dumps(
            {
                "profile_id": "profile_a",
                "runtime_instance_id": "instance_old",
                "request_id": "req-9",
            }
        )
    )
    assert await runner._process_search_defaults_retry() is True
    assert len(context.pages) == 0


@pytest.mark.asyncio
async def test_existing_success_marker_preserves_later_manual_choice(
    tmp_path: Path,
) -> None:
    """A55: once the first initialization applied Google (marker written),
    later startups never re-run the UI flow — so a default the user picked
    manually afterwards is never overwritten by a subsequent launch."""
    path = tmp_path / SEARCH_ENGINE_MARKER_FILE
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "google_default_applied": True,
                "engine_keyword": "google.com",
            }
        )
    )

    class _ExplodingContext:
        async def new_page(self):  # noqa: D102 - any use proves a re-run happened
            raise AssertionError("initialization must not re-run after the marker")

    await initialize_profile_defaults(
        _ExplodingContext(), tmp_path, set_google_default=True
    )
