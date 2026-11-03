"""Repository privacy and hygiene guards."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOME_PATH = re.compile(r"/(?:Users|home)/([A-Za-z0-9._-]+)/")
CONTAINER_USERS = {"cbrowser", "appuser", "selkies", "pulse", "root", "runner", "docker"}


def tracked_text_files() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT, text=False
    ).decode("utf-8")
    files: list[Path] = []
    allowlist = {
        line.strip()
        for line in (ROOT / "tests/unit/review_privacy_allowlist.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    for name in output.split("\0"):
        if not name or name.startswith("docs/archive/") or name in allowlist:
            continue
        path = ROOT / name
        if not path.is_file():
            continue
        try:
            head = path.read_bytes()[:8192]
        except OSError:
            continue
        if b"\0" not in head:
            files.append(path)
    return files


def test_tracked_files_do_not_leak_developer_home_paths():
    # Historical archive/review snapshots are immutable by convention (A44).
    violations: list[str] = []
    for path in tracked_text_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in HOME_PATH.finditer(text):
            if match.group(1) not in CONTAINER_USERS:
                violations.append(f"{path.relative_to(ROOT)}: {match.group(0)}")
    assert not violations, "\n".join(violations)


def test_archived_spikes_have_read_only_notice():
    readme = ROOT / "docs/archive/spikes/README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert ".scratch" in text and "probe_work" in text
