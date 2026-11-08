"""A13: capture_once must detach any CDP session it attached on every exit
path (success, invalid viewport, metrics/screenshot/decode failure and
cancellation). A failing detach must not mask the original capture error,
and repeated captures must not linearly accumulate attached sessions."""

from __future__ import annotations

import asyncio
import base64
import binascii
from pathlib import Path

import pytest
from cbrowser.preview import PreviewPolicy, preview_dir, write_policy
from cbrowser.runtime_agent.preview_capture import PreviewCaptureLoop


class _SessionCdp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, str | None]] = []
        self.active = 0
        self.peak = 0
        self.session_seq = 0
        self.bad_viewport = False
        self.bad_data = False
        self.fail_on: str | None = None
        self.detach_error: BaseException | None = None
        self.cancel_on: str | None = None
        self.reached: asyncio.Event | None = None
        self.proceed: asyncio.Event | None = None

    async def send(self, method, params, session=None):
        self.calls.append((method, params, session))
        if self.fail_on == method:
            raise RuntimeError(f"injected {method} failure")
        if self.cancel_on == method:
            if self.reached is not None:
                self.reached.set()
            if self.proceed is not None:
                await self.proceed.wait()
            raise asyncio.CancelledError()
        if method == "Target.getTargets":
            return {"targetInfos": [{"type": "page", "targetId": "tid-1"}]}
        if method == "Target.attachToTarget":
            self.session_seq += 1
            self.active += 1
            self.peak = max(self.peak, self.active)
            return {"sessionId": f"sess-{self.session_seq}"}
        if method == "Target.detachFromTarget":
            self.active -= 1
            if self.detach_error is not None:
                raise self.detach_error
            return {}
        if method == "Page.getLayoutMetrics":
            if self.bad_viewport:
                return {
                    "cssLayoutViewport": {"clientWidth": 0, "clientHeight": 0}
                }
            return {
                "cssLayoutViewport": {"clientWidth": 1280, "clientHeight": 800}
            }
        if method == "Page.captureScreenshot":
            if self.bad_data:
                return {"data": "a"}
            return {"data": base64.b64encode(b"\xff\xd8jpeg").decode("ascii")}
        raise AssertionError(f"unexpected method: {method}")


def _loop(tmp_path: Path, cdp: _SessionCdp) -> PreviewCaptureLoop:
    directory = preview_dir(tmp_path, "p1")
    write_policy(
        directory,
        PreviewPolicy(enabled=True, epoch=1, runtime_instance_id="inst-1"),
    )
    return PreviewCaptureLoop(directory, cdp.send, "inst-1")


def _assert_detached(cdp: _SessionCdp) -> None:
    assert cdp.active == 0
    detaches = [c for c in cdp.calls if c[0] == "Target.detachFromTarget"]
    attaches = [c for c in cdp.calls if c[0] == "Target.attachToTarget"]
    assert len(detaches) == len(attaches) == 1
    assert detaches[0][1] == {"sessionId": "sess-1"}
    assert detaches[0][2] is None


@pytest.mark.asyncio
async def test_a13_success_detaches_session(tmp_path: Path) -> None:
    cdp = _SessionCdp()
    await _loop(tmp_path, cdp).capture_once()
    _assert_detached(cdp)


@pytest.mark.asyncio
async def test_a13_invalid_viewport_detaches_session(tmp_path: Path) -> None:
    cdp = _SessionCdp()
    cdp.bad_viewport = True
    await _loop(tmp_path, cdp).capture_once()
    _assert_detached(cdp)


@pytest.mark.asyncio
async def test_a13_metrics_failure_detaches_session(tmp_path: Path) -> None:
    cdp = _SessionCdp()
    cdp.fail_on = "Page.getLayoutMetrics"
    with pytest.raises(RuntimeError, match="injected Page.getLayoutMetrics"):
        await _loop(tmp_path, cdp).capture_once()
    _assert_detached(cdp)


@pytest.mark.asyncio
async def test_a13_screenshot_failure_detaches_session(tmp_path: Path) -> None:
    cdp = _SessionCdp()
    cdp.fail_on = "Page.captureScreenshot"
    with pytest.raises(RuntimeError, match="injected Page.captureScreenshot"):
        await _loop(tmp_path, cdp).capture_once()
    _assert_detached(cdp)


@pytest.mark.asyncio
async def test_a13_decode_failure_detaches_session(tmp_path: Path) -> None:
    cdp = _SessionCdp()
    cdp.bad_data = True
    with pytest.raises(binascii.Error):
        await _loop(tmp_path, cdp).capture_once()
    _assert_detached(cdp)


@pytest.mark.asyncio
async def test_a13_cancellation_detaches_session(tmp_path: Path) -> None:
    cdp = _SessionCdp()
    cdp.cancel_on = "Page.captureScreenshot"
    cdp.reached = asyncio.Event()
    cdp.proceed = asyncio.Event()
    loop = _loop(tmp_path, cdp)
    task = asyncio.create_task(loop.capture_once())
    await asyncio.wait_for(cdp.reached.wait(), timeout=1.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cdp.active == 0
    assert any(c[0] == "Target.detachFromTarget" for c in cdp.calls)


@pytest.mark.asyncio
async def test_a13_detach_failure_preserves_original_error(tmp_path: Path) -> None:
    cdp = _SessionCdp()
    cdp.fail_on = "Page.captureScreenshot"
    cdp.detach_error = RuntimeError("detach boom")
    with pytest.raises(RuntimeError, match="injected Page.captureScreenshot"):
        await _loop(tmp_path, cdp).capture_once()
    assert cdp.active == 0
    assert any(c[0] == "Target.detachFromTarget" for c in cdp.calls)


@pytest.mark.asyncio
async def test_a13_repeated_captures_do_not_accumulate_sessions(
    tmp_path: Path,
) -> None:
    cdp = _SessionCdp()
    loop = _loop(tmp_path, cdp)
    for _ in range(5):
        await loop.capture_once()
        assert cdp.active == 0
    assert cdp.peak == 1
    detaches = [c for c in cdp.calls if c[0] == "Target.detachFromTarget"]
    attaches = [c for c in cdp.calls if c[0] == "Target.attachToTarget"]
    assert len(detaches) == len(attaches) == 5
