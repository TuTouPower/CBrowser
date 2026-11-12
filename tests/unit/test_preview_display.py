"""Whole-display capture and strict JPEG validation, without host screenshots."""

from __future__ import annotations

import io

import pytest
from cbrowser.preview import PreviewPolicy, read_meta, write_policy
from cbrowser.runtime_agent import preview_capture
from PIL import Image


def jpeg(size=(480, 300), color="white", format="JPEG"):
    with io.BytesIO() as output:
        Image.new("RGB", size, color).save(output, format)
        return output.getvalue()


@pytest.mark.asyncio
async def test_display_capture_resizes_entire_frame_including_browser_chrome(
    tmp_path, monkeypatch
):
    image = Image.new("RGB", (1280, 800), "blue")
    image.paste("red", (0, 0, 1280, 80))
    seen = []

    def grab(*, xdisplay):
        seen.append(xdisplay)
        return image

    monkeypatch.setattr(preview_capture.ImageGrab, "grab", grab)
    monkeypatch.setattr(preview_capture.sys, "platform", "linux")
    directory = tmp_path / "preview"
    write_policy(
        directory, PreviewPolicy(enabled=True, epoch=2, runtime_instance_id="i")
    )
    loop = preview_capture.PreviewCaptureLoop(directory, ":99", "i")
    await loop.capture_once()
    assert seen == [":99"]
    meta = read_meta(directory)
    from cbrowser.preview import read_preview

    _metadata, data = read_preview(
        directory,
        loop.policy or preview_capture.read_policy(directory),
        epoch=2,
        runtime_instance_id="i",
    )
    with Image.open(io.BytesIO(data)) as actual:
        assert actual.size == (480, 300)
        assert actual.getpixel((240, 10))[0] > 200
        assert actual.getpixel((240, 200))[2] > 200
    assert meta.captured_at == loop.last_captured_at


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data,size",
    [
        (b"not JPEG", (480, 300)),
        (jpeg()[:-20], (480, 300)),
        (jpeg()[:-1000] + b"\xff\xd9", (480, 300)),
        (jpeg(format="PNG"), (480, 300)),
        (jpeg(size=(400, 300)), (480, 300)),
    ],
)
async def test_invalid_frames_never_commit_or_update_timestamp(
    tmp_path, caplog, data, size
):
    write_policy(
        tmp_path, PreviewPolicy(enabled=True, epoch=2, runtime_instance_id="i")
    )
    loop = preview_capture.PreviewCaptureLoop(
        tmp_path, ":99", "i", capture=lambda _display: (data, size)
    )
    await loop.capture_once()
    assert read_meta(tmp_path) is None
    assert loop.last_captured_at is None
    assert list(tmp_path.glob("*.jpg")) == []
    assert "Preview frame rejected" in caplog.text


@pytest.mark.asyncio
async def test_legal_solid_jpeg_is_accepted(tmp_path):
    write_policy(
        tmp_path, PreviewPolicy(enabled=True, epoch=2, runtime_instance_id="i")
    )
    loop = preview_capture.PreviewCaptureLoop(
        tmp_path, ":99", "i", capture=lambda _display: (jpeg(), (480, 300))
    )
    await loop.capture_once()
    assert read_meta(tmp_path).captured_at == loop.last_captured_at


@pytest.mark.parametrize("display", ["", "localhost:0", ":x", None])
def test_display_requires_explicit_local_x11_without_host_fallback(
    display, monkeypatch
):
    monkeypatch.setattr(
        preview_capture.ImageGrab,
        "grab",
        lambda **kwargs: pytest.fail("host screenshot attempted"),
    )
    with pytest.raises(ValueError):
        preview_capture.capture_display(display)


@pytest.mark.asyncio
async def test_live_disabled_file_blocks_stale_uds_before_display_read(tmp_path):
    write_policy(
        tmp_path, PreviewPolicy(enabled=False, epoch=10, runtime_instance_id="i")
    )
    loop = preview_capture.PreviewCaptureLoop(
        tmp_path,
        ":99",
        "i",
        capture=lambda _display: pytest.fail("revoked display must not be read"),
    )
    loop.set_policy(enabled=True, epoch=10, runtime_instance_id="i")
    await loop.capture_once()
    assert read_meta(tmp_path) is None
    assert loop.last_captured_at is None


@pytest.mark.asyncio
async def test_agent_startup_passes_runner_xauthority_to_display_capture(
    tmp_path, monkeypatch
):
    import json
    import os

    from cbrowser.runtime_agent import agent

    run = tmp_path / "run"
    run.mkdir()
    authority = run / "Xauthority"
    authority.write_bytes(b"fixture")
    (run / "runner_info.json").write_text(
        json.dumps(
            {
                "profile_id": "profile_a",
                "runtime_instance_id": "instance_a",
                "config_version": 1,
                "browser_ws_url": "ws://127.0.0.1:9222/x",
                "display": ":99",
                "xauth_path": str(authority),
            }
        )
    )
    monkeypatch.setenv("PROFILE_ID", "profile_a")
    monkeypatch.setenv("RUNTIME_INSTANCE_ID", "instance_a")
    monkeypatch.setenv("XAUTHORITY", "/unrelated-authority")

    class Proxy:
        def __init__(self, **kwargs):
            pass

        async def start(self):
            pass

        async def reconcile_downloads(self):
            pass

        async def close(self):
            pass

    class Server:
        def __init__(self, config):
            pass

        async def serve(self, **kwargs):
            assert os.environ["XAUTHORITY"] == str(authority)

    class Listener:
        def bind(self, path):
            Path(path).touch()

        def setblocking(self, value):
            pass

        def close(self):
            pass

    from pathlib import Path

    monkeypatch.setattr(agent.socket, "socket", lambda *args: Listener())
    monkeypatch.setattr(agent, "CdpProxyManager", Proxy)
    monkeypatch.setattr(agent.uvicorn, "Server", Server)
    await agent.run_uds_agent(
        run, tmp_path / "downloads", uds_path=tmp_path / "agent.sock"
    )


@pytest.mark.parametrize("failure", ["missing", "timeout"])
def test_strict_decoder_missing_or_timeout_rejects_frame(monkeypatch, failure):
    import subprocess

    def fail(*args, **kwargs):
        if failure == "missing":
            raise FileNotFoundError("jpeginfo")
        raise subprocess.TimeoutExpired("jpeginfo", 2.0)

    monkeypatch.setattr(subprocess, "run", fail)
    assert not preview_capture.valid_frame(jpeg(), (480, 300))
