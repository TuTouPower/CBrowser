"""Bounded, data-root-independent UDS runtime root shared by the Browser Agent
producer and the Supervisor consumers.
"""

from __future__ import annotations

import errno
import hashlib
import os
import socket
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from .security import validate_runtime_id

AGENT_SOCKET_ROOT_ENV = "CBROWSER_SOCKET_ROOT"
AGENT_SOCKET_PATH_ENV = "CBROWSER_AGENT_SOCKET_PATH"
DEFAULT_AGENT_SOCKET_ROOT = "/run/cb/socks"
AGENT_SOCKET_NAME = "agent.sock"
PROC_SELF_FD = "/proc/self/fd"
SUN_PATH_BYTE_LIMIT = 100
SOCKET_SLOT_LENGTH = 20

RESERVED_SLOT_IDS = frozenset({".", ".."})


class SocketRootError(RuntimeError):
    """Raised when the managed UDS root violates its security contract."""


def resolve_socket_root(env: Mapping[str, str] | None = None) -> Path:
    source = os.environ if env is None else env
    raw = source.get(AGENT_SOCKET_ROOT_ENV) or DEFAULT_AGENT_SOCKET_ROOT
    root = Path(raw)
    if not root.is_absolute():
        raise SocketRootError("Socket root must be absolute")
    if root.is_symlink():
        raise SocketRootError("Socket root cannot be a symlink")
    # t055 A12: the longest possible slot path (20-char slot id +
    # "agent.sock") must fit the sun_path bound at startup, so a
    # deployment can never build an unconnectable socket path later.
    longest = root / ("x" * SOCKET_SLOT_LENGTH) / AGENT_SOCKET_NAME
    if len(os.fsencode(str(longest))) > SUN_PATH_BYTE_LIMIT:
        raise SocketRootError(
            "Socket root is too long for the longest socket slot path"
        )
    return root


def _socket_is_live(entry: Path) -> bool:
    """True when the Unix socket at ``entry`` still accepts connections.

    A refused or vanished socket is stale. Any other probe failure is
    treated as live (fail-closed): an ambiguous entry is never unlinked.
    """
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.settimeout(1.0)
        probe.connect(os.fsdecode(entry))
        return True
    except (ConnectionRefusedError, FileNotFoundError):
        return False
    except OSError:
        return True
    finally:
        probe.close()


def socket_slot(profile_id: str, instance_id: str) -> str:
    validate_runtime_id(profile_id)
    validate_runtime_id(instance_id)
    if profile_id in RESERVED_SLOT_IDS or instance_id in RESERVED_SLOT_IDS:
        raise SocketRootError("Reserved socket identity")
    digest = hashlib.sha256(
        f"{profile_id}\x00{instance_id}".encode("utf-8")
    ).hexdigest()
    return digest[:SOCKET_SLOT_LENGTH]


def agent_socket_dir(root: Path, profile_id: str, instance_id: str) -> Path:
    return Path(root) / socket_slot(profile_id, instance_id)


def agent_socket_path(root: Path, profile_id: str, instance_id: str) -> Path:
    return agent_socket_dir(root, profile_id, instance_id) / AGENT_SOCKET_NAME


def _validated_explicit_socket_path(raw: str, root: Path) -> str:
    path = Path(raw)
    if not path.is_absolute():
        raise SocketRootError("Explicit agent socket path must be absolute")
    if path.is_symlink():
        raise SocketRootError("Explicit agent socket path cannot be a symlink")
    resolved_root = os.path.realpath(str(root))
    resolved_path = os.path.realpath(str(path))
    if not (
        resolved_path == resolved_root
        or resolved_path.startswith(resolved_root + os.sep)
    ):
        raise SocketRootError("Explicit agent socket path escapes the socket root")
    if len(os.fsencode(str(path))) > SUN_PATH_BYTE_LIMIT:
        raise SocketRootError("Encoded UDS path exceeds sun_path bound")
    return str(path)


def container_agent_socket_path(env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    explicit = source.get(AGENT_SOCKET_PATH_ENV)
    if explicit:
        return _validated_explicit_socket_path(explicit, resolve_socket_root(source))
    profile_id = source.get("PROFILE_ID")
    instance_id = source.get("RUNTIME_INSTANCE_ID")
    if not profile_id or not instance_id:
        raise SocketRootError(
            "Container socket identity unavailable: "
            "PROFILE_ID and RUNTIME_INSTANCE_ID are required"
        )
    return str(
        agent_socket_path(resolve_socket_root(source), profile_id, instance_id)
    )


def validate_socket_deployment(
    root: Path, profile_id: str, instance_id: str
) -> Path:
    sock = agent_socket_path(root, profile_id, instance_id)
    if len(os.fsencode(str(sock))) > SUN_PATH_BYTE_LIMIT:
        raise SocketRootError("Encoded UDS path exceeds sun_path bound")
    return sock


def prepare_socket_dir(
    root: Path,
    profile_id: str,
    instance_id: str,
    managed_uid: int | None = None,
    managed_gid: int | None = None,
) -> Path:
    sock = agent_socket_path(root, profile_id, instance_id)
    directory = sock.parent
    if directory.is_symlink():
        raise SocketRootError("Socket slot directory is a symlink")
    directory.mkdir(parents=True, exist_ok=True)
    if managed_uid is not None and managed_gid is not None:
        os.chown(directory, managed_uid, managed_gid)
    os.chmod(directory, 0o750)
    entry = directory / AGENT_SOCKET_NAME
    if entry.is_symlink():
        raise SocketRootError("Socket slot entry is a symlink")
    if entry.exists():
        # t055 A12: validate owner, type, and liveness before unlinking.
        # Anything that is not our own stale socket is a conflict and is
        # left in place; only a stale socket may be reclaimed.
        try:
            st = entry.stat()
        except FileNotFoundError:
            # The entry vanished between exists() and stat() (another
            # process or an old instance's cleanup reclaimed the same
            # slot concurrently); the slot is already clean.
            return directory
        if managed_uid is not None and st.st_uid != managed_uid:
            raise SocketRootError("Socket slot owned by another user")
        if not stat.S_ISSOCK(st.st_mode):
            raise SocketRootError("Socket slot entry is not a socket")
        if _socket_is_live(entry):
            raise SocketRootError("Socket slot is still live")
        try:
            entry.unlink()
        except FileNotFoundError:
            pass
    return directory


def _fd_proc_available(dir_fd: int) -> bool:
    return os.path.isdir(f"{PROC_SELF_FD}/{dir_fd}")


def _socket_target(dir_fd: int, sock: Path) -> str:
    if _fd_proc_available(dir_fd):
        return f"{PROC_SELF_FD}/{dir_fd}/{AGENT_SOCKET_NAME}"
    return str(sock)


def _validate_slot_dir(
    fd_stat: os.stat_result,
    path_stat: os.stat_result,
    managed_uid: int | None,
    managed_gid: int | None,
) -> None:
    """Raise unless the opened fd still names the same slot directory.

    The fd and the path must agree (dev/ino), the target must be a
    directory, it must not be group/other writable, and its owner and
    group must match the managed identity when one is given. Messages
    are part of the SocketRootError contract; keep them verbatim.
    """
    if (fd_stat.st_dev, fd_stat.st_ino) != (path_stat.st_dev, path_stat.st_ino):
        raise SocketRootError("Socket slot directory replaced after open")
    if not stat.S_ISDIR(fd_stat.st_mode):
        raise SocketRootError("Socket slot is not a directory")
    if fd_stat.st_mode & 0o022:
        raise SocketRootError("Socket slot directory is group/other writable")
    if managed_uid is not None and fd_stat.st_uid != managed_uid:
        raise SocketRootError("Socket slot directory owner mismatch")
    if managed_gid is not None and fd_stat.st_gid != managed_gid:
        raise SocketRootError("Socket slot directory group mismatch")


@contextmanager
def managed_socket_target(
    root: Path,
    profile_id: str,
    instance_id: str,
    *,
    managed_uid: int | None = None,
    managed_gid: int | None = None,
) -> Iterator[str]:
    sock = validate_socket_deployment(root, profile_id, instance_id)
    directory = sock.parent
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        dir_fd = os.open(str(directory), flags)
    except OSError as exc:
        if exc.errno in (errno.ENOENT, errno.ENOTDIR):
            yield str(sock)
            return
        raise SocketRootError("Socket slot directory open failed") from None
    try:
        fd_stat = os.fstat(dir_fd)
        try:
            path_stat = os.lstat(str(directory))
        except FileNotFoundError:
            # The slot directory vanished between open() and lstat()
            # (another process or an old instance's cleanup reclaimed
            # the same slot concurrently); treat the slot as
            # unavailable, same as the open() ENOENT/ENOTDIR fallback
            # above — callers treat a non-socket target as absent.
            yield str(sock)
            return
        _validate_slot_dir(fd_stat, path_stat, managed_uid, managed_gid)
        try:
            sock_stat = os.stat(
                AGENT_SOCKET_NAME, dir_fd=dir_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            sock_stat = None
        if sock_stat is not None:
            if stat.S_ISLNK(sock_stat.st_mode) or not stat.S_ISSOCK(sock_stat.st_mode):
                raise SocketRootError("Socket entry is not a real socket")
            if managed_uid is not None and sock_stat.st_uid != managed_uid:
                raise SocketRootError("Socket owner mismatch")
        yield _socket_target(dir_fd, sock)
    finally:
        os.close(dir_fd)
