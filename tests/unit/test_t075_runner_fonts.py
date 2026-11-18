"""t075 AC-005/006: the Runner <-> font-verification seam, for real.

The egress tests stub ``verify_mounted_font_set`` (their subject is
the SDK launch kwargs).  These tests do the opposite: a real font set
is imported onto a patched mount root, the Runner runs the real
``prepare_profile_fontconfig`` + ``verify_mounted_font_set`` path
(real fc-list, real sha256, real FreeType render proof), and the
assertions cover what the seam must do — launch the browser and
publish the verified verdict into ``runner_info.json`` on success;
write the error state, raise, and never launch on a tampered mount.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cbrowser.domain.models import ConfigVersionSnapshot, ProfileConfig
from cbrowser.font_sets import import_font_set
from cbrowser.runtime_agent.runner import FontConfigUnavailableError

CJK_FONT = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
LATIN_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

needs_real_fonts = pytest.mark.skipif(
    not CJK_FONT.is_file() or not LATIN_FONT.is_file(),
    reason="fixture fonts unavailable",
)


def _import_real_set(tmp_path: Path) -> tuple[Path, str]:
    """Import the real Latin + CJK fonts as a windows set; return
    ``(mount_root, set_id)`` with a production-shaped manifest."""
    source = tmp_path / "font-src"
    source.mkdir()
    shutil.copyfile(CJK_FONT, source / CJK_FONT.name)
    shutil.copyfile(LATIN_FONT, source / LATIN_FONT.name)
    mount_root = tmp_path / "fonts"
    result = import_font_set("windows", [str(source)], "v1", root=str(mount_root))
    return mount_root, result["set_id"]


def _runner_with_mocks(runner_mod, tmp_path: Path, mount_root: Path, set_id: str, launch):
    """Build a BrowserRunner whose launch seams are mocked, but whose
    fontconfig preparation and mount verification run for real."""
    import cbrowser.runtime_agent.fontconfig as fontconfig_mod

    run_dir = tmp_path / "run"
    user_dir = tmp_path / "profile"
    run_dir.mkdir()
    user_dir.mkdir()
    snap_path = run_dir / "snapshot.json"
    cfg = ProfileConfig(
        name="p1",
        font_set_id=set_id,
        include_cjk_fonts=True,
        proxy_id=None,
        geoip=False,
    )
    snap = ConfigVersionSnapshot(
        id="snap_1",
        profile_id="prof_1",
        version=1,
        config=cfg.model_dump(),
        proxy_credential_revision=None,
        created_at="2026-11-15T00:00:00+00:00",
    )
    snap_path.write_text(snap.model_dump_json(), encoding="utf-8")

    # The mount root is a module constant in both modules; point both
    # at the fixture root so fontconfig generation and verification
    # agree on the mount the instance receives.
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(runner_mod, "FONT_SET_MOUNT_ROOT", mount_root)
    monkeypatch.setattr(fontconfig_mod, "FONT_SET_MOUNT_ROOT", mount_root)
    runner = runner_mod.BrowserRunner(
        profile_id="prof_1",
        runtime_instance_id="inst_1",
        config_snapshot_path=snap_path,
        run_dir=run_dir,
        user_data_dir=user_dir,
        engine_build="146.0.7680.177.3",
    )
    wrapper = tmp_path / "chrome-wrapper"
    wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(runner, "resolve_engine_binary", lambda: wrapper)
    monkeypatch.setattr(runner, "setup_pulse", lambda: (run_dir / "pulse.sock", run_dir / "cookie"))
    monkeypatch.setattr(runner, "setup_display", lambda width, height: run_dir / "Xauth")
    monkeypatch.setattr(runner, "_resolve_browser_version", AsyncMock(return_value=("Chrome/146", "UA")))
    monkeypatch.setattr(runner, "_configure_window", AsyncMock())
    monkeypatch.setattr(
        runner_mod,
        "run_search_defaults_initialization",
        AsyncMock(return_value=SimpleNamespace(state="applied", error_kind=None)),
    )
    monkeypatch.setattr(runner_mod, "launch_persistent_context_async", launch)
    return runner, run_dir, user_dir, monkeypatch


class _Resp:
    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def read(self) -> bytes:
        return json.dumps(
            {"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/1"}
        ).encode("utf-8")


@pytest.mark.asyncio
@needs_real_fonts
async def test_runner_launches_and_publishes_verified_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cbrowser.runtime_agent.runner as runner_mod

    mount_root, set_id = _import_real_set(tmp_path)
    launched: dict = {}

    class _FakeContext:
        pages: list = []

        async def close(self) -> None:
            return None

    async def fake_launch(**kwargs):
        launched.update(kwargs)
        (tmp_path / "run" / "chrome.pid").write_text(
            str(os.getpid()), encoding="utf-8"
        )
        (tmp_path / "profile" / "DevToolsActivePort").write_text(
            "9222\n/devtools/browser/1\n", encoding="utf-8"
        )
        return _FakeContext()

    monkeypatch.setattr(runner_mod.urllib.request, "urlopen", lambda *_a, **_k: _Resp())
    guard = SimpleNamespace(start=AsyncMock(return_value=9333), close=AsyncMock())
    monkeypatch.setattr(runner_mod, "CdpGuard", lambda *_a, **_k: guard)
    runner, run_dir, _user_dir, ctx = _runner_with_mocks(
        runner_mod, tmp_path, mount_root, set_id, fake_launch
    )
    try:
        await runner.start()
        assert launched, "the browser must launch once the mount verifies"
        assert runner.font_verification is not None
        assert runner.font_verification["status"] == "verified"
        assert runner.font_verification["font_set_id"] == set_id
        info = json.loads((run_dir / "runner_info.json").read_text())
        assert info["font_verification"]["status"] == "verified"
        assert info["font_verification"]["font_set_id"] == set_id
        state = runner.event_storage.get_instance_state("prof_1", "inst_1")
        assert state is not None and state.state == "running"
    finally:
        await runner.stop()
        ctx.undo()


@pytest.mark.asyncio
@needs_real_fonts
async def test_runner_refuses_tampered_mount_and_never_launches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cbrowser.runtime_agent.runner as runner_mod

    mount_root, set_id = _import_real_set(tmp_path)
    # Substitute the CJK file's bytes after import: same names, broken hash.
    (mount_root / "windows" / set_id / CJK_FONT.name).write_bytes(
        b"not a font at all"
    )
    launch_mock = AsyncMock()
    monkeypatch.setattr(
        runner_mod, "launch_persistent_context_async", launch_mock
    )
    runner, run_dir, _user_dir, ctx = _runner_with_mocks(
        runner_mod, tmp_path, mount_root, set_id, launch_mock
    )
    try:
        with pytest.raises(FontConfigUnavailableError):
            await runner.start()
        launch_mock.assert_not_awaited()
        state = runner.event_storage.get_instance_state("prof_1", "inst_1")
        assert state is not None
        assert state.state == "error"
        assert state.exit_reason == "font_set_unavailable"
        assert not (run_dir / "runner_info.json").exists()
        assert runner.font_verification is None
    finally:
        ctx.undo()
