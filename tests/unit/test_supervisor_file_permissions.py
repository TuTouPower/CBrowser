"""Host Profile directories are owned by the runtime UID with least privilege."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.path_validator import PathValidator

BROWSER = "sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346"
STREAM = "sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531"


def _adapter(tmp_path: Path, **kwargs) -> DockerAdapter:
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    return DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=object(),
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
        **kwargs,
    )


def test_managed_directories_are_chowned_to_runtime_uid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter(tmp_path, manage_ownership=True)
    chown_calls: list[tuple[Path, int, int]] = []
    monkeypatch.setattr(
        os,
        "chown",
        lambda path, uid, gid: chown_calls.append((Path(path), uid, gid)),
    )
    dirs = adapter.prepare_profile_directories("p1")

    assert {(path.name, uid, gid) for path, uid, gid in chown_calls} >= {
        ("profile", 1000, 1000),
        ("p1", 1000, 1000),
        ("x11", 1000, 1000),
        ("pulse", 1000, 1000),
    }
    assert stat.S_IMODE(dirs["profile"].stat().st_mode) == 0o750
    assert stat.S_IMODE(dirs["runtime"].stat().st_mode) == 0o750
    assert stat.S_IMODE(dirs["events"].stat().st_mode) == 0o750
    assert stat.S_IMODE(dirs["exchange"].stat().st_mode) == 0o750
    assert stat.S_IMODE(dirs["x11"].stat().st_mode) == 0o1777


def test_host_direct_run_skips_chown_and_keeps_legacy_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter(tmp_path, manage_ownership=False)
    monkeypatch.setattr(
        os,
        "chown",
        lambda *_args: pytest.fail("host direct run must not chown user files"),
    )
    dirs = adapter.prepare_profile_directories("p1")

    assert stat.S_IMODE(dirs["profile"].stat().st_mode) == 0o777
    assert stat.S_IMODE(dirs["x11"].stat().st_mode) == 0o1777


def test_managed_ownership_failure_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter(tmp_path, manage_ownership=True)

    def deny(_path, _uid, _gid):
        raise PermissionError("not root")

    monkeypatch.setattr(os, "chown", deny)
    with pytest.raises(Exception, match="ownership"):
        adapter.prepare_profile_directories("p1")
