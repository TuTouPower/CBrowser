"""t080: Linux-native storage layout — volume naming and mount planning."""

from __future__ import annotations

from pathlib import Path

import pytest

from cbrowser.supervisor.path_validator import PathSecurityError
from cbrowser.supervisor.storage_layout import MountPlanner, volume_name
from cbrowser.supervisor.volume_spec import (
    browser_volumes,
    cache_init_volumes,
    stream_volumes,
)


def _planner(tmp_path: Path) -> MountPlanner:
    data_root = tmp_path / "data"
    return MountPlanner(
        resource_prefix="cbrowser",
        data_root=data_root,
        socket_root=data_root / "sockets",
        fonts_root=tmp_path / "fonts",
    )


def test_volume_names_derive_from_prefix() -> None:
    assert volume_name("cbrowser", "db") == "cbrowser-db"
    assert volume_name("cbrowser", "data") == "cbrowser-data"
    assert volume_name("cbrowser", "fonts") == "cbrowser-fonts"
    assert volume_name("cbrowser", "runtime") == "cbrowser-runtime"
    with pytest.raises(ValueError):
        volume_name("cbrowser", "bogus")


def test_planner_maps_profile_tree_to_data_volume(tmp_path: Path) -> None:
    planner = _planner(tmp_path)
    volume, subpath = planner.resolve(tmp_path / "data/profiles/p1/profile")
    assert volume == "cbrowser-data"
    assert subpath == "profiles/p1/profile"


def test_planner_maps_runtime_trees_to_runtime_volume(tmp_path: Path) -> None:
    planner = _planner(tmp_path)
    assert planner.resolve(tmp_path / "data/runtime/p1/x11") == (
        "cbrowser-runtime",
        "p1/x11",
    )
    assert planner.resolve(tmp_path / "data/control/gates/p1/inst/role") == (
        "cbrowser-runtime",
        "gates/p1/inst/role",
    )
    assert planner.resolve(tmp_path / "data/sockets/p1/inst") == (
        "cbrowser-runtime",
        "sockets/p1/inst",
    )
    assert planner.resolve(tmp_path / "data/runtime/.secrets/p1") == (
        "cbrowser-runtime",
        ".secrets/p1",
    )


def test_planner_maps_fonts_and_cache(tmp_path: Path) -> None:
    planner = _planner(tmp_path)
    assert planner.resolve(tmp_path / "fonts/windows/abc123") == (
        "cbrowser-fonts",
        "windows/abc123",
    )
    assert planner.resolve(tmp_path / "data/engine-cache/geoip") == (
        "cbrowser-data",
        "engine-cache/geoip",
    )


def test_planner_rejects_outside_and_volume_roots(tmp_path: Path) -> None:
    planner = _planner(tmp_path)
    with pytest.raises(PathSecurityError):
        planner.resolve(tmp_path / "elsewhere" / "file")
    with pytest.raises(PathSecurityError):
        planner.resolve(tmp_path / "data")
    with pytest.raises(PathSecurityError):
        planner.mount(tmp_path / "data/profiles/p1", "/x", mode="bad")


def test_planner_mount_is_typed_volume_subpath(tmp_path: Path) -> None:
    planner = _planner(tmp_path)
    mount = planner.mount(
        tmp_path / "fonts/windows/abc123", "/fonts/windows/abc123", "ro"
    )
    assert mount["Type"] == "volume"
    assert mount["Source"] == "cbrowser-fonts"
    assert mount["Target"] == "/fonts/windows/abc123"
    assert mount["ReadOnly"] is True
    assert mount["VolumeOptions"]["Subpath"] == "windows/abc123"


def test_browser_volumes_are_exact_subpath_mounts(tmp_path: Path) -> None:
    planner = _planner(tmp_path)
    data = tmp_path / "data"
    dirs = {
        "profile": data / "profiles/p1/profile",
        "events": data / "runtime-events/p1",
        "exchange": data / "artifacts/p1/downloads",
        "uploads": data / "artifacts/p1/uploads",
        "runtime": data / "runtime/p1",
        "x11": data / "runtime/p1/x11",
        "pulse": data / "runtime/p1/pulse",
        "preview": data / "profiles/p1/preview",
    }
    mounts = browser_volumes(
        planner=planner,
        profile_id="p1",
        dirs=dirs,
        gate=data / "control/gates/p1/inst/role",
        engine_cache=data / "engine-cache",
        geoip_cache=data / "engine-cache/geoip",
        credentials_path=data / "runtime/.secrets/p1/proxy_credentials.json",
    )
    by_target = {m["Target"]: m for m in mounts}
    profile_mount = by_target["/data/profiles/p1/profile"]
    assert profile_mount["Source"] == "cbrowser-data"
    assert profile_mount["VolumeOptions"]["Subpath"] == "profiles/p1/profile"
    assert profile_mount["ReadOnly"] is False
    gate_mount = by_target["/run/cbrowser_policy"]
    assert gate_mount["Source"] == "cbrowser-runtime"
    assert gate_mount["VolumeOptions"]["Subpath"] == "gates/p1/inst/role"
    assert gate_mount["ReadOnly"] is True
    creds_mount = by_target["/run/cbrowser/proxy_credentials.json"]
    assert creds_mount["Source"] == "cbrowser-runtime"
    assert creds_mount["VolumeOptions"]["Subpath"] == ".secrets/p1/proxy_credentials.json"
    # No mount may reference another Profile or a whole volume.
    for mount in mounts:
        assert mount["VolumeOptions"]["Subpath"]
        assert "p2" not in mount["VolumeOptions"]["Subpath"]


def test_stream_volumes_have_no_profile_or_artifact_mounts(tmp_path: Path) -> None:
    planner = _planner(tmp_path)
    data = tmp_path / "data"
    runtime = data / "runtime/p1"
    mounts = stream_volumes(
        planner=planner,
        gate=data / "control/gates/p1/inst/stream",
        x11_socket=runtime / "x11/X99",
        xauth_file=runtime / "Xauthority",
        pulse_dir=runtime / "pulse",
        secret_file=runtime / ".stream-secret",
        selkies_file=runtime / ".selkies.json",
    )
    for mount in mounts:
        assert mount["Source"] == "cbrowser-runtime"
        assert mount["ReadOnly"] is True
        subpath = mount["VolumeOptions"]["Subpath"]
        assert not subpath.startswith("profiles/")
        assert "artifacts" not in subpath
        assert not subpath.startswith("windows/")


def test_cache_init_volumes_are_writable_data_subpaths(tmp_path: Path) -> None:
    planner = _planner(tmp_path)
    data = tmp_path / "data"
    mounts = cache_init_volumes(
        planner=planner,
        engine_cache=data / "engine-cache",
        geoip_cache=data / "engine-cache/geoip",
    )
    assert {m["VolumeOptions"]["Subpath"] for m in mounts} == {
        "engine-cache",
        "engine-cache/geoip",
    }
    assert all(m["Source"] == "cbrowser-data" and not m["ReadOnly"] for m in mounts)
