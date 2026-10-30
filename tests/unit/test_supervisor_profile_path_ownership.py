"""Aliases inside the data root must not cross Profile boundaries."""

import pytest
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.path_validator import PathSecurityError, PathValidator


def test_profile_runtime_directory_cannot_alias_another_profile(tmp_path):
    (tmp_path / "runtime" / "profile_b").mkdir(parents=True)
    (tmp_path / "runtime" / "profile_a").symlink_to(tmp_path / "runtime" / "profile_b")
    with pytest.raises(PathSecurityError):
        PathValidator(tmp_path).get_runtime_dir("profile_a")


def test_user_data_directory_cannot_alias_another_profile(tmp_path):
    target = tmp_path / "profiles" / "profile_b" / "profile"
    target.mkdir(parents=True)
    source = tmp_path / "profiles" / "profile_a"
    source.mkdir()
    (source / "profile").symlink_to(target)
    with pytest.raises(PathSecurityError):
        PathValidator(tmp_path).get_profile_data_dir("profile_a")


def test_pulse_mount_cannot_alias_another_profile(tmp_path):
    target = tmp_path / "runtime" / "profile_b" / "pulse"
    target.mkdir(parents=True)
    runtime = tmp_path / "runtime" / "profile_a"
    runtime.mkdir()
    (runtime / "pulse").symlink_to(target)
    engine = tmp_path / "engine_cache"
    (engine / "geoip").mkdir(parents=True)
    adapter = DockerAdapter(
        PathValidator(tmp_path),
        engine,
        docker_client=object(),
        browser_image="sha256:unused",
        stream_image="sha256:unused",
    )
    with pytest.raises(PathSecurityError):
        adapter.prepare_profile_directories("profile_a")
