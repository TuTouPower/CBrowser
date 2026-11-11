"""Profile clipboard_sync must map to locked, seamless Selkies clipboard policy."""

from __future__ import annotations

from pathlib import Path

from cbrowser.supervisor.container_spec import stream_environment


def _env(clipboard_sync: bool):
    return stream_environment(
        display=":99",
        profile_id="p1",
        runtime_instance_id="i1",
        gateway_url="ws://127.0.0.1:18080",
        config_version=1,
        udp_mux_port=30000,
        screen_width=1920,
        screen_height=1080,
        clipboard_sync=clipboard_sync,
    )


def test_clipboard_sync_maps_to_locked_seamless_text_only_policy() -> None:
    assert _env(True)["SELKIES_ENABLE_CLIPBOARD"] == "true"
    assert _env(False)["SELKIES_ENABLE_CLIPBOARD"] == "false"
    for value in (True, False):
        assert _env(value)["SELKIES_ENABLE_BINARY_CLIPBOARD"] == "false|locked"
        assert _env(value)["SELKIES_CLIPBOARD_SEAMLESS"] == "true|locked"


def test_entrypoint_defaults_to_locked_seamless_clipboard_for_official_selkies() -> None:
    entrypoint = (
        Path(__file__).resolve().parents[2]
        / "config/docker/stream_runtime/entrypoint.sh"
    )
    content = entrypoint.read_text(encoding="utf-8")
    active = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert any(
        'export SELKIES_ENABLE_CLIPBOARD="${SELKIES_ENABLE_CLIPBOARD:-true}"' in line
        for line in active
    )
    assert any(
        "export SELKIES_ENABLE_BINARY_CLIPBOARD="
        '"${SELKIES_ENABLE_BINARY_CLIPBOARD:-false|locked}"' in line
        for line in active
    )
    assert any(
        "export SELKIES_CLIPBOARD_SEAMLESS="
        '"${SELKIES_CLIPBOARD_SEAMLESS:-true|locked}"' in line
        for line in active
    )
    assert any(
        '--enable-clipboard "$SELKIES_ENABLE_CLIPBOARD"' in line for line in active
    )
    assert any(
        '--enable-binary-clipboard "$SELKIES_ENABLE_BINARY_CLIPBOARD"' in line
        for line in active
    )
    assert any(
        '--clipboard-seamless "$SELKIES_CLIPBOARD_SEAMLESS"' in line for line in active
    )
