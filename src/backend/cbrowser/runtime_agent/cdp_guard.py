"""CDP loopback boundary guard.

Chrome's DevTools endpoint is kept on an internal loopback port reachable only
by in-container runtime_agent clients. This guard owns the advertised
``cdp_port`` on 127.0.0.1 and is the sole externally reachable CDP entry point:
every HTTP request is Host-checked, every WebSocket upgrade is Host- and
Origin-checked, and only allowed traffic is proxied to Chrome. Anything
malformed or unexpected fails closed with 403 without leaking version data.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger("cbrowser.runtime_agent.cdp_guard")

_HOST_RE = re.compile(r"(?:127\.0\.0\.1|localhost)(?::\d+)?", re.IGNORECASE)
_ORIGIN_RE = re.compile(r"http://(?:127\.0\.0\.1|localhost)(?::\d+)?", re.IGNORECASE)
_FORBIDDEN = (
    b"HTTP/1.1 403 Forbidden\r\n"
    b"Content-Type: text/plain\r\n"
    b"Content-Length: 9\r\n"
    b"Connection: close\r\n"
    b"\r\n"
    b"Forbidden"
)

Header = tuple[str, str]


def host_is_allowed(value: str | None) -> bool:
    """Allow only loopback literals/``localhost`` with an optional numeric port."""
    if not isinstance(value, str):
        return False
    return _HOST_RE.fullmatch(value) is not None


def origin_is_allowed(value: str | None) -> bool:
    """Allow only plain-HTTP loopback/localhost origins with an optional port."""
    if not isinstance(value, str):
        return False
    return _ORIGIN_RE.fullmatch(value) is not None


def _retarget(url: str, port: int) -> str:
    parts = urlsplit(url)
    return urlunsplit(("ws", f"127.0.0.1:{port}", parts.path, parts.query, parts.fragment))


def _rewrite_value(value: object, port: int) -> object:
    if isinstance(value, dict):
        result: dict[object, object] = {}
        for key, item in value.items():
            if key == "webSocketDebuggerUrl" and isinstance(item, str):
                result[key] = _retarget(item, port)
            else:
                result[key] = _rewrite_value(item, port)
        return result
    if isinstance(value, list):
        return [_rewrite_value(item, port) for item in value]
    return value


def rewrite_json_ws_urls(body: bytes, port: int) -> bytes:
    """Point every ``webSocketDebuggerUrl`` in a JSON body back at the guard."""
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return body
    return json.dumps(_rewrite_value(data, port), separators=(",", ":")).encode("utf-8")


class CdpGuard:
    """Loopback-only, fail-closed HTTP/WebSocket reverse proxy for Chrome CDP."""

    def __init__(self, chrome_port: int, *, host: str = "127.0.0.1") -> None:
        self._chrome_port = chrome_port
        self._host = host
        self._server: asyncio.AbstractServer | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._port = 0
        self._bound_host = ""

    @property
    def port(self) -> int:
        return self._port

    @property
    def bound_host(self) -> str:
        return self._bound_host

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._accept, self._host, 0)
        sockname = self._server.sockets[0].getsockname()
        self._bound_host = str(sockname[0])
        self._port = int(sockname[1])
        logger.info(
            "CDP guard listening on %s:%d (Chrome upstream %d)",
            self._bound_host,
            self._port,
            self._chrome_port,
        )
        return self._port

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        try:
            await self._handle_client(reader, writer)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - a broken peer must not escape as 500
            logger.warning("CDP guard connection aborted (%s)", type(exc).__name__)
        finally:
            if task is not None:
                self._tasks.discard(task)
            try:
                writer.close()
            except Exception:  # noqa: BLE001 - teardown is best-effort
                pass

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            method, target, version, headers, body = await self._read_request(reader)
            host_values = [v for n, v in headers if n == "host"]
            if len(host_values) != 1 or not host_is_allowed(host_values[0]):
                await self._write_forbidden(writer)
                return
            if self._is_websocket_upgrade(headers):
                origin_values = [v for n, v in headers if n == "origin"]
                if len(origin_values) != 1 or not origin_is_allowed(origin_values[0]):
                    await self._write_forbidden(writer)
                    return
                await self._proxy_ws(method, target, version, headers, reader, writer)
                return
            await self._proxy_http(method, target, body, writer)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - any malformed input fails closed as 403
            logger.warning("CDP guard request rejected (%s)", type(exc).__name__)
            await self._write_forbidden(writer)

    @staticmethod
    async def _read_request(
        reader: asyncio.StreamReader,
    ) -> tuple[str, str, str, list[Header], bytes]:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10)
        lines = head.decode("iso-8859-1").split("\r\n")
        parts = lines[0].split(" ")
        if len(parts) != 3 or not parts[2].startswith("HTTP/"):
            raise ValueError("malformed request line")
        method, target, version = parts
        headers: list[Header] = []
        for line in lines[1:]:
            if not line:
                continue
            name, sep, value = line.partition(":")
            if not sep:
                raise ValueError("malformed header")
            headers.append((name.strip().lower(), value.strip()))
        length = 0
        for name, value in headers:
            if name == "content-length":
                length = int(value)
                break
        body = b""
        if length > 0:
            body = await asyncio.wait_for(reader.readexactly(length), timeout=10)
        return method, target, version, headers, body

    @staticmethod
    def _is_websocket_upgrade(headers: list[Header]) -> bool:
        return any(n == "upgrade" and v.lower() == "websocket" for n, v in headers)

    async def _write_forbidden(self, writer: asyncio.StreamWriter) -> None:
        try:
            writer.write(_FORBIDDEN)
            await writer.drain()
        except Exception:  # noqa: BLE001 - peer may already be gone
            pass

    async def _proxy_http(
        self,
        method: str,
        target: str,
        body: bytes,
        writer: asyncio.StreamWriter,
    ) -> None:
        request = (
            f"{method} {target} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self._chrome_port}\r\n"
            f"Connection: close\r\n"
        )
        if body:
            request += f"Content-Length: {len(body)}\r\n"
        request += "\r\n"
        payload = request.encode("iso-8859-1") + body

        up_reader, up_writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", self._chrome_port), timeout=10
        )
        try:
            up_writer.write(payload)
            await asyncio.wait_for(up_writer.drain(), timeout=10)
            status_line, resp_headers, resp_body = await asyncio.wait_for(
                self._read_response(up_reader), timeout=10
            )
        except Exception as exc:  # noqa: BLE001 - upstream failure fails closed as 403
            logger.warning("CDP guard upstream HTTP failed (%s)", type(exc).__name__)
            await self._write_forbidden(writer)
            return
        finally:
            up_writer.close()

        new_body = rewrite_json_ws_urls(resp_body, self._port)
        content_type = next(
            (v for n, v in resp_headers if n == "content-type"),
            "application/octet-stream",
        )
        header = (
            f"{status_line}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(new_body)}\r\n"
            f"Connection: close\r\n\r\n"
        )
        writer.write(header.encode("iso-8859-1") + new_body)
        await writer.drain()

    @staticmethod
    async def _read_response(
        reader: asyncio.StreamReader,
    ) -> tuple[str, list[Header], bytes]:
        head = await reader.readuntil(b"\r\n\r\n")
        lines = head.decode("iso-8859-1").split("\r\n")
        status_line = lines[0]
        headers: list[Header] = []
        for line in lines[1:]:
            if not line:
                continue
            name, sep, value = line.partition(":")
            if sep:
                headers.append((name.strip().lower(), value.strip()))
        length: int | None = None
        chunked = False
        for name, value in headers:
            if name == "content-length":
                length = int(value)
            elif name == "transfer-encoding" and "chunked" in value.lower():
                chunked = True
        if chunked:
            body = await CdpGuard._read_chunked(reader)
        elif length is not None:
            body = await reader.readexactly(length)
        else:
            body = await reader.read()
        return status_line, headers, body

    @staticmethod
    async def _read_chunked(reader: asyncio.StreamReader) -> bytes:
        chunks: list[bytes] = []
        while True:
            line = await reader.readuntil(b"\r\n")
            size = int(line[:-2].split(b";", 1)[0], 16)
            if size == 0:
                await reader.readuntil(b"\r\n")
                break
            chunks.append(await reader.readexactly(size))
            await reader.readexactly(2)
        return b"".join(chunks)

    async def _proxy_ws(
        self,
        method: str,
        target: str,
        version: str,
        headers: list[Header],
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        forward = f"{method} {target} {version}\r\n"
        for name, value in headers:
            if name == "host":
                forward += f"Host: 127.0.0.1:{self._chrome_port}\r\n"
            elif name == "origin":
                continue
            else:
                forward += f"{name}: {value}\r\n"
        forward += "\r\n"

        up_reader: asyncio.StreamReader | None = None
        up_writer: asyncio.StreamWriter | None = None
        try:
            try:
                up_reader, up_writer = await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", self._chrome_port), timeout=10
                )
                up_writer.write(forward.encode("iso-8859-1"))
                await asyncio.wait_for(up_writer.drain(), timeout=10)
                resp_head = await asyncio.wait_for(
                    up_reader.readuntil(b"\r\n\r\n"), timeout=10
                )
                if not (
                    resp_head.startswith(b"HTTP/1.1 101")
                    or resp_head.startswith(b"HTTP/1.0 101")
                ):
                    raise RuntimeError("upstream refused upgrade")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - upstream failure fails closed as 403
                logger.warning(
                    "CDP guard upstream WebSocket unavailable (%s)", type(exc).__name__
                )
                await self._write_forbidden(writer)
                return

            writer.write(resp_head)
            await writer.drain()
            await self._tunnel(reader, writer, up_reader, up_writer)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - tunnel teardown must not surface as 500
            logger.warning("CDP guard WebSocket tunnel ended (%s)", type(exc).__name__)
        finally:
            if up_writer is not None:
                up_writer.close()

    @staticmethod
    async def _tunnel(
        down_reader: asyncio.StreamReader,
        down_writer: asyncio.StreamWriter,
        up_reader: asyncio.StreamReader,
        up_writer: asyncio.StreamWriter,
    ) -> None:
        async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
            try:
                while True:
                    data = await src.read(65536)
                    if not data:
                        return
                    dst.write(data)
                    await dst.drain()
            except (ConnectionError, OSError):
                return

        tasks = [
            asyncio.create_task(pipe(down_reader, up_writer)),
            asyncio.create_task(pipe(up_reader, down_writer)),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
