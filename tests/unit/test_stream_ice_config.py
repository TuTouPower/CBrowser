"""Stream ICE must stay on loopback host candidates only (ADR 013, t019).

Selkies 2.1.0 defaults to external STUN/TURN (OpenRelay), which makes every
new PeerConnection wait ~5s for a TURN allocation timeout. The Stream
runtime must explicitly enable ICE-lite so no external STUN/TURN is used
and only ``127.0.0.1:<udp mux>`` host candidates appear.
"""

from __future__ import annotations

import re
from pathlib import Path

from cbrowser.supervisor.container_spec import stream_environment

ENTRYPOINT = Path("config/docker/stream_runtime/entrypoint.sh")


def _active_lines() -> list[str]:
    content = ENTRYPOINT.read_text(encoding="utf-8")
    return [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_supervisor_stream_environment_enables_ice_lite() -> None:
    env = stream_environment(
        public_ip="127.0.0.1",
        display=":99",
        profile_id="p1",
        runtime_instance_id="i1",
        gateway_url="ws://127.0.0.1:18080",
        config_version=1,
        udp_mux_port=30000,
        screen_width=1920,
        screen_height=1080,
    )
    assert env["SELKIES_WEBRTC_ICE_LITE"] == "true"


def test_stream_entrypoint_enables_ice_lite_for_official_selkies() -> None:
    active = _active_lines()
    assert any("export SELKIES_WEBRTC_ICE_LITE=true" in line for line in active)
    assert any("--webrtc-ice-lite" in line for line in active)


_FORBIDDEN = re.compile(
    r"--turn|--stun|webrtc[-_](turn|stun)|(turn|stun)[-_]?servers?"
    r"|SELKIES_TURN|SELKIES_STUN|openrelay|metered\.ca"
    r"|stun:|turn:|turns:",
    re.IGNORECASE,
)


def test_stream_entrypoint_configures_no_external_stun_or_turn() -> None:
    offenders = [line for line in _active_lines() if _FORBIDDEN.search(line)]
    assert offenders == []


def test_supervisor_stream_environment_configures_no_external_stun_or_turn() -> (
    None
):
    env = stream_environment(
        public_ip="127.0.0.1",
        display=":99",
        profile_id="p1",
        runtime_instance_id="i1",
        gateway_url="ws://127.0.0.1:18080",
        config_version=1,
        udp_mux_port=30000,
        screen_width=1920,
        screen_height=1080,
    )
    offenders = [
        f"{key}={value}"
        for key, value in env.items()
        if "TURN" in key.upper()
        or "STUN" in key.upper()
        or _FORBIDDEN.search(str(value))
    ]
    assert offenders == []
