"""Files left by an old Browser must not make a replacement ready."""

import json

import pytest
from cbrowser.supervisor.core import browser_runtime_ready


@pytest.mark.parametrize(
    "field,value",
    [
        ("profile_id", "other"),
        ("runtime_instance_id", "old"),
        ("config_version", 1),
        ("browser_pid", 0),
    ],
)
def test_stale_or_unstarted_browser_is_not_ready(tmp_path, field, value):
    for relative in ("x11/X99", "pulse/pulse.sock", "Xauthority", "agent.sock"):
        path = tmp_path / relative
        path.parent.mkdir(exist_ok=True)
        path.touch()
    info = {
        "profile_id": "p1",
        "runtime_instance_id": "new",
        "config_version": 2,
        "browser_pid": 42,
    }
    (tmp_path / "runner_info.json").write_text(json.dumps(info))
    assert browser_runtime_ready(tmp_path, "p1", "new", 2)
    info[field] = value
    (tmp_path / "runner_info.json").write_text(json.dumps(info))
    assert not browser_runtime_ready(tmp_path, "p1", "new", 2)
