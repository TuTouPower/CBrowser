"""Asyncio auth-forwarding proxy (t065). Stdlib only.

One process, one upstream, one listen socket. The upstream credentials live
in a JSON file mounted read-only into the forwarder container alone; the
Browser container never sees them.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import socket
import ssl
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cbrowser.redact import redact

logger = logging.getLogger("cbrowser.proxy_forwarder")

# The Browser reaches the forwarder on the per-profile Browser network.
# The port is fixed: the endpoint file the Runner reads carries it, and the
# forwarder container's network policy opens exactly this input port.
PROXY_FORWARDER_PORT = 18080

# Credentialless endpoint file, written to the Browser-readable runtime dir
# by the Supervisor. It carries no secret: scheme is always "http" (the
# forwarder speaks plain HTTP proxy protocol to the Browser) plus the
# forwarder container hostname, the listen port and the frozen credential
# revision the Runner checks before launching Chromium.
PROXY_FORWARDER_FILENAME = "proxy_forwarder.json"

_PROXY_SCHEMES = frozenset({"http", "https", "socks5"})
_CONNECT_TIMEOUT = 10.0
_FIRST_BYTE_TIMEOUT = 10.0
_MAX_HEAD_BYTES = 65536


class ForwarderConfigError(ValueError):
    """Upstream config is missing, malformed or unusable (fail closed)."""


class UpstreamError(RuntimeError):
    """Upstream unreachable or refused the request (fail closed)."""


class UpstreamAuthError(UpstreamError):
    """Upstream rejected the injected credentials (407 / SOCKS5 auth)."""


def _validate_upstream_scheme(scheme: Any) -> str:
    if scheme not in _PROXY_SCHEMES:
        raise ForwarderConfigError(f"unsupported upstream scheme: {scheme!r}")
    return scheme


def _validate_upstream_host(host: Any) -> str:
    if not isinstance(host, str) or not host:
        raise ForwarderConfigError("upstream host is required")
    return host


def _validate_upstream_port(port: Any) -> int:
    if type(port) is not int or not 1 <= port <= 65535:
        raise ForwarderConfigError("upstream port must be an integer 1..65535")
    return port


def _validate_upstream_username(username: Any) -> str | None:
    if username is not None and not isinstance(username, str):
        raise ForwarderConfigError("upstream username must be a string")
    return username


def _validate_upstream_password(username: Any, password: Any) -> str | None:
    if password is not None and not isinstance(password, str):
        raise ForwarderConfigError("upstream password must be a string")
    if username is None and password is not None:
        raise ForwarderConfigError(
            "upstream password without username is not allowed"
        )
    return password


def _validate_upstream_revision(revision: Any) -> int | None:
    if revision is not None and type(revision) is not int:
        raise ForwarderConfigError("credential_revision must be an integer")
    return revision


@dataclass(frozen=True)
class UpstreamConfig:
    scheme: str
    host: str
    port: int
    username: str | None
    password: str | None
    credential_revision: int | None

    @classmethod
    def from_dict(cls, data: Any) -> UpstreamConfig:
        if not isinstance(data, dict):
            raise ForwarderConfigError("upstream config must be a JSON object")
        return cls(
            scheme=_validate_upstream_scheme(data.get("scheme")),
            host=_validate_upstream_host(data.get("host")),
            port=_validate_upstream_port(data.get("port")),
            username=_validate_upstream_username(data.get("username")),
            password=_validate_upstream_password(
                data.get("username"), data.get("password")
            ),
            credential_revision=_validate_upstream_revision(
                data.get("credential_revision")
            ),
        )

    @property
    def basic_auth(self) -> str | None:
        if self.username is None:
            return None
        # RFC 7617: user-id is always followed by a colon, even when the
        # password is empty (a username-only credential is "user:").
        secret = f"{self.username}:{self.password or ''}"
        return "Basic " + base64.b64encode(secret.encode("utf-8")).decode("ascii")


def load_upstream_config(path: Path) -> UpstreamConfig:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ForwarderConfigError(
            f"upstream config unreadable: {Path(path).name}"
        ) from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ForwarderConfigError("upstream config is not valid JSON") from exc
    return UpstreamConfig.from_dict(data)


def read_forwarder_endpoint(path: Path) -> tuple[str, int]:
    """Read the credentialless forwarder endpoint file (t065).

    Returns ``(url, credential_revision)`` where the URL is a plain
    ``http://<forwarder-container>:18080`` with no userinfo. The file
    carries no secret, but any drift — wrong scheme, a host carrying
    userinfo or a path, a port other than the fixed listen port, a
    missing or non-integer revision — fails closed: the caller must
    refuse to launch or to open egress.
    """
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ForwarderConfigError(
            f"forwarder endpoint unreadable: {Path(path).name}"
        ) from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ForwarderConfigError(
            "forwarder endpoint is not valid JSON"
        ) from exc
    if not isinstance(data, dict):
        raise ForwarderConfigError("forwarder endpoint must be a JSON object")
    scheme = data.get("scheme")
    host = data.get("host")
    port = data.get("port")
    revision = data.get("credential_revision")
    if (
        scheme != "http"
        or not isinstance(host, str)
        or not host
        or any(c in host for c in ("@", "/", ":", " "))
        or type(port) is not int
        or port != PROXY_FORWARDER_PORT
        or type(revision) is not int
    ):
        raise ForwarderConfigError(
            "forwarder endpoint is malformed "
            "(want scheme=http, bare forwarder hostname, "
            f"port={PROXY_FORWARDER_PORT}, integer credential_revision)"
        )
    return f"http://{host}:{port}", revision


async def serve(
    config: UpstreamConfig, host: str, port: int
) -> asyncio.Server:
    return await asyncio.start_server(
        lambda r, w: handle_client(r, w, config), host, port
    )


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    config: UpstreamConfig,
) -> None:
    peer = writer.get_extra_info("peername")
    try:
        head = await asyncio.wait_for(
            reader.readuntil(b"\r\n\r\n"), timeout=_FIRST_BYTE_TIMEOUT
        )
    except (
        asyncio.TimeoutError,
        asyncio.IncompleteReadError,
        asyncio.LimitOverrunError,
        ConnectionError,
    ):
        # LimitOverrunError: the StreamReader's own 64 KiB limit (equal
        # to _MAX_HEAD_BYTES) fires before readuntil can return an
        # over-long head, so the length check below is only a second
        # layer for a reader built with a larger limit. Without this
        # except arm the overrun escaped handle_client unhandled.
        _close(writer)
        return
    if len(head) > _MAX_HEAD_BYTES:
        _close(writer)
        return
    try:
        lines = head.decode("latin-1").split("\r\n")
        method, target, _version = lines[0].split(" ", 2)
    except ValueError:
        _close(writer)
        return
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        key, _, value = line.partition(":")
        headers[key.strip().lower()] = value.strip()
    try:
        if method == "CONNECT":
            await _handle_connect(reader, writer, config, target)
        elif target.lower().startswith("http://"):
            await _handle_absolute_form(reader, writer, config, method, target, headers)
        else:
            # Origin-form or unknown: not a proxy request. Fail closed.
            logger.warning(
                "rejecting non-proxy request from %s",
                redact(str(peer)),
            )
            _close(writer)
    except UpstreamAuthError:
        logger.warning(
            "upstream rejected credentials for %s",
            redact(_safe_target(target)),
        )
        _close(writer)
    except UpstreamError as exc:
        logger.warning(
            "upstream failed for %s: %s",
            redact(_safe_target(target)),
            redact(str(exc)),
        )
        _close(writer)
    except (ConnectionError, asyncio.IncompleteReadError, asyncio.TimeoutError):
        _close(writer)


def _safe_target(target: str) -> str:
    """Target without any userinfo (a client must never send credentials;
    strip them before the value can reach a log line)."""
    try:
        split = urlsplit(target if "://" in target else "http://" + target)
        host = split.hostname or ""
        port = f":{split.port}" if split.port else ""
        return f"{host}{port}"
    except ValueError:
        return "<unparseable>"


def _bracket_host(host: str) -> str:
    """Bracket an IPv6 literal for a CONNECT request line / Host header.

    A bare IPv6 literal must travel as ``[2001:db8::1]:port``; hostnames
    and IPv4 literals pass through unchanged.
    """
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


async def _handle_connect(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    config: UpstreamConfig,
    target: str,
) -> None:
    host, _, port_text = target.rpartition(":")
    if not host or not port_text.isdigit():
        _close(writer)
        return
    if host.startswith("[") and host.endswith("]"):
        # IPv6 literal: strip the brackets for the SOCKS5 address
        # encoder (which re-encodes it as ATYP 0x04); the HTTP CONNECT
        # request line re-brackets it in _open_http_upstream.
        host = host[1:-1]
    port = int(port_text)
    upstream_reader, upstream_writer = await _open_upstream(
        config, host, port
    )
    try:
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        await _relay(reader, writer, upstream_reader, upstream_writer)
    finally:
        _close(upstream_writer)


async def _handle_absolute_form(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    config: UpstreamConfig,
    method: str,
    target: str,
    headers: dict[str, str],
) -> None:
    split = urlsplit(target)
    host = split.hostname
    port = split.port or (443 if split.scheme == "https" else 80)
    if not host:
        _close(writer)
        return
    if config.scheme in {"http", "https"}:
        # The upstream IS the HTTP proxy: open a plain TCP connection and
        # forward the absolute-form request to it (no CONNECT handshake).
        upstream_reader, upstream_writer = await _open_http_proxy_tcp(config)
        request_target = target
    else:
        # SOCKS5 is a TCP tunnel to the origin: open it, then speak
        # origin-form HTTP through the tunnel.
        upstream_reader, upstream_writer = await _open_upstream(
            config, host, port
        )
        request_target = split.path or "/"
        if split.query:
            request_target += f"?{split.query}"
    try:
        # One request per connection: forward with Connection: close so the
        # response is delimited by EOF. The client's own Proxy-Authorization
        # (there must be none: the Browser holds no credentials) is dropped
        # and replaced by the injected one.
        forwarded = [f"{method} {request_target} HTTP/1.1"]
        for key, value in headers.items():
            if key in {"proxy-authorization", "proxy-connection", "connection"}:
                continue
            forwarded.append(f"{key}: {value}")
        auth = config.basic_auth
        if auth is not None and config.scheme in {"http", "https"}:
            forwarded.append(f"Proxy-Authorization: {auth}")
        forwarded.append("Connection: close")
        forwarded.append("")
        forwarded.append("")
        upstream_writer.write("\r\n".join(forwarded).encode("latin-1"))
        await upstream_writer.drain()
        if config.scheme in {"http", "https"}:
            # The upstream is a proxy, not the origin: a non-2xx answer
            # (407 included) is a proxy refusal, not origin content.
            # Fail closed like the CONNECT path — close both sides and
            # relay nothing, so an upstream-controlled response body can
            # never reach the Browser.
            try:
                head = await asyncio.wait_for(
                    upstream_reader.readuntil(b"\r\n\r\n"),
                    timeout=_FIRST_BYTE_TIMEOUT,
                )
            except (
                asyncio.TimeoutError,
                asyncio.IncompleteReadError,
                asyncio.LimitOverrunError,
                ConnectionError,
            ) as exc:
                raise UpstreamError(
                    "upstream closed the proxy response"
                ) from exc
            status = head.decode("latin-1", errors="replace").split("\r\n", 1)[0]
            if status.startswith("HTTP/1.1 407") or status.startswith(
                "HTTP/1.0 407"
            ):
                raise UpstreamAuthError("upstream answered 407")
            if not (
                status.startswith("HTTP/1.1 2") or status.startswith("HTTP/1.0 2")
            ):
                raise UpstreamError(f"upstream proxy refused: {status}")
            writer.write(head)
            await writer.drain()
        # Relay both ways from here: any request body still arriving from
        # the client is forwarded, and the response streams back. The
        # forwarded Connection: close makes the upstream close after the
        # response, which ends the session.
        await _relay(reader, writer, upstream_reader, upstream_writer)
    finally:
        _close(upstream_writer)


async def _open_http_proxy_tcp(
    config: UpstreamConfig,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """TCP to an HTTP upstream (absolute-form requests only).

    No CONNECT handshake: the absolute-form request itself is the proxy
    request. An ``https`` upstream is wrapped in TLS first (same as a
    browser speaking to an HTTPS proxy); an ``http`` upstream stays
    plain TCP.
    """
    try:
        return await asyncio.wait_for(
            asyncio.open_connection(
                config.host,
                config.port,
                ssl=_tls_context(config),
            ),
            timeout=_CONNECT_TIMEOUT,
        )
    except (OSError, asyncio.TimeoutError) as exc:
        raise UpstreamError(f"cannot reach upstream {config.host}:{config.port}") from exc


def _tls_context(config: UpstreamConfig) -> ssl.SSLContext | None:
    """Default-verifying TLS context for an ``https`` upstream, else None.

    ``asyncio.open_connection`` defaults ``server_hostname`` to the host
    when ``ssl`` is given, so SNI and certificate verification use the
    upstream hostname. A plain-``http`` upstream gets no context.
    """
    if config.scheme != "https":
        return None
    return ssl.create_default_context()


async def _open_upstream(
    config: UpstreamConfig, host: str, port: int
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    if config.scheme in {"http", "https"}:
        return await _open_http_upstream(config, host, port)
    return await _open_socks5_upstream(config, host, port)


async def _open_http_upstream(
    config: UpstreamConfig, host: str, port: int
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                config.host,
                config.port,
                ssl=_tls_context(config),
            ),
            timeout=_CONNECT_TIMEOUT,
        )
    except (OSError, asyncio.TimeoutError) as exc:
        raise UpstreamError(f"cannot reach upstream {config.host}:{config.port}") from exc
    request = [
        f"CONNECT {_bracket_host(host)}:{port} HTTP/1.1",
        f"Host: {_bracket_host(host)}:{port}",
    ]
    auth = config.basic_auth
    if auth is not None:
        request.append(f"Proxy-Authorization: {auth}")
    request.extend(["Proxy-Connection: keep-alive", "", ""])
    try:
        writer.write("\r\n".join(request).encode("latin-1"))
        await writer.drain()
        head = await asyncio.wait_for(
            reader.readuntil(b"\r\n\r\n"), timeout=_FIRST_BYTE_TIMEOUT
        )
    except (
        asyncio.TimeoutError,
        asyncio.IncompleteReadError,
        asyncio.LimitOverrunError,  # f010: third readuntil site; f007 fixed the other two
        ConnectionError,
    ) as exc:
        _close(writer)
        raise UpstreamError("upstream closed the CONNECT handshake") from exc
    status = head.decode("latin-1", errors="replace").split("\r\n", 1)[0]
    if status.startswith("HTTP/1.1 407") or status.startswith("HTTP/1.0 407"):
        _close(writer)
        raise UpstreamAuthError("upstream answered 407")
    if not (status.startswith("HTTP/1.1 200") or status.startswith("HTTP/1.0 200")):
        _close(writer)
        raise UpstreamError(f"upstream CONNECT refused: {status}")
    return reader, writer


async def _open_socks5_upstream(
    config: UpstreamConfig, host: str, port: int
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(config.host, config.port),
            timeout=_CONNECT_TIMEOUT,
        )
    except (OSError, asyncio.TimeoutError) as exc:
        raise UpstreamError(f"cannot reach upstream {config.host}:{config.port}") from exc
    try:
        methods = b"\x05\x01\x02" if config.username is not None else b"\x05\x01\x00"
        writer.write(methods)
        await writer.drain()
        chosen = await asyncio.wait_for(reader.readexactly(2), timeout=_FIRST_BYTE_TIMEOUT)
        if chosen[0] != 0x05 or chosen[1] not in (0x00, 0x02):
            raise UpstreamError("SOCKS5 greeting rejected")
        if chosen[1] == 0x02:
            if config.username is None or config.password is None:
                raise UpstreamAuthError("SOCKS5 demands credentials")
            user = config.username.encode("utf-8")
            password = config.password.encode("utf-8")
            writer.write(
                b"\x01"
                + bytes([len(user)])
                + user
                + bytes([len(password)])
                + password
            )
            await writer.drain()
            auth = await asyncio.wait_for(
                reader.readexactly(2), timeout=_FIRST_BYTE_TIMEOUT
            )
            if auth[0] != 0x01 or auth[1] != 0x00:
                raise UpstreamAuthError("SOCKS5 authentication failed")
        # Remote DNS: hostnames travel as domain addresses, so the target
        # is never resolved on this host. An IPv6 literal travels as a
        # 16-byte address (ATYP 0x04), an IPv4 literal as 4 bytes
        # (ATYP 0x01); only a real hostname becomes ATYP 0x03.
        try:
            raw_ip6 = socket.inet_pton(socket.AF_INET6, host)
            address = b"\x04" + raw_ip6
        except OSError:
            try:
                raw_ip = socket.inet_aton(host)
                address = b"\x01" + raw_ip
            except OSError:
                encoded = host.encode("utf-8")
                if len(encoded) > 255:
                    raise UpstreamError("SOCKS5 hostname too long")
                address = b"\x03" + bytes([len(encoded)]) + encoded
        writer.write(
            b"\x05\x01\x00" + address + port.to_bytes(2, "big")
        )
        await writer.drain()
        reply = await asyncio.wait_for(reader.readexactly(4), timeout=_FIRST_BYTE_TIMEOUT)
        if reply[0] != 0x05 or reply[1] != 0x00:
            raise UpstreamError(f"SOCKS5 CONNECT refused: rep={reply[1]}")
        atyp = reply[3]
        if atyp == 0x01:
            await asyncio.wait_for(reader.readexactly(6), timeout=_FIRST_BYTE_TIMEOUT)
        elif atyp == 0x03:
            length = (await asyncio.wait_for(reader.readexactly(1), timeout=_FIRST_BYTE_TIMEOUT))[0]
            await asyncio.wait_for(
                reader.readexactly(length + 2), timeout=_FIRST_BYTE_TIMEOUT
            )
        elif atyp == 0x04:
            await asyncio.wait_for(reader.readexactly(18), timeout=_FIRST_BYTE_TIMEOUT)
        else:
            raise UpstreamError("SOCKS5 reply address type unknown")
    except UpstreamError:
        _close(writer)
        raise
    except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError) as exc:
        _close(writer)
        raise UpstreamError("SOCKS5 handshake failed") from exc
    return reader, writer


async def _relay(
    a_reader: asyncio.StreamReader,
    a_writer: asyncio.StreamWriter,
    b_reader: asyncio.StreamReader,
    b_writer: asyncio.StreamWriter,
) -> None:
    """Pump both directions until either side closes, then close both.

    First-completion semantics: a proxy must not wait for the idle side
    (a keep-alive client would hang the session forever after the upstream
    already answered and closed).
    """

    async def pump(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                chunk = await reader.read(65536)
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass

    tasks = [
        asyncio.ensure_future(pump(a_reader, b_writer)),
        asyncio.ensure_future(pump(b_reader, a_writer)),
    ]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        _close(a_writer)
        _close(b_writer)


def _close(writer: asyncio.StreamWriter) -> None:
    try:
        writer.close()
    except Exception:  # noqa: BLE001 - close is best-effort
        pass
