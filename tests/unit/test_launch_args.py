"""Launch argument whitelist contract (A45)."""

import pytest
from cbrowser.domain.models import ProfileConfig
from cbrowser.launch_args import InvalidLaunchArgument, validate_launch_args
from cbrowser.runtime_agent.runner import BrowserRunner
from pydantic import ValidationError


def test_whitelisted_arguments_pass():
    args = ["--no-first-run", "--lang=en-US", "--accept-lang=en-US,zh-CN"]
    assert validate_launch_args(args) == args


@pytest.mark.parametrize(
    "arg",
    [
        "--load-extension=/tmp/evil",
        "--js-flags=--noopt",
        "file:///etc/passwd",
        "--fingerprint=123",
        "--window-size=800,600",
        "--no-sandbox",
        "--disable-web-security",
        "--user-data-dir=/tmp/other",
    ],
)
def test_bypass_and_infrastructure_arguments_are_rejected(arg):
    with pytest.raises(InvalidLaunchArgument):
        validate_launch_args([arg])


def test_profile_config_filters_legacy_launch_args():
    assert ProfileConfig(launch_args=["--load-extension=/tmp/evil"]).launch_args == []
    from cbrowser.domain.models import ProfileCreateRequest

    with pytest.raises(ValidationError):
        ProfileCreateRequest(name="bad", launch_args=["--load-extension=/tmp/evil"])


def test_update_request_rejects_out_of_whitelist_launch_args():
    from cbrowser.domain.models import ProfileUpdateRequest

    with pytest.raises(ValidationError):
        ProfileUpdateRequest(launch_args=["--load-extension=/tmp/evil"])


def test_update_request_keeps_whitelisted_launch_args_verbatim():
    from cbrowser.domain.models import ProfileUpdateRequest

    request = ProfileUpdateRequest(launch_args=["--mute-audio", "--lang=en-US"])
    assert request.launch_args == ["--mute-audio", "--lang=en-US"]


def test_update_request_null_launch_args_stays_null_for_patch_tri_state():
    from cbrowser.domain.models import ProfileUpdateRequest

    request = ProfileUpdateRequest(launch_args=None)
    assert request.launch_args is None
    assert "launch_args" in request.model_fields_set
    absent = ProfileUpdateRequest()
    assert absent.launch_args is None
    assert "launch_args" not in absent.model_fields_set


def test_runner_second_gate_rejects_non_whitelisted_arguments(tmp_path):
    with pytest.raises(InvalidLaunchArgument):
        BrowserRunner.validate_launch_arguments(["--js-flags=--noopt"])


def test_runtime_storage_defaults_target_uid_1000():
    from cbrowser.adapters.filesystem.artifact_store import ArtifactStore
    from cbrowser.services.profile_service import ProfileService

    assert ArtifactStore("/tmp/unused-artifacts").runtime_uid == 1000
    assert ProfileService(repo=None).runtime_uid == 1000  # type: ignore[arg-type]
