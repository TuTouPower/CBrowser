from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from cbrowser.preview import (
    PreviewPolicy,
    preview_dir,
    read_policy,
    write_policy,
)
from cbrowser.runtime_agent.agent import create_agent_app
from cbrowser.runtime_agent.preview_capture import PreviewCaptureLoop


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
async def test_disabled_policy_skips_capture(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    write_policy(
        directory,
        PreviewPolicy(enabled=False, epoch=5, runtime_instance_id="inst-1"),
    )
    loop = PreviewCaptureLoop(
        directory,
        ":99",
        "inst-1",
        capture=lambda _d: pytest.fail("capture must be skipped"),
    )

    await loop.capture_once()

    assert loop.last_captured_at is None
    assert not (directory / "latest.jpg").exists()


@pytest.mark.asyncio
async def test_missing_policy_skips_capture(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    loop = PreviewCaptureLoop(
        directory,
        ":99",
        "inst-1",
        capture=lambda _d: pytest.fail("capture must be skipped"),
    )

    await loop.capture_once()

    assert loop.last_captured_at is None


@pytest.mark.asyncio
async def test_health_details_include_preview_captured_at(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    loop = PreviewCaptureLoop(directory, ":99", "inst-1")
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
    loop = PreviewCaptureLoop(directory, ":99", "inst-1")
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
    directory = preview_dir(tmp_path, "p1")
    loop = PreviewCaptureLoop(directory, ":99", "inst-1")
    loop.set_policy(enabled=True, epoch=9, runtime_instance_id="inst-1")
    assert loop.policy == PreviewPolicy(
        enabled=True, epoch=9, runtime_instance_id="inst-1"
    )
    loop.set_policy(enabled=True, epoch=8, runtime_instance_id="inst-1")
    assert loop.policy.epoch == 9
    assert read_policy(directory) is None
