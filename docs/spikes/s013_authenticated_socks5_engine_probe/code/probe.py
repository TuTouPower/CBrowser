"""s013: does CloakBrowser 0.6.4 / Chromium 146 honour authenticated SOCKS5?

Runs entirely inside the Linux arm64 probe container:
  * a minimal RFC 1928 SOCKS5 server that REQUIRES username/password (0x02)
  * a local HTTP target that reports the peer address it sees
  * the real Chromium 146 engine launched with
    --proxy-server=socks5://user:pass@127.0.0.1:1080

Chromium is asked to fetch the target through the proxy; a control run uses
an unauthenticated SOCKS5 server (method 0x00).  The experiment records
whether the engine performs the auth sub-negotiation and whether the page
loads.  No product code is modified.
"""

from __future__ import annotations

import http.server
import json
import socket
import socketserver
import struct
import threading
import time
from pathlib import Path

PROXY_HOST, PROXY_PORT = "127.0.0.1", 1080
TARGET_HOST, TARGET_PORT = "127.0.0.1", 8080
USER, PASSWORD = b"probeuser", b"probepass"
EVENTS: list[dict] = []
ENGINE = (
    "/data/engine-cache/chromium-146.0.7680.177.3/chrome"
)


class TargetHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        EVENTS.append({"event": "http_request", "client": str(self.client_address)})
        body = b"<html><title>probe-ok</title><body>proxy-reached</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


class Socks5Handler(socketserver.BaseRequestHandler):
    require_auth: bool = True

    def _recv_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.request.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("eof")
            buf += chunk
        return buf

    def handle(self) -> None:
        try:
            greeting = self._recv_exact(2)
            ver, nmethods = greeting
            methods = self._recv_exact(nmethods)
            EVENTS.append(
                {"event": "greeting", "version": ver, "methods": list(methods)}
            )
            chosen = 0x02 if self.require_auth else 0x00
            if chosen not in methods:
                self.request.sendall(b"\x05\xff")
                EVENTS.append({"event": "no_acceptable_method"})
                return
            self.request.sendall(bytes([5, chosen]))
            if self.require_auth:
                auth = self._recv_exact(2)
                ulen = auth[1]
                uname = self._recv_exact(ulen)
                plen = self._recv_exact(1)[0]
                passwd = self._recv_exact(plen)
                EVENTS.append(
                    {
                        "event": "auth_attempt",
                        "username": uname.decode("utf-8", "replace"),
                        "password": passwd.decode("utf-8", "replace"),
                    }
                )
                ok = uname == USER and passwd == PASSWORD
                self.request.sendall(b"\x01\x00" if ok else b"\x01\x01")
                if not ok:
                    EVENTS.append({"event": "auth_rejected"})
                    return
                EVENTS.append({"event": "auth_accepted"})
            req = self._recv_exact(4)
            atyp = req[3]
            if atyp == 1:
                addr = socket.inet_ntoa(self._recv_exact(4))
            elif atyp == 3:
                addr = self._recv_exact(self._recv_exact(1)[0]).decode()
            else:
                addr = socket.inet_ntop(socket.AF_INET6, self._recv_exact(16))
            port = struct.unpack("!H", self._recv_exact(2))[0]
            EVENTS.append({"event": "connect", "addr": addr, "port": port})
            upstream = socket.create_connection((addr, port), timeout=5)
            self.request.sendall(b"\x05\x00\x00\x01" + socket.inet_aton("127.0.0.1") + struct.pack("!H", PROXY_PORT))
            EVENTS.append({"event": "connect_ok"})
            self._pump(self.request, upstream)
        except Exception as exc:  # noqa: BLE001 - probe diagnostics
            EVENTS.append({"event": "proxy_error", "detail": type(exc).__name__})

    @staticmethod
    def _pump(client: socket.socket, upstream: socket.socket) -> None:
        import select

        sockets = [client, upstream]
        while True:
            readable, _, _ = select.select(sockets, [], [], 5)
            if not readable:
                break
            for s in readable:
                data = s.recv(65536)
                if not data:
                    return
                (upstream if s is client else client).sendall(data)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_servers(require_auth: bool, port: int) -> tuple[Server, http.server.HTTPServer]:
    handler = type("H", (Socks5Handler,), {"require_auth": require_auth})
    proxy = Server((PROXY_HOST, port), handler)
    target = http.server.ThreadingHTTPServer((TARGET_HOST, TARGET_PORT), TargetHandler)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    threading.Thread(target=target.serve_forever, daemon=True).start()
    return proxy, target


def run_engine(use_auth: bool, port: int, password: bytes = PASSWORD) -> dict:
    from playwright.sync_api import sync_playwright

    url = (
        f"socks5://{USER.decode()}:{password.decode()}@{PROXY_HOST}:{port}"
        if use_auth
        else f"socks5://{PROXY_HOST}:{port}"
    )
    result: dict = {"proxy_server": url, "loaded": False, "title": None, "error": None}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=ENGINE,
            headless=True,
            args=[
                "--no-sandbox",
                f"--proxy-server={url}",
                "--proxy-bypass-list=<-loopback>",
            ],
        )
        page = browser.new_page()
        try:
            resp = page.goto(
                f"http://{TARGET_HOST}:{TARGET_PORT}/",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            result["loaded"] = resp is not None and resp.status == 200
            result["title"] = page.title()
        except Exception as exc:  # noqa: BLE001 - probe diagnostics
            result["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        finally:
            browser.close()
    return result


def main() -> None:
    print(json.dumps({"engine": ENGINE, "exists": Path(ENGINE).is_file()}))
    for idx, (label, auth, passwd) in enumerate(
        (
            ("unauthenticated_control", False, PASSWORD),
            ("authenticated", True, PASSWORD),
            ("authenticated_wrong_password", True, b"wrongpass"),
        )
    ):
        EVENTS.clear()
        port = PROXY_PORT + idx
        proxy, target = start_servers(auth, port)
        time.sleep(0.3)
        outcome = run_engine(auth, port, passwd)
        proxy.shutdown()
        proxy.server_close()
        target.shutdown()
        target.server_close()
        print(json.dumps({"case": label, "outcome": outcome, "events": EVENTS}, ensure_ascii=False))


if __name__ == "__main__":
    main()
