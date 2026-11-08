"""A14: read_secret_file must open with O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK,
validate S_ISREG and permissions on the fd, read from that same fd, reject
non-regular/unsafe files with bounded, redacted errors, and close every fd."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

import pytest
from cbrowser.secret_files import read_secret_file


def _secret(path: Path, mode: int, value: str = "a" * 40) -> Path:
    path.write_text(value, encoding="utf-8")
    path.chmod(mode)
    return path


def test_a14_private_regular_file_reads(tmp_path: Path) -> None:
    path = _secret(tmp_path / "token", 0o600)
    assert read_secret_file(path) == "a" * 40
    assert read_secret_file(path, minimum_bytes=40) == "a" * 40


@pytest.mark.parametrize(
    "mode", [0o640, 0o604, 0o644, 0o660, 0o606, 0o666, 0o777]
)
def test_a14_group_other_modes_rejected(tmp_path: Path, mode: int) -> None:
    path = _secret(tmp_path / "token", mode)
    with pytest.raises(RuntimeError, match="group or others"):
        read_secret_file(path)


def test_a14_symlink_rejected(tmp_path: Path) -> None:
    target = _secret(tmp_path / "real", 0o600)
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(RuntimeError):
        read_secret_file(link)


def test_a14_directory_rejected(tmp_path: Path) -> None:
    path = tmp_path / "adir"
    path.mkdir()
    path.chmod(0o700)
    with pytest.raises(RuntimeError):
        read_secret_file(path)


def test_a14_fifo_rejected_bounded(tmp_path: Path) -> None:
    fifo = tmp_path / "token"
    os.mkfifo(fifo)
    os.chmod(fifo, 0o600)
    outcome: dict[str, object] = {}

    def worker() -> None:
        try:
            outcome["value"] = read_secret_file(fifo)
        except RuntimeError:
            outcome["rejected"] = True

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout=2.0)
    assert not thread.is_alive(), "FIFO read did not return promptly"
    assert outcome.get("rejected") is True


def test_a14_path_replacement_reads_original_fd(tmp_path, monkeypatch) -> None:
    path = tmp_path / "token"
    path.write_text("a" * 40)
    path.chmod(0o600)
    real_stat = os.stat
    real_fstat = os.fstat
    swapped: list[bool] = []
    active: list[bool] = []

    def do_swap() -> None:
        if swapped:
            return
        swapped.append(True)
        os.unlink(path)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
        os.write(fd, b"b" * 40)
        os.close(fd)

    def wrapped_stat(p, *args, **kwargs):
        result = real_stat(p, *args, **kwargs)
        if active:
            do_swap()
        return result

    def wrapped_fstat(fd):
        result = real_fstat(fd)
        if active:
            do_swap()
        return result

    monkeypatch.setattr(os, "stat", wrapped_stat)
    monkeypatch.setattr(os, "fstat", wrapped_fstat)
    active.append(True)
    try:
        value = read_secret_file(path)
    finally:
        active.clear()
    assert swapped
    assert value == "a" * 40


def test_a14_same_fd_for_fstat_read_and_close(tmp_path, monkeypatch) -> None:
    path = _secret(tmp_path / "token", 0o600, "c" * 40)
    real_open = os.open
    real_fstat = os.fstat
    real_read = os.read
    real_close = os.close
    opened: list[tuple[int, int]] = []
    fstat_fds: list[int] = []
    read_fds: list[int] = []
    closed: list[int] = []
    active: list[bool] = []

    def wrapped_open(p, flags, *args, **kwargs):
        fd = real_open(p, flags, *args, **kwargs)
        if active:
            opened.append((fd, flags))
        return fd

    def wrapped_fstat(fd):
        if active:
            fstat_fds.append(fd)
        return real_fstat(fd)

    def wrapped_read(fd, *args, **kwargs):
        if active:
            read_fds.append(fd)
        return real_read(fd, *args, **kwargs)

    def wrapped_close(fd):
        if active:
            closed.append(fd)
        return real_close(fd)

    monkeypatch.setattr(os, "open", wrapped_open)
    monkeypatch.setattr(os, "fstat", wrapped_fstat)
    monkeypatch.setattr(os, "read", wrapped_read)
    monkeypatch.setattr(os, "close", wrapped_close)
    active.append(True)
    try:
        value = read_secret_file(path)
    finally:
        active.clear()
    assert value == "c" * 40
    assert len(opened) == 1
    fd, flags = opened[0]
    assert flags & os.O_NOFOLLOW
    assert flags & os.O_CLOEXEC
    assert flags & os.O_NONBLOCK
    assert fd in fstat_fds
    assert fd in read_fds
    assert fd in closed
    assert {item[0] for item in opened} == set(closed)


def test_a14_errors_and_logs_do_not_leak_content(tmp_path, caplog) -> None:
    marker = "SENSITIVE_MARKER_9f8e7d6c"
    path = _secret(tmp_path / "token", 0o644, marker)
    messages: list[str] = []
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(RuntimeError) as exc_info:
            read_secret_file(path, label="Widget token")
        messages.append(str(exc_info.value))
        with pytest.raises(RuntimeError) as exc_info2:
            read_secret_file(_secret(tmp_path / "short", 0o600, "tiny"))
        messages.append(str(exc_info2.value))
    for message in messages:
        assert marker not in message
        assert str(path) not in message
    assert marker not in caplog.text
    assert "tiny" not in caplog.text
