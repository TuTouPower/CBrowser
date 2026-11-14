"""t065: proxy auth-forwarder protocol proofs (no Docker required).

The forwarder is the credentialless entry point the Browser uses: it holds
the upstream proxy credentials, injects auth toward the upstream, and never
lets a secret reach the Browser container. These tests drive the forwarder
against in-process fake upstreams (HTTP proxy / SOCKS5 / origin) over
loopback sockets.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import socket
import ssl
import subprocess
import time
from pathlib import Path

import pytest

from cbrowser.proxy_forwarder.forwarder import (
    PROXY_FORWARDER_PORT,
    ForwarderConfigError,
    UpstreamConfig,
    load_upstream_config,
    serve,
)

ORIGIN_BODY = b"ORIGIN-BODY"
USER = "us@er"
PASSWORD = "p@ss:w/rd?"
WRONG_PASSWORD = "n0t-the-password"


def _basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


async def _read_exactly(reader: asyncio.StreamReader, n: int) -> bytes:
    data = await reader.readexactly(n)
    return data


async def _read_headers(reader: asyncio.StreamReader) -> tuple[str, dict[str, str]]:
    """Read one HTTP request/response head; returns (first line, headers)."""
    head = await reader.readuntil(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        key, _, value = line.partition(":")
        headers[key.strip().lower()] = value.strip()
    return lines[0], headers


class FakeOrigin:
    """Minimal HTTP origin: answers every request with a fixed body."""

    def __init__(self) -> None:
        self.connections = 0
        self.requests: list[str] = []
        self._server: asyncio.Server | None = None

    async def start(self, host: str = "127.0.0.1") -> int:
        self._server = await asyncio.start_server(
            self._handle, host, 0
        )
        return self._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.connections += 1
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            self.requests.append(head.decode("latin-1").split("\r\n")[0])
            body = ORIGIN_BODY
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\nConnection: close\r\n\r\n"
                + body
            )
            await writer.drain()
        except (asyncio.IncompleteRead, ConnectionError):
            pass
        finally:
            writer.close()

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()


class FakeHttpProxy:
    """HTTP proxy upstream requiring Proxy-Authorization; handles CONNECT
    (tunnel to the origin) and absolute-form GET (fetch via direct TCP)."""

    def __init__(self, origin_port: int, body_on_407: bytes = b"") -> None:
        self.origin_port = origin_port
        # Non-empty body_on_407 makes the 407 answer carry a body, so a
        # test can prove the forwarder never relays a proxy refusal body.
        self.body_on_407 = body_on_407
        self.auth_seen: list[str | None] = []
        self.connect_targets: list[str] = []
        self.absolute_targets: list[str] = []
        self.tls_seen: list[bool] = []
        self._server: asyncio.Server | None = None

    async def start(
        self, host: str = "127.0.0.1", ssl_context: object = None
    ) -> int:
        kwargs: dict[str, object] = {}
        if ssl_context is not None:
            kwargs["ssl"] = ssl_context
        self._server = await asyncio.start_server(self._handle, host, 0, **kwargs)  # type: ignore[arg-type]
        return self._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            self.tls_seen.append(
                writer.get_extra_info("ssl_object") is not None
            )
            first, headers = await _read_headers(reader)
        except (asyncio.IncompleteRead, ConnectionError):
            writer.close()
            return
        auth = headers.get("proxy-authorization")
        self.auth_seen.append(auth)
        if auth != _basic(USER, PASSWORD):
            body = self.body_on_407
            writer.write(
                b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                b'Proxy-Authenticate: Basic realm="test"\r\n'
                b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
            )
            await writer.drain()
            writer.close()
            return
        method, target, _version = first.split(" ", 2)
        if method == "CONNECT":
            self.connect_targets.append(target)
            host, _, port = target.rpartition(":")
            await self._tunnel(writer, reader, host, int(port))
            return
        self.absolute_targets.append(target)
        # Absolute-form: fetch the origin directly and relay the response.
        try:
            url = target
            rest = url.split("://", 1)[1]
            hostport, _, path = rest.partition("/")
            host, _, port = hostport.rpartition(":")
            origin_reader, origin_writer = await asyncio.open_connection(
                host, int(port or 80)
            )
            origin_writer.write(
                f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\n"
                "Connection: close\r\n\r\n".encode()
            )
            await origin_writer.drain()
            while True:
                chunk = await origin_reader.read(65536)
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()
            origin_writer.close()
        except (OSError, asyncio.IncompleteRead, ConnectionError):
            pass
        finally:
            writer.close()

    async def _tunnel(
        self,
        client_writer: asyncio.StreamWriter,
        client_reader: asyncio.StreamReader,
        host: str,
        port: int,
    ) -> None:
        try:
            origin_reader, origin_writer = await asyncio.open_connection(host, port)
        except OSError:
            client_writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            await client_writer.drain()
            client_writer.close()
            return
        client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await client_writer.drain()
        await _relay(client_reader, client_writer, origin_reader, origin_writer)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()


async def _relay(
    a_reader: asyncio.StreamReader,
    a_writer: asyncio.StreamWriter,
    b_reader: asyncio.StreamReader,
    b_writer: asyncio.StreamWriter,
) -> None:
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
        except (ConnectionError, asyncio.IncompleteRead):
            pass
        finally:
            try:
                writer.close()
            except Exception:  # noqa: BLE001 - close is best-effort
                pass

    await asyncio.gather(
        pump(a_reader, b_writer), pump(b_reader, a_writer), return_exceptions=True
    )


class FakeSocks5:
    """SOCKS5 upstream with username/password auth and remote DNS.

    Domain targets are resolved through ``domain_map`` only: a name that is
    absent from the map is refused, which proves the client never resolved
    it locally (a local resolver would have failed first for names such as
    ``unresolvable.invalid``).
    """

    def __init__(self, domain_map: dict[str, tuple[str, int]]) -> None:
        self.domain_map = domain_map
        self.auth_seen: list[tuple[str, str] | None] = []
        self.requested: list[str] = []
        # (address type, raw address bytes) per CONNECT request, so a
        # test can prove an IPv6 literal was encoded as ATYP 0x04.
        self.address_types: list[tuple[int, bytes]] = []
        self._server: asyncio.Server | None = None

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            greeting = await _read_exactly(reader, 2)
            assert greeting[0] == 0x05
            nmethods = greeting[1]
            methods = await _read_exactly(reader, nmethods)
            if 0x02 in methods:
                writer.write(b"\x05\x02")
            else:
                writer.write(b"\x05\x00")
            await writer.drain()
            if 0x02 in methods:
                auth_head = await _read_exactly(reader, 2)
                assert auth_head[0] == 0x01
                ulen = auth_head[1]
                user = (await _read_exactly(reader, ulen)).decode()
                plen = (await _read_exactly(reader, 1))[0]
                password = (await _read_exactly(reader, plen)).decode()
                self.auth_seen.append((user, password))
                if (user, password) != (USER, PASSWORD):
                    writer.write(b"\x01\x01")
                    await writer.drain()
                    writer.close()
                    return
                writer.write(b"\x01\x00")
                await writer.drain()
            req = await _read_exactly(reader, 4)
            assert req[0] == 0x05 and req[1] == 0x01
            atyp = req[3]
            if atyp == 0x03:
                dlen = (await _read_exactly(reader, 1))[0]
                raw = await _read_exactly(reader, dlen)
                host = raw.decode()
                self.address_types.append((0x03, raw))
            elif atyp == 0x01:
                raw = await _read_exactly(reader, 4)
                host = socket.inet_ntoa(raw)
                self.address_types.append((0x01, raw))
            elif atyp == 0x04:
                raw = await _read_exactly(reader, 16)
                host = socket.inet_ntop(socket.AF_INET6, raw)
                self.address_types.append((0x04, raw))
            else:
                writer.write(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00")
                await writer.drain()
                writer.close()
                return
            port = int.from_bytes(await _read_exactly(reader, 2), "big")
            self.requested.append(f"{host}:{port}")
            target = self.domain_map.get(host)
            if target is None:
                writer.write(b"\x05\x04\x00\x01\x00\x00\x00\x00\x00\x00")
                await writer.drain()
                writer.close()
                return
            origin_reader, origin_writer = await asyncio.open_connection(*target)
            writer.write(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
            await writer.drain()
            await _relay(reader, writer, origin_reader, origin_writer)
        except (asyncio.IncompleteRead, ConnectionError, AssertionError):
            writer.close()
            return

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()


def _upstream_config(**overrides: object) -> UpstreamConfig:
    data: dict[str, object] = {
        "scheme": "http",
        "host": "127.0.0.1",
        "port": 18081,
        "username": USER,
        "password": PASSWORD,
        "credential_revision": 3,
    }
    data.update(overrides)
    return UpstreamConfig(**data)  # type: ignore[arg-type]


async def _start_forwarder(config: UpstreamConfig) -> tuple[asyncio.Server, int]:
    server = await serve(config, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    return server, port


async def _http_get_via_forwarder(
    forwarder_port: int, target: str
) -> tuple[str, dict[str, str], bytes]:
    """CONNECT to target through the forwarder, then GET / over the tunnel."""
    reader, writer = await asyncio.open_connection("127.0.0.1", forwarder_port)
    host, _, port = target.rpartition(":")
    writer.write(
        f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode()
    )
    await writer.drain()
    status, _headers = await _read_headers(reader)
    assert status.startswith("HTTP/1.1 200"), status
    writer.write(f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
    await writer.drain()
    head = await reader.readuntil(b"\r\n\r\n")
    first = head.decode("latin-1").split("\r\n")[0]
    headers: dict[str, str] = {}
    for line in head.decode("latin-1").split("\r\n")[1:]:
        if line:
            key, _, value = line.partition(":")
            headers[key.strip().lower()] = value.strip()
    body = await reader.readexactly(int(headers["content-length"]))
    writer.close()
    return first, headers, body


async def test_http_upstream_connect_tunnel() -> None:
    origin = FakeOrigin()
    origin_port = await origin.start()
    proxy = FakeHttpProxy(origin_port)
    proxy_port = await proxy.start()
    config = _upstream_config(port=proxy_port)
    server, fw_port = await _start_forwarder(config)
    try:
        first, _headers, body = await _http_get_via_forwarder(
            fw_port, f"127.0.0.1:{origin_port}"
        )
        assert first.startswith("HTTP/1.1 200")
        assert body == ORIGIN_BODY
        assert proxy.auth_seen == [_basic(USER, PASSWORD)]
        assert proxy.connect_targets == [f"127.0.0.1:{origin_port}"]
        assert origin.connections == 1
    finally:
        server.close()
        await server.wait_closed()
        await proxy.stop()
        await origin.stop()


async def test_http_upstream_absolute_form_get() -> None:
    origin = FakeOrigin()
    origin_port = await origin.start()
    proxy = FakeHttpProxy(origin_port)
    proxy_port = await proxy.start()
    config = _upstream_config(port=proxy_port)
    server, fw_port = await _start_forwarder(config)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", fw_port)
        writer.write(
            f"GET http://127.0.0.1:{origin_port}/ HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{origin_port}\r\nConnection: close\r\n\r\n".encode()
        )
        await writer.drain()
        head = await reader.readuntil(b"\r\n\r\n")
        headers: dict[str, str] = {}
        for line in head.decode("latin-1").split("\r\n")[1:]:
            if line:
                key, _, value = line.partition(":")
                headers[key.strip().lower()] = value.strip()
        body = await reader.readexactly(int(headers["content-length"]))
        writer.close()
        assert body == ORIGIN_BODY
        assert proxy.auth_seen == [_basic(USER, PASSWORD)]
        assert proxy.absolute_targets == [f"http://127.0.0.1:{origin_port}/"]
    finally:
        server.close()
        await server.wait_closed()
        await proxy.stop()
        await origin.stop()


async def test_http_upstream_407_fails_closed(caplog: pytest.LogCaptureFixture) -> None:
    origin = FakeOrigin()
    origin_port = await origin.start()
    proxy = FakeHttpProxy(origin_port)
    proxy_port = await proxy.start()
    config = _upstream_config(port=proxy_port, password=WRONG_PASSWORD)
    server, fw_port = await _start_forwarder(config)
    try:
        with caplog.at_level(logging.INFO, logger="cbrowser.proxy_forwarder"):
            reader, writer = await asyncio.open_connection("127.0.0.1", fw_port)
            writer.write(
                f"CONNECT 127.0.0.1:{origin_port} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{origin_port}\r\n\r\n".encode()
            )
            await writer.drain()
            data = await reader.read()
            writer.close()
        # Fail closed: the connection is closed with no response body.
        assert data == b""
        assert origin.connections == 0
        assert PASSWORD not in caplog.text
        assert base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode() not in caplog.text
        assert WRONG_PASSWORD not in caplog.text
    finally:
        server.close()
        await server.wait_closed()
        await proxy.stop()
        await origin.stop()


async def test_socks5_connect_uses_remote_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    # Block local resolution of the target name for the duration of the
    # test: only the SOCKS5 server may map it, so a successful fetch means
    # the forwarder passed the domain through untouched (remote DNS).
    real_getaddrinfo = socket.getaddrinfo

    def _guarded(host: object, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if host == "unresolvable.invalid":
            raise socket.gaierror("blocked by test: target must not resolve locally")
        return real_getaddrinfo(host, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(socket, "getaddrinfo", _guarded)
    origin = FakeOrigin()
    origin_port = await origin.start()
    socks = FakeSocks5({"unresolvable.invalid": ("127.0.0.1", origin_port)})
    socks_port = await socks.start()
    config = _upstream_config(scheme="socks5", port=socks_port)
    server, fw_port = await _start_forwarder(config)
    try:
        first, _headers, body = await _http_get_via_forwarder(
            fw_port, "unresolvable.invalid:80"
        )
        assert first.startswith("HTTP/1.1 200")
        assert body == ORIGIN_BODY
        assert socks.auth_seen == [(USER, PASSWORD)]
        assert socks.requested == ["unresolvable.invalid:80"]
    finally:
        server.close()
        await server.wait_closed()
        await socks.stop()
        await origin.stop()


async def test_socks5_auth_failure_fails_closed() -> None:
    origin = FakeOrigin()
    origin_port = await origin.start()
    socks = FakeSocks5({"example.invalid": ("127.0.0.1", origin_port)})
    socks_port = await socks.start()
    config = _upstream_config(
        scheme="socks5", port=socks_port, password=WRONG_PASSWORD
    )
    server, fw_port = await _start_forwarder(config)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", fw_port)
        writer.write(
            b"CONNECT example.invalid:80 HTTP/1.1\r\nHost: example.invalid:80\r\n\r\n"
        )
        await writer.drain()
        data = await reader.read()
        writer.close()
        assert data == b""
        assert origin.connections == 0
    finally:
        server.close()
        await server.wait_closed()
        await socks.stop()
        await origin.stop()


async def test_upstream_down_fails_closed_without_direct_attempt() -> None:
    origin = FakeOrigin()
    origin_port = await origin.start()
    # No upstream listening: pick a port and confirm nothing answers.
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    dead_port = probe.getsockname()[1]
    probe.close()
    config = _upstream_config(port=dead_port)
    server, fw_port = await _start_forwarder(config)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", fw_port)
        writer.write(
            f"CONNECT 127.0.0.1:{origin_port} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{origin_port}\r\n\r\n".encode()
        )
        await writer.drain()
        data = await reader.read()
        writer.close()
        assert data == b""
        # No direct attempt: the origin never saw a connection.
        assert origin.connections == 0
    finally:
        server.close()
        await server.wait_closed()
        await origin.stop()


async def test_absolute_form_via_socks5() -> None:
    origin = FakeOrigin()
    origin_port = await origin.start()
    socks = FakeSocks5({"127.0.0.1": ("127.0.0.1", origin_port)})
    socks_port = await socks.start()
    config = _upstream_config(scheme="socks5", port=socks_port)
    server, fw_port = await _start_forwarder(config)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", fw_port)
        writer.write(
            f"GET http://127.0.0.1:{origin_port}/ HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{origin_port}\r\nConnection: close\r\n\r\n".encode()
        )
        await writer.drain()
        head = await reader.readuntil(b"\r\n\r\n")
        headers: dict[str, str] = {}
        for line in head.decode("latin-1").split("\r\n")[1:]:
            if line:
                key, _, value = line.partition(":")
                headers[key.strip().lower()] = value.strip()
        body = await reader.readexactly(int(headers["content-length"]))
        writer.close()
        assert body == ORIGIN_BODY
        assert socks.requested == [f"127.0.0.1:{origin_port}"]
    finally:
        server.close()
        await server.wait_closed()
        await socks.stop()
        await origin.stop()


async def test_http_upstream_ipv6_and_special_chars() -> None:
    origin = FakeOrigin()
    origin_port = await origin.start()
    proxy = FakeHttpProxy(origin_port)
    try:
        proxy_port = await proxy.start(host="::1")
    except OSError:
        pytest.skip("IPv6 loopback unavailable in this environment")
    config = _upstream_config(host="::1", port=proxy_port)
    server, fw_port = await _start_forwarder(config)
    try:
        first, _headers, body = await _http_get_via_forwarder(
            fw_port, f"127.0.0.1:{origin_port}"
        )
        assert body == ORIGIN_BODY
        # Special characters survive Base64 round-trip unchanged.
        assert proxy.auth_seen == [_basic(USER, PASSWORD)]
    finally:
        server.close()
        await server.wait_closed()
        await proxy.stop()
        await origin.stop()


async def test_socks5_ipv6_literal_target_uses_atyp4() -> None:
    """f003: a SOCKS5 upstream + IPv6 literal target must be encoded as
    ATYP 0x04 with the 16-byte address — never as a bracketed domain."""
    origin = FakeOrigin()
    try:
        origin_port = await origin.start(host="::1")
    except OSError:
        pytest.skip("IPv6 loopback unavailable in this environment")
    socks = FakeSocks5({"2001:db8::1": ("::1", origin_port)})
    socks_port = await socks.start()
    config = _upstream_config(scheme="socks5", port=socks_port)
    server, fw_port = await _start_forwarder(config)
    try:
        first, _headers, body = await _http_get_via_forwarder(
            fw_port, "[2001:db8::1]:443"
        )
        assert first.startswith("HTTP/1.1 200")
        assert body == ORIGIN_BODY
        assert socks.requested == ["2001:db8::1:443"]
        assert socks.address_types == [
            (0x04, socket.inet_pton(socket.AF_INET6, "2001:db8::1"))
        ]
    finally:
        server.close()
        await server.wait_closed()
        await socks.stop()
        await origin.stop()


def _make_tls_server_context(tmp_path: Path) -> ssl.SSLContext:
    """Self-signed cert for 127.0.0.1 (test only; openssl must exist)."""
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key), "-out", str(cert), "-days", "1", "-nodes",
            "-subj", "/CN=127.0.0.1",
            "-addext", "subjectAltName=IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))
    return context


async def test_https_upstream_wraps_tls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """f002: an https upstream gets a real TLS handshake before CONNECT
    (and before an absolute-form request); the proxy sees TLS, not
    plaintext."""
    try:
        server_context = _make_tls_server_context(tmp_path)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("openssl unavailable for a self-signed test certificate")
    # Production verifies with the default context; the test certificate
    # is self-signed, so only this test disables verification — the TLS
    # handshake and the CONNECT/absolute-form flows are still real.
    monkeypatch.setattr(
        ssl, "create_default_context", lambda: ssl._create_unverified_context()
    )
    origin = FakeOrigin()
    origin_port = await origin.start()
    proxy = FakeHttpProxy(origin_port)
    proxy_port = await proxy.start(ssl_context=server_context)
    config = _upstream_config(scheme="https", port=proxy_port)
    server, fw_port = await _start_forwarder(config)
    try:
        first, _headers, body = await _http_get_via_forwarder(
            fw_port, f"127.0.0.1:{origin_port}"
        )
        assert first.startswith("HTTP/1.1 200")
        assert body == ORIGIN_BODY
        assert proxy.tls_seen == [True]
        assert proxy.auth_seen == [_basic(USER, PASSWORD)]
        assert proxy.connect_targets == [f"127.0.0.1:{origin_port}"]
        # Absolute-form over the same TLS upstream.
        reader, writer = await asyncio.open_connection("127.0.0.1", fw_port)
        writer.write(
            f"GET http://127.0.0.1:{origin_port}/ HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{origin_port}\r\nConnection: close\r\n\r\n".encode()
        )
        await writer.drain()
        head = await reader.readuntil(b"\r\n\r\n")
        headers: dict[str, str] = {}
        for line in head.decode("latin-1").split("\r\n")[1:]:
            if line:
                key, _, value = line.partition(":")
                headers[key.strip().lower()] = value.strip()
        body = await reader.readexactly(int(headers["content-length"]))
        writer.close()
        assert body == ORIGIN_BODY
        assert proxy.tls_seen == [True, True]
    finally:
        server.close()
        await server.wait_closed()
        await proxy.stop()
        await origin.stop()


async def test_absolute_form_407_body_is_not_relayed() -> None:
    """f005: an absolute-form 407 (with a body) from an HTTP upstream
    must fail closed like the CONNECT path — the body never reaches
    the Browser."""
    origin = FakeOrigin()
    origin_port = await origin.start()
    proxy = FakeHttpProxy(origin_port, body_on_407=b"hello")
    proxy_port = await proxy.start()
    config = _upstream_config(port=proxy_port, password=WRONG_PASSWORD)
    server, fw_port = await _start_forwarder(config)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", fw_port)
        writer.write(
            f"GET http://127.0.0.1:{origin_port}/ HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{origin_port}\r\nConnection: close\r\n\r\n".encode()
        )
        await writer.drain()
        data = await reader.read()
        writer.close()
        assert data == b""
        assert b"hello" not in data
        assert origin.connections == 0
    finally:
        server.close()
        await server.wait_closed()
        await proxy.stop()
        await origin.stop()


def test_basic_auth_username_only_keeps_colon() -> None:
    """f006 (RFC 7617): a username-only credential is 'user:', never
    bare 'user'."""
    config = UpstreamConfig.from_dict(
        {
            "scheme": "http",
            "host": "127.0.0.1",
            "port": 8080,
            "username": "user",
            "password": None,
            "credential_revision": None,
        }
    )
    assert config.basic_auth == "Basic " + base64.b64encode(b"user:").decode()
    anonymous = UpstreamConfig.from_dict(
        {
            "scheme": "http",
            "host": "127.0.0.1",
            "port": 8080,
            "username": None,
            "password": None,
            "credential_revision": None,
        }
    )
    assert anonymous.basic_auth is None


async def test_oversized_request_head_fails_closed_without_unhandled_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """f007: a request head over the 64 KiB bound closes the connection
    and must not escape handle_client as an unhandled LimitOverrunError."""
    origin = FakeOrigin()
    origin_port = await origin.start()
    proxy = FakeHttpProxy(origin_port)
    proxy_port = await proxy.start()
    config = _upstream_config(port=proxy_port)
    server, fw_port = await _start_forwarder(config)
    try:
        with caplog.at_level(logging.ERROR, logger="asyncio"):
            reader, writer = await asyncio.open_connection("127.0.0.1", fw_port)
            writer.write(b"GET / HTTP/1.1\r\nX-Pad: " + b"A" * 70000 + b"\r\n\r\n")
            await writer.drain()
            data = await reader.read()
            writer.close()
        assert data == b""
        assert "LimitOverrunError" not in caplog.text
        assert origin.connections == 0
    finally:
        server.close()
        await server.wait_closed()
        await proxy.stop()
        await origin.stop()


async def test_oversized_connect_response_head_fails_closed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """f010 (f007 same class, third readuntil site): an upstream that
    answers CONNECT with a head over the 64 KiB bound must fail closed
    — no unhandled LimitOverrunError, no hanging CONNECT."""
    received: list[str] = []

    async def _handle(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            first, _headers = await _read_headers(reader)
            received.append(first)
        except (asyncio.IncompleteRead, ConnectionError):
            writer.close()
            return
        writer.write(
            b"HTTP/1.1 200 Connection Established\r\nX-Pad: "
            + b"B" * 70000
            + b"\r\n\r\n"
        )
        await writer.drain()
        # Stay open briefly so a hung CONNECT would show as a hang,
        # not as a fast close.
        await asyncio.sleep(0.5)
        writer.close()

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    proxy_port = server.sockets[0].getsockname()[1]
    config = _upstream_config(port=proxy_port)
    fw_server, fw_port = await _start_forwarder(config)
    try:
        with caplog.at_level(logging.ERROR, logger="asyncio"):
            reader, writer = await asyncio.open_connection("127.0.0.1", fw_port)
            writer.write(
                b"CONNECT 127.0.0.1:443 HTTP/1.1\r\n"
                b"Host: 127.0.0.1:443\r\n\r\n"
            )
            await writer.drain()
            data = await asyncio.wait_for(reader.read(), timeout=10)
            writer.close()
        assert received == ["CONNECT 127.0.0.1:443 HTTP/1.1"]
        assert data == b""
        assert "LimitOverrunError" not in caplog.text
    finally:
        fw_server.close()
        await fw_server.wait_closed()
        server.close()
        await server.wait_closed()


def test_config_validation_fails_closed(tmp_path: Path) -> None:
    good = {
        "scheme": "http",
        "host": "127.0.0.1",
        "port": 18081,
        "username": USER,
        "password": PASSWORD,
        "credential_revision": 3,
    }
    path = tmp_path / "creds.json"
    path.write_text(json.dumps(good), encoding="utf-8")
    assert load_upstream_config(path).scheme == "http"

    bad_cases: list[dict[str, object]] = [
        {**good, "scheme": "ftp"},
        {**good, "host": ""},
        {**good, "port": 0},
        {**good, "port": 70000},
        {**good, "port": "18081"},
        {**good, "username": None, "password": PASSWORD},
        {**good, "credential_revision": "3"},
        {"scheme": "http"},
    ]
    for case in bad_cases:
        path.write_text(json.dumps(case), encoding="utf-8")
        with pytest.raises(ForwarderConfigError):
            load_upstream_config(path)
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(ForwarderConfigError):
        load_upstream_config(path)
    with pytest.raises(ForwarderConfigError):
        load_upstream_config(tmp_path / "missing.json")


async def test_origin_form_request_is_rejected() -> None:
    origin = FakeOrigin()
    origin_port = await origin.start()
    proxy = FakeHttpProxy(origin_port)
    proxy_port = await proxy.start()
    config = _upstream_config(port=proxy_port)
    server, fw_port = await _start_forwarder(config)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", fw_port)
        writer.write(b"GET /no-proxy-semantics HTTP/1.1\r\nHost: x\r\n\r\n")
        await writer.drain()
        data = await reader.read()
        writer.close()
        assert data == b""
        assert origin.connections == 0
    finally:
        server.close()
        await server.wait_closed()
        await proxy.stop()
        await origin.stop()


async def test_first_byte_smoke_reports_latency_samples(record_property) -> None:
    """AC-004 liveness smoke — NOT a baseline comparison.

    Five loopback fetches through the forwarder must all succeed; the
    run reports the first-byte latency samples (median + full list in
    the junit properties) for the record. This asserts liveness only:
    it says nothing about the forwarder vs. baseline. The AC-004
    baseline comparison (same topology/target/samples, success rate,
    first-byte and 407 round-trip report) is a real-deployment
    measurement owned by p098 item 4, not by this test.
    """
    origin = FakeOrigin()
    origin_port = await origin.start()
    proxy = FakeHttpProxy(origin_port)
    proxy_port = await proxy.start()
    config = _upstream_config(port=proxy_port)
    server, fw_port = await _start_forwarder(config)
    try:
        samples: list[float] = []
        for _ in range(5):
            start = time.monotonic()
            _first, _headers, body = await _http_get_via_forwarder(
                fw_port, f"127.0.0.1:{origin_port}"
            )
            samples.append(time.monotonic() - start)
            assert body == ORIGIN_BODY
        samples.sort()
        record_property("first_byte_samples_s", json.dumps(samples))
        record_property("median_first_byte_s", samples[len(samples) // 2])
    finally:
        server.close()
        await server.wait_closed()
        await proxy.stop()
        await origin.stop()


def test_forwarder_listen_port_constant() -> None:
    assert PROXY_FORWARDER_PORT == 18080
