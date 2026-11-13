"""t055 A12: socket slot cleanup validates before unlink.

A stale socket slot is cleaned; a live socket, a foreign-owned entry, a
non-socket entry, and a symlink are conflicts that must be left in place.
The socket root length is validated at Supervisor startup.
"""

from __future__ import annotations

import errno
import os
import shutil
import socket
import stat
import tempfile
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from cbrowser.runtime_agent import socket_root as sr
from cbrowser.runtime_agent.socket_root import (
    SocketRootError,
    agent_socket_path,
    managed_socket_target,
    prepare_socket_dir,
    resolve_socket_root,
)
from cbrowser.supervisor.path_validator import PathValidator

PROFILE = "prof1"
INSTANCE = "inst1"


@pytest.fixture
def short_root() -> Iterator[Path]:
    """Short /tmp root for tests that bind or length-validate real UDS paths.

    pytest tmp_path under xdist (popen-gwN- prefix) pushes
    <root>/<slot>/agent.sock past the sun_path bound; the production
    socket root is short by design (/run/cb/socks), so these tests use
    a short mkdtemp root instead (same pattern as the p019 fixture in
    test_normal_exit_replay.py).
    """
    root = Path(tempfile.mkdtemp(prefix="cbx-sock-", dir="/tmp"))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _stale_socket(root: Path) -> Path:
    sock = agent_socket_path(root, PROFILE, INSTANCE)
    sock.parent.mkdir(parents=True, exist_ok=True)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.bind(str(sock))
    finally:
        s.close()
    assert sock.is_socket()
    return sock


def _live_socket(root: Path):
    sock = agent_socket_path(root, PROFILE, INSTANCE)
    sock.parent.mkdir(parents=True, exist_ok=True)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(str(sock))
    s.listen(1)
    return s, sock


def test_prepare_socket_dir_cleans_stale_socket_and_leaves_other_slots(short_root):
    """AC-009: a stale socket in the target slot is cleaned; other slots stay."""
    root = short_root / "socks"
    stale = _stale_socket(root)
    other = agent_socket_path(root, "other-prof", "other-inst")
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("keep me", encoding="utf-8")

    directory = prepare_socket_dir(root, PROFILE, INSTANCE)

    assert directory == stale.parent
    assert not stale.exists()
    assert other.read_text(encoding="utf-8") == "keep me"


def test_prepare_socket_dir_tolerates_entry_vanishing_between_exists_and_stat(
    short_root, monkeypatch
):
    """AC-009: an entry deleted between exists() and stat() (concurrent
    cleanup of the same slot) is treated as already cleaned, not a bare
    FileNotFoundError leaking out of prepare_socket_dir."""
    root = short_root / "socks"
    stale = _stale_socket(root)
    real_exists = Path.exists

    def vanishing_exists(self, *, follow_symlinks=True):
        result = real_exists(self, follow_symlinks=follow_symlinks)
        if result and self == stale:
            # Simulate a concurrent cleanup deleting the entry right
            # after the existence check succeeded.
            os.unlink(self)
        return result

    monkeypatch.setattr(Path, "exists", vanishing_exists)

    directory = prepare_socket_dir(root, PROFILE, INSTANCE)

    assert directory == stale.parent


def test_prepare_socket_dir_rejects_live_socket(short_root):
    """AC-009: a live socket is a conflict and is left in place."""
    root = short_root / "socks"
    server, sock = _live_socket(root)
    try:
        with pytest.raises(SocketRootError):
            prepare_socket_dir(root, PROFILE, INSTANCE)
    finally:
        server.close()
    assert sock.is_socket()


def test_prepare_socket_dir_rejects_foreign_uid(short_root):
    """AC-009: an entry owned by another uid is a conflict."""
    root = short_root / "socks"
    stale = _stale_socket(root)
    foreign_uid = os.geteuid() + 1

    with pytest.raises(SocketRootError):
        prepare_socket_dir(root, PROFILE, INSTANCE, managed_uid=foreign_uid)

    assert stale.is_socket()


def test_prepare_socket_dir_rejects_non_socket_entry(tmp_path):
    """AC-009: a regular file in the slot is a conflict, not a stale socket."""
    root = tmp_path / "socks"
    sock = agent_socket_path(root, PROFILE, INSTANCE)
    sock.parent.mkdir(parents=True, exist_ok=True)
    sock.write_text("not a socket", encoding="utf-8")

    with pytest.raises(SocketRootError):
        prepare_socket_dir(root, PROFILE, INSTANCE)

    assert sock.read_text(encoding="utf-8") == "not a socket"


def test_prepare_socket_dir_rejects_symlink_entry(tmp_path):
    """AC-009: a symlink in the slot is a conflict and is left in place."""
    root = tmp_path / "socks"
    target = tmp_path / "elsewhere.sock"
    target.write_text("victim", encoding="utf-8")
    sock = agent_socket_path(root, PROFILE, INSTANCE)
    sock.parent.mkdir(parents=True, exist_ok=True)
    sock.symlink_to(target)

    with pytest.raises(SocketRootError):
        prepare_socket_dir(root, PROFILE, INSTANCE)

    assert sock.is_symlink()
    assert target.read_text(encoding="utf-8") == "victim"


def test_resolve_socket_root_rejects_overlong_longest_slot_path():
    """AC-009: the longest possible slot path must fit the sun_path bound."""
    long_root = "/tmp/" + "x" * 70
    # root(75) + "/" + slot(20) + "/" + "agent.sock"(10) = 107 > 100.
    with pytest.raises(SocketRootError):
        resolve_socket_root({"CBROWSER_SOCKET_ROOT": long_root})


def test_resolve_socket_root_accepts_bounded_root():
    """AC-009: a short root still resolves (regression guard)."""
    assert resolve_socket_root({"CBROWSER_SOCKET_ROOT": "/tmp/cb"}) == Path(
        "/tmp/cb"
    )


def test_path_validator_construction_rejects_overlong_socket_root(
    tmp_path, monkeypatch
):
    """AC-009: successor of the deleted a36 overlong-root test. An overlong
    socket root now fails at Supervisor startup (PathValidator construction),
    not at prepare time."""
    monkeypatch.setenv(sr.AGENT_SOCKET_ROOT_ENV, "/tmp/" + "x" * 200)
    with pytest.raises(SocketRootError):
        PathValidator(tmp_path / "data")


def test_managed_socket_target_tolerates_directory_vanishing_between_open_and_lstat(
    short_root, monkeypatch
):
    """A12 (socket_root read path, not the AC-009 slot-cleanup path): a
    slot directory deleted between open() and lstat() (concurrent cleanup
    of the same slot) falls back to the plain socket path, same as the
    open() ENOENT/ENOTDIR fallback — callers treat a non-socket target
    as absent — instead of leaking a bare FileNotFoundError."""
    root = short_root / "socks"
    sock = agent_socket_path(root, PROFILE, INSTANCE)
    directory = sock.parent
    directory.mkdir(parents=True, exist_ok=True)
    real_lstat = os.lstat

    def vanishing_lstat(path, *args, **kwargs):
        if os.fspath(path) == str(directory):
            # Simulate a concurrent cleanup deleting the slot directory
            # right after open() succeeded.
            raise FileNotFoundError(
                errno.ENOENT, "No such file or directory", path
            )
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", vanishing_lstat)

    with managed_socket_target(root, PROFILE, INSTANCE) as target:
        assert target == str(sock)


def _slot_stat(*, dev=1, ino=2, mode=0o40755, uid=1000, gid=1000):
    """Fake os.stat_result for _validate_slot_dir direct tests."""
    return SimpleNamespace(
        st_dev=dev, st_ino=ino, st_mode=mode, st_uid=uid, st_gid=gid
    )


def test_validate_slot_dir_accepts_matching_identity():
    """A12 (socket_root read path, not the AC-009 slot-cleanup path):
    _validate_slot_dir returns None when the fd and the path agree on
    dev/ino, the target is a directory, it is not group/other writable,
    and owner and group match the managed identity."""
    assert (
        sr._validate_slot_dir(
            _slot_stat(), _slot_stat(), managed_uid=1000, managed_gid=1000
        )
        is None
    )


def test_validate_slot_dir_rejects_group_mismatch():
    """A12 (socket_root read path, not the AC-009 slot-cleanup path):
    a slot directory whose group differs from the managed gid is
    rejected, even when dev/ino, mode, and owner all match."""
    with pytest.raises(SocketRootError, match="group"):
        sr._validate_slot_dir(
            _slot_stat(gid=2000),
            _slot_stat(gid=2000),
            managed_uid=1000,
            managed_gid=1000,
        )


def test_validate_slot_dir_ignores_group_when_unmanaged():
    """A12 (socket_root read path, not the AC-009 slot-cleanup path):
    with managed_gid=None the group is not checked, so a directory
    whose group differs from any ambient gid still passes."""
    assert (
        sr._validate_slot_dir(
            _slot_stat(gid=2000),
            _slot_stat(gid=2000),
            managed_uid=1000,
            managed_gid=None,
        )
        is None
    )
