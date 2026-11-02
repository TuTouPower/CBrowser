"""Stream display geometry comes from the Profile config version, never defaults."""

from __future__ import annotations

import os
import secrets
from unittest.mock import patch

import pytest
from cbrowser.stream_agent.config import StreamAgentConfig


def _base_env() -> dict[str, str]:
    return {
        "CBROWSER_PROFILE_ID": "profile_display",
        "CBROWSER_RUNTIME_INSTANCE_ID": "inst_display",
        "CBROWSER_GATEWAY_URL": "ws://127.0.0.1:18090",
        "CBROWSER_AGENT_TOKEN": secrets.token_urlsafe(32),
        "CBROWSER_CONFIG_VERSION": "1",
        "SELKIES_TURN_HOST": "10.0.0.1",
        "SELKIES_TURN_PORT": "3478",
    }


def test_stream_agent_config_accepts_profile_geometry() -> None:
    cfg = StreamAgentConfig(
        profile_id="profile_display",
        runtime_instance_id="inst_display",
        gateway_url="ws://127.0.0.1:18090",
        agent_token=secrets.token_urlsafe(32),
        width=1280,
        height=720,
    )

    assert (cfg.width, cfg.height) == (1280, 720)


def test_from_env_reads_profile_geometry() -> None:
    env = {
        **_base_env(),
        "CBROWSER_SCREEN_WIDTH": "1280",
        "CBROWSER_SCREEN_HEIGHT": "720",
    }
    with patch.dict(os.environ, env, clear=True):
        cfg = StreamAgentConfig.from_env()

    assert (cfg.width, cfg.height) == (1280, 720)


@pytest.mark.parametrize(
    ("width", "height"),
    [("0", "720"), ("1280", "0"), ("abc", "720"), ("1280", "")],
)
def test_from_env_rejects_invalid_profile_geometry(width: str, height: str) -> None:
    env = {
        **_base_env(),
        "CBROWSER_SCREEN_WIDTH": width,
        "CBROWSER_SCREEN_HEIGHT": height,
    }
    with patch.dict(os.environ, env, clear=True), pytest.raises(
        ValueError, match="CBROWSER_SCREEN"
    ):
        StreamAgentConfig.from_env()
