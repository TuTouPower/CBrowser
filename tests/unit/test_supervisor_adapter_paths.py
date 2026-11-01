"""Host mount sources must be inside the configured data root."""

import pytest
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.path_validator import PathSecurityError, PathValidator

BROWSER = "sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346"
STREAM = "sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531"


def test_engine_cache_cannot_escape_data_root(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(PathSecurityError):
        DockerAdapter(
            PathValidator(tmp_path / "data"),
            outside,
            docker_client=object(),
            browser_image=BROWSER,
            stream_image=STREAM,
        )


def test_geoip_cache_cannot_escape_data_root(tmp_path):
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    with pytest.raises(PathSecurityError):
        DockerAdapter(
            PathValidator(root),
            engine,
            docker_client=object(),
            browser_image=BROWSER,
            stream_image=STREAM,
            geoip_cache_dir=tmp_path / "outside_geoip",
        )


def test_engine_cache_symlink_escape_is_rejected(tmp_path):
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (engine / "escaped").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathSecurityError):
        DockerAdapter(
            PathValidator(root),
            engine,
            docker_client=object(),
            browser_image=BROWSER,
            stream_image=STREAM,
        )


@pytest.mark.parametrize(
    "profile_id",
    ["", ".secrets", ".hidden", "secrets", "archive", "..", "a/b", "a\\b"],
)
def test_profile_id_rejects_reserved_and_escaping_names(tmp_path, profile_id) -> None:
    validator = PathValidator(tmp_path)
    for getter in (
        validator.get_profile_data_dir,
        validator.get_runtime_dir,
        validator.get_secret_dir,
        validator.get_events_dir,
        validator.get_exchange_dir,
    ):
        with pytest.raises(PathSecurityError):
            getter(profile_id)


def test_uuid_shaped_profile_id_remains_valid(tmp_path) -> None:
    validator = PathValidator(tmp_path)
    profile_id = "8f14e45f-ceea-467f-a8d4-0c1e3b2a9f10"
    assert validator.get_runtime_dir(profile_id).name == profile_id
