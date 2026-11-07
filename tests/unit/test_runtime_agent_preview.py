from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest
from cbrowser.preview import (
    JPEG_QUALITY,
    PREVIEW_WIDTH,
    PreviewMeta,
    PreviewPolicy,
    preview_dir,
    read_meta,
    read_policy,
    write_policy,
)
from cbrowser.runtime_agent.agent import create_agent_app
from cbrowser.runtime_agent.preview_capture import PreviewCaptureLoop


class _FakeCdp:
    def __init__(
        self, vw: int = 1280, vh: int = 800, data: bytes = b"\xff\xd8jpeg"
    ) -> None:
        self.calls: list[tuple[str, dict, str | None]] = []
        self.vw = vw
        self.vh = vh
        self.data = data
        self.on_capture = None

    async def send(self, method, params, session=None):
        self.calls.append((method, params, session))
        if method == "Target.getTargets":
            return {
                "targetInfos": [
                    {"type": "page", "targetId": "tid-1"},
                    {"type": "other", "targetId": "tid-2"},
                    {"type": "page", "targetId": "tid-3"},
                ]
            }
        if method == "Target.attachToTarget":
            return {"sessionId": "sess-1"}
        if method == "Page.getLayoutMetrics":
            return {
                "cssLayoutViewport": {
                    "clientWidth": self.vw,
                    "clientHeight": self.vh,
                }
            }
        if method == "Page.captureScreenshot":
            if self.on_capture is not None:
                self.on_capture()
            return {"data": base64.b64encode(self.data).decode("ascii")}
        raise AssertionError(f"unexpected method: {method}")


def _runner_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "runner_info.json").write_text(
        json.dumps(
            {
                "profile_id": "p1",
                "runtime_instance_id": "inst-1",
                "config_version": 1,
                "display": ":99",
                "browser_ws_url": "ws://127.0.0.1:9222/cdp",
            }
        ),
        encoding="utf-8",
    )
    return run_dir


@pytest.mark.asyncio
async def test_capture_once_scales_clip_and_commits_without_activation(
    tmp_path: Path,
) -> None:
    directory = preview_dir(tmp_path, "p1")
    write_policy(
        directory,
        PreviewPolicy(enabled=True, epoch=5, runtime_instance_id="inst-1"),
    )
    fake = _FakeCdp(vw=1280, vh=800)
    loop = PreviewCaptureLoop(directory, fake.send, "inst-1")

    await loop.capture_once()

    shot = [c for c in fake.calls if c[0] == "Page.captureScreenshot"]
    assert len(shot) == 1
    params = shot[0][1]
    assert params["format"] == "jpeg"
    assert params["quality"] == JPEG_QUALITY
    assert params["clip"]["x"] == 0
    assert params["clip"]["y"] == 0
    assert params["clip"]["width"] == 1280
    assert params["clip"]["height"] == 800
    assert params["clip"]["scale"] == PREVIEW_WIDTH / 1280
    assert shot[0][2] == "sess-1"

    attach = [c for c in fake.calls if c[0] == "Target.attachToTarget"]
    assert len(attach) == 1
    assert attach[0][1]["targetId"] == "tid-1"
    assert attach[0][1]["flatten"] is True
    assert attach[0][2] is None

    methods = [c[0] for c in fake.calls]
    assert "Target.activateTarget" not in methods
    assert "Page.bringToFront" not in methods

    assert (directory / "latest.jpg").read_bytes() == b"\xff\xd8jpeg"
    meta = read_meta(directory)
    assert meta is not None
    assert meta.policy_epoch == 5
    assert meta.runtime_instance_id == "inst-1"
    assert loop.last_captured_at == meta.captured_at


@pytest.mark.asyncio
async def test_disabled_policy_skips_capture(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    write_policy(
        directory,
        PreviewPolicy(enabled=False, epoch=5, runtime_instance_id="inst-1"),
    )
    fake = _FakeCdp()
    loop = PreviewCaptureLoop(directory, fake.send, "inst-1")

    await loop.capture_once()

    assert fake.calls == []
    assert loop.last_captured_at is None
    assert not (directory / "latest.jpg").exists()


@pytest.mark.asyncio
async def test_missing_policy_skips_capture(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    fake = _FakeCdp()
    loop = PreviewCaptureLoop(directory, fake.send, "inst-1")

    await loop.capture_once()

    assert fake.calls == []
    assert loop.last_captured_at is None


@pytest.mark.asyncio
async def test_rejected_commit_does_not_update_captured_at(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    write_policy(
        directory,
        PreviewPolicy(enabled=True, epoch=5, runtime_instance_id="inst-1"),
    )
    fake = _FakeCdp()

    def revoke() -> None:
        write_policy(
            directory,
            PreviewPolicy(enabled=False, epoch=6, runtime_instance_id="inst-1"),
        )

    fake.on_capture = revoke
    loop = PreviewCaptureLoop(directory, fake.send, "inst-1")

    await loop.capture_once()

    assert loop.last_captured_at is None
    assert not (directory / "latest.jpg").exists()
    assert read_meta(directory) is None


@pytest.mark.asyncio
async def test_health_details_include_preview_captured_at(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    loop = PreviewCaptureLoop(directory, _FakeCdp().send, "inst-1")
    loop.last_captured_at = "2026-11-08T00:00:00+00:00"
    app = create_agent_app(
        run_dir=_runner_dir(tmp_path),
        default_download_dir=tmp_path / "downloads",
        preview_loop=loop,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://agent"
    ) as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.json()["details"]["preview_captured_at"] == "2026-11-08T00:00:00+00:00"


@pytest.mark.asyncio
async def test_control_preview_policy_updates_in_memory_policy(
    tmp_path: Path,
) -> None:
    directory = preview_dir(tmp_path, "p1")
    loop = PreviewCaptureLoop(directory, _FakeCdp().send, "inst-1")
    app = create_agent_app(
        run_dir=_runner_dir(tmp_path),
        default_download_dir=tmp_path / "downloads",
        preview_loop=loop,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://agent"
    ) as client:
        resp = await client.post(
            "/control",
            json={
                "action": "preview_policy",
                "params": {
                    "enabled": True,
                    "epoch": 7,
                    "runtime_instance_id": "inst-1",
                    "request_id": "r1",
                },
            },
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert loop.policy == PreviewPolicy(
        enabled=True, epoch=7, runtime_instance_id="inst-1"
    )
    assert read_policy(directory) is None


@pytest.mark.asyncio
async def test_set_policy_is_epoch_monotonic_and_never_writes(tmp_path: Path) -> None:
    cdp = _FakeCdp()
    directory = preview_dir(tmp_path, "p1")
    loop = PreviewCaptureLoop(directory, cdp.send, "inst-1")
    loop.set_policy(enabled=True, epoch=9, runtime_instance_id="inst-1")
    assert loop.policy == PreviewPolicy(
        enabled=True, epoch=9, runtime_instance_id="inst-1"
    )
    loop.set_policy(enabled=True, epoch=8, runtime_instance_id="inst-1")
    assert loop.policy.epoch == 9
    assert read_policy(directory) is None


@pytest.mark.asyncio
async def test_stale_uds_cannot_reenable_capture_after_revocation(
    tmp_path: Path,
) -> None:
    cdp = _FakeCdp()
    directory = preview_dir(tmp_path, "p1")
    write_policy(
        directory,
        PreviewPolicy(enabled=False, epoch=10, runtime_instance_id="inst-1"),
    )
    loop = PreviewCaptureLoop(directory, cdp.send, "inst-1")
    loop.set_policy(enabled=True, epoch=10, runtime_instance_id="inst-1")
    loop.set_policy(enabled=True, epoch=9, runtime_instance_id="inst-1")
    assert loop.policy.epoch == 10
    await loop.capture_once()
    assert not (directory / "latest.jpg").exists()
    assert read_meta(directory) is None
