"""Selkies file transfers must be explicitly disabled in the Stream Runtime."""

from __future__ import annotations

from pathlib import Path

from cbrowser.supervisor.container_spec import stream_environment


def test_supervisor_explicitly_disables_selkies_file_transfers() -> None:
    env = stream_environment(
        display=":99",
        profile_id="p1",
        runtime_instance_id="i1",
        gateway_url="ws://127.0.0.1:18080",
        config_version=1,
        udp_mux_port=30000,
        screen_width=1920,
        screen_height=1080,
    )
    assert env["SELKIES_MODE"] == "webrtc"
    assert env["SELKIES_ENABLE_DUAL_MODE"] == "false"
    assert env["SELKIES_FILE_TRANSFERS"] == "none"
    assert env["SELKIES_ENABLE_SHARING"] == "true"
    assert env["SELKIES_ENABLE_COLLAB"] == "false"


def test_stream_entrypoint_passes_file_transfers_none_to_official_selkies() -> None:
    entrypoint = (
        Path(__file__).resolve().parents[2]
        / "config/docker/stream_runtime/entrypoint.sh"
    )
    content = entrypoint.read_text(
        encoding="utf-8"
    )
    active = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert any("export SELKIES_FILE_TRANSFERS=none" in line for line in active)
    assert any("--file-transfers=none" in line for line in active)
