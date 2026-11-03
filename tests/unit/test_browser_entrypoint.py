"""Browser runtime entrypoint argument contract (t024 AC-010/A32).

The browser image's default CMD is ``--help``; the entrypoint must answer
help requests with usage text and exit 0, reject unknown arguments with a
non-zero exit, and keep the required-argument failure non-zero.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "config" / "docker" / "browser_runtime" / "entrypoint.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(ENTRYPOINT), *args],
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_help_long_flag_prints_usage_and_exits_zero() -> None:
    result = _run("--help")
    assert result.returncode == 0
    assert "--profile-id" in result.stdout
    assert "--config-snapshot" in result.stdout


def test_help_short_flag_prints_usage_and_exits_zero() -> None:
    result = _run("-h")
    assert result.returncode == 0
    assert "--profile-id" in result.stdout


def test_unknown_argument_exits_nonzero() -> None:
    result = _run("--definitely-not-a-real-flag")
    assert result.returncode != 0


def test_missing_required_arguments_exit_nonzero() -> None:
    result = _run()
    assert result.returncode != 0
