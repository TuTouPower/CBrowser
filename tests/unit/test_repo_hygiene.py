"""Repository privacy and hygiene guards."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = ROOT / "tests/unit/review_privacy_allowlist.txt"

# Developer home-path shapes across platforms (t024 AC-017/A52).  The POSIX
# form captures the account segment; the /root/ form captures the whole path
# token so fixed in-container paths can be exempted precisely; the Windows
# forms cover both separator styles.
POSIX_HOME_PATH = re.compile(r"/(?:Users|home)/([A-Za-z0-9._-]+)/")
ROOT_HOME_PATH = re.compile(r"/root/[A-Za-z0-9._\-/]+")
WINDOWS_HOME_PATHS = (
    re.compile(r"[A-Za-z]:\\Users\\([A-Za-z0-9._% \-]+)\\"),
    re.compile(r"[A-Za-z]:/Users/([A-Za-z0-9._% \-]+)/"),
)
CONTAINER_USERS = {"cbrowser", "appuser", "selkies", "pulse", "root", "runner", "docker"}
WINDOWS_SYSTEM_PROFILES = {"Public", "Default", "Default User", "All Users"}
# Exact in-container paths that are part of the product, not a developer's
# machine (the Browser image runs Chrome as root with this config dir).
CONTAINER_FIXED_PATH_PREFIXES = ("/root/.config/google-chrome",)
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".woff", ".woff2",
    ".ttf", ".otf", ".ttc", ".eot", ".zip", ".gz", ".bz2", ".xz", ".7z",
    ".pdf", ".wasm", ".so", ".dylib", ".dll", ".exe", ".bin", ".mp4",
    ".webm", ".mov", ".pyc", ".class", ".jar", ".db", ".sqlite",
}


def find_developer_path_leaks(text: str) -> list[str]:
    """Return developer home-path occurrences in *text*.

    Container accounts, Windows system profiles and the exact fixed
    in-container paths above are not leaks.
    """
    spans: list[tuple[int, int, str]] = []
    for match in POSIX_HOME_PATH.finditer(text):
        if match.group(1) not in CONTAINER_USERS:
            spans.append((match.start(), match.end(), match.group(0)))
    for pattern in WINDOWS_HOME_PATHS:
        for match in pattern.finditer(text):
            if (
                match.group(1) not in CONTAINER_USERS
                and match.group(1) not in WINDOWS_SYSTEM_PROFILES
            ):
                spans.append((match.start(), match.end(), match.group(0)))
    # A Windows forward-slash path contains a POSIX-looking substring; the
    # wider match wins so one leak is reported once.
    leaks = [
        text_value
        for start, end, text_value in spans
        if not any(
            other_start <= start and end <= other_end and (other_start, other_end) != (start, end)
            for other_start, other_end, _ in spans
        )
    ]
    for match in ROOT_HOME_PATH.finditer(text):
        token = match.group(0).rstrip("/.,;:)'\"")
        if not any(
            token == prefix or token.startswith(prefix + "/")
            for prefix in CONTAINER_FIXED_PATH_PREFIXES
        ):
            leaks.append(token)
    return leaks


def decode_candidate_text(path: Path, data: bytes) -> str | None:
    """Classify tracked content for scanning.

    A file is scanned when it decodes as UTF-8; a NUL byte early in the file
    no longer exempts the whole text (the old 8192-byte head check silently
    skipped leaks later in such files).  Only known-binary suffixes are
    skipped outright; anything else undecodable is scanned lossily so the
    guard fails toward detection.
    """
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        if path.suffix.lower() in BINARY_SUFFIXES:
            return None
        return data.decode("utf-8", errors="ignore")


def approved_snapshots(lines: list[str] | None = None) -> set[tuple[str, str]]:
    """Approved historical snapshots as (path, sha256) pairs (A44/AC-017).

    Each allowlist entry binds one specific path to the sha256 of its
    approved bytes: the exemption follows neither content nor location
    alone — the same bytes at an unlisted path are NOT exempt, and any
    content change at a listed path lapses its exemption.  When a file is
    moved (e.g. task files archived at finish), its entry's path must be
    updated to the new location in the same change.
    """
    if lines is None:
        lines = ALLOWLIST.read_text(encoding="utf-8").splitlines()
    pairs: set[tuple[str, str]] = set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        path, _, fingerprint = line.rpartition(" sha256:")
        assert fingerprint and len(fingerprint) == 64, f"allowlist entry lacks fingerprint: {line!r}"
        pairs.add((path, fingerprint))
    return pairs


def is_approved_snapshot(name: str, data: bytes, approved: set[tuple[str, str]]) -> bool:
    return (name, hashlib.sha256(data).hexdigest()) in approved


def tracked_files() -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT, text=False
    ).decode("utf-8")
    return [name for name in output.split("\0") if name]


def test_tracked_files_do_not_leak_developer_home_paths():
    # Historical snapshots are exempt only by exact (path, content
    # fingerprint) pairs (A44: history is not rewritten).  There is no
    # directory-level exemption: new files under docs/archive/ or
    # docs/reviews/ are scanned like everything else, copying an exempt
    # file to a new path does not exempt the copy, and editing an exempt
    # file lapses its exemption.
    approved = approved_snapshots()
    violations: list[str] = []
    for name in tracked_files():
        path = ROOT / name
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if is_approved_snapshot(name, data, approved):
            continue
        text = decode_candidate_text(path, data)
        if text is None:
            continue
        for leak in find_developer_path_leaks(text):
            violations.append(f"{name}: {leak}")
    assert not violations, "\n".join(violations)


def _joined(*parts: str) -> str:
    # Synthetic samples are assembled from fragments so this guard's own
    # source never contains a contiguous developer path for it to flag.
    return "/".join(parts)


def test_hygiene_guard_detects_each_platform_shape():
    mac = _joined("", "Users", "dev", "proj")
    linux = _joined("", "home", "dev", "proj")
    win_fwd = "C:" + _joined("", "Users", "dev", "proj")
    win_back = "C:\\" + "\\".join(["Users", "dev", "proj"])
    root_home = _joined("", "root", "work", "proj")
    assert find_developer_path_leaks(f"worktree '{mac}' diff") == [_joined("", "Users", "dev", "")]
    assert find_developer_path_leaks(f"worktree '{linux}' diff") == [_joined("", "home", "dev", "")]
    assert find_developer_path_leaks(f"worktree '{win_back}' diff") == ["C:\\" + "Users" + "\\" + "dev" + "\\"]
    assert find_developer_path_leaks(f"worktree '{win_fwd}' diff") == ["C:" + _joined("", "Users", "dev", "")]
    assert find_developer_path_leaks(f"checkout '{root_home}' diff") == [root_home]


def test_hygiene_guard_exempts_container_and_system_identities():
    cbrowser_home = _joined("", "home", "cbrowser", "x")
    selkies_home = _joined("", "home", "selkies", "y")
    assert find_developer_path_leaks(f"runs as '{cbrowser_home}' and '{selkies_home}'") == []
    public_profile = "C:\\" + "\\".join(["Users", "Public", "shared"])
    assert find_developer_path_leaks(f"profile '{public_profile}'") == []
    chrome_dir = _joined("", "root", ".config", "google-chrome", "Default")
    assert find_developer_path_leaks(f"chrome dir {chrome_dir}") == []


def test_hygiene_guard_scans_past_nul_bytes_and_binary_classification():
    linux = _joined("", "home", "dev", "proj")
    payload = b"\x00binary-ish head\ncheckout '" + linux.encode() + b"' diff"
    text = decode_candidate_text(Path("notes.md"), payload)
    assert text is not None
    assert find_developer_path_leaks(text) == [_joined("", "home", "dev", "")]
    assert decode_candidate_text(Path("font.ttc"), b"\x00\x01\x02\xff") is None


def test_snapshot_exemption_lapses_when_content_changes():
    mac = _joined("", "Users", "dev", "proj")
    original = f"snapshot with '{mac}' inside".encode()
    pairs = approved_snapshots([f"docs/reviews/x.md sha256:{hashlib.sha256(original).hexdigest()}"])
    assert is_approved_snapshot("docs/reviews/x.md", original, pairs)
    assert not is_approved_snapshot("docs/reviews/x.md", original + b"edited", pairs)


def test_snapshot_exemption_does_not_follow_content_to_a_new_path():
    mac = _joined("", "Users", "dev", "proj")
    original = f"snapshot with '{mac}' inside".encode()
    pairs = approved_snapshots([f"docs/reviews/x.md sha256:{hashlib.sha256(original).hexdigest()}"])
    # Identical bytes at an unlisted path are not exempt (AC-017 double
    # binding: path AND fingerprint).
    assert not is_approved_snapshot("docs/reviews/y.md", original, pairs)
    assert not is_approved_snapshot("src/copy.md", original, pairs)


def test_container_prefix_exemption_respects_segment_boundary():
    fixed = _joined("", "root", ".config", "google-chrome", "Default")
    assert find_developer_path_leaks(f"path {fixed} end") == []
    evil = _joined("", "root", ".config", "google-chrome.evil", "x")
    assert find_developer_path_leaks(f"path {evil} end") == [evil]
    evil2 = _joined("", "root", ".config", "google-chrome2", "x")
    assert find_developer_path_leaks(f"path {evil2} end") == [evil2]


def test_archived_spikes_have_read_only_notice():
    readme = ROOT / "docs/archive/spikes/README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert ".scratch" in text and "probe_work" in text
