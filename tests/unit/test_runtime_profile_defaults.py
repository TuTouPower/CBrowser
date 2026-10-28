"""Corrupt initialization markers must not silently suppress real setup."""

import json
from pathlib import Path

import pytest
from cbrowser.runtime_agent.profile_defaults import (
    SEARCH_ENGINE_MARKER_FILE,
    ProfileDefaultsError,
    initialize_profile_defaults,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "marker",
    [
        {
            "version": True,
            "google_default_applied": True,
            "engine_keyword": "google.com",
        },
        {
            "version": 1,
            "google_default_applied": "false",
            "engine_keyword": "google.com",
        },
        {"version": 1, "google_default_applied": True, "engine_keyword": "other"},
    ],
)
async def test_corrupt_marker_rejected_before_using_browser(
    tmp_path: Path, marker: dict
) -> None:
    path = tmp_path / SEARCH_ENGINE_MARKER_FILE
    original = json.dumps(marker)
    path.write_text(original)
    with pytest.raises(ProfileDefaultsError):
        await initialize_profile_defaults(None, tmp_path, set_google_default=True)
    assert path.read_text() == original
